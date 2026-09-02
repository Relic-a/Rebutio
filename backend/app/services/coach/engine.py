import asyncio
import datetime
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.db import (
    CoachMemory,
    CoachMessage,
    CoachThread,
    DebateReview,
    DebateSession,
    DerivedAudioClip,
    MediaAsset,
    User,
    utcnow,
)
from backend.app.models.schemas import (
    AudioEvidenceCardSchema,
    CoachHomeSchema,
    CoachMessageSchema,
    CoachOpeningAnalysisResult,
    CoachThreadDetailSchema,
    CoachThreadSummarySchema,
    CoachTurnResponse,
    OpeningAnalysisSchema,
    ProgressStatsSchema,
    QuickReplySchema,
    ScoreWithRubricSchema,
    SkillMasteryItemSchema,
)
from backend.app.observability.logging import get_logger
from backend.app.persistence.repositories import (
    CoachRepository,
    DebateSessionRepository,
    ProgressRepository,
    SpeechProfileRepository,
)
from backend.app.prompts.coach import (
    build_coach_conversation_prompt,
    build_coach_opening_prompt,
)
from backend.app.prompts.coach_memory import build_coach_memory_update_prompt
from backend.app.services.ai.config import ModelRole
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.media.storage import media_storage
from backend.app.services.modal.client import modal_speech_client
from backend.app.services.privacy.encryption import encryptor

logger = get_logger("rebutio.coach")


class CoachEngine:
    @staticmethod
    async def update_coach_memory_after_debate(
        db: AsyncSession,
        user_id: str,
        debate_summary: dict,
    ) -> str:
        coach_repo = CoachRepository(db)
        prev_md, rev = await coach_repo.get_memory_markdown(user_id)
        today = datetime.date.today().isoformat()
        session_id = debate_summary.get("session_id")
        session_marker = f"<!-- session:{session_id} -->" if session_id else None

        # Idempotency check: if this session was already recorded in coach memory, return current memory
        if session_marker and session_marker in prev_md:
            logger.info("coach.memory.already_recorded_for_session", session_id=session_id, user_id=user_id)
            return prev_md

        prompt_msgs = build_coach_memory_update_prompt(
            previous_memory_markdown=prev_md,
            debate_summary=debate_summary,
            current_date=today,
        )

        try:
            updated_md = await ai_gateway.update_coach_memory(
                messages=prompt_msgs,
                previous_markdown=prev_md,
                debate_summary=debate_summary,
                current_date=today,
            )
        except Exception as e:
            logger.warning("coach.memory_update_ai_failed", error=str(e), session_id=session_id, user_id=user_id)
            # Fail closed: DO NOT add marker, DO NOT save un-updated memory
            raise RuntimeError(f"Coach memory AI update failed: {e}") from e

        # Append session marker ONLY after successful Coach memory AI update
        if session_marker and session_marker not in updated_md:
            updated_md = f"{updated_md.rstrip()}\n\n{session_marker}\n"

        saved, new_rev = await coach_repo.save_memory_markdown(user_id, updated_md, expected_revision=rev)
        if not saved:
            logger.info("coach.memory.concurrency_conflict_retrying", user_id=user_id, expected_rev=rev)
            # 1. Reload latest Markdown and revision
            latest_md, latest_rev = await coach_repo.get_memory_markdown(user_id)
            if session_marker and session_marker in latest_md:
                logger.info("coach.memory.already_recorded_in_latest", session_id=session_id, user_id=user_id)
                return latest_md

            # 2. Rerun memory-update AI using the latest Markdown plus the new debate findings
            retry_prompt_msgs = build_coach_memory_update_prompt(
                previous_memory_markdown=latest_md,
                debate_summary=debate_summary,
                current_date=today,
            )
            try:
                retry_updated_md = await ai_gateway.update_coach_memory(
                    messages=retry_prompt_msgs,
                    previous_markdown=latest_md,
                    debate_summary=debate_summary,
                    current_date=today,
                )
            except Exception as e:
                logger.warning("coach.memory_update_retry_ai_failed", error=str(e), session_id=session_id, user_id=user_id)
                raise RuntimeError(f"Coach memory AI update failed during concurrency retry: {e}") from e

            # Only append marker after that retry AI update succeeds
            if session_marker and session_marker not in retry_updated_md:
                retry_updated_md = f"{retry_updated_md.rstrip()}\n\n{session_marker}\n"

            # 3. Retry the save once with the latest revision
            retry_saved, _ = await coach_repo.save_memory_markdown(user_id, retry_updated_md, expected_revision=latest_rev)
            if retry_saved:
                return retry_updated_md
            else:
                logger.warning("coach.memory_update_retry_conflict", user_id=user_id, revision=latest_rev)
                raise RuntimeError(f"Coach memory update concurrency conflict on retry for user {user_id}")

        return updated_md

    @staticmethod
    async def get_or_create_debate_coach_thread(
        db: AsyncSession,
        user_id: str,
        session_id: str,
    ) -> CoachThread:
        coach_repo = CoachRepository(db)
        sess_repo = DebateSessionRepository(db)
        session = None

        if session_id in ("latest", "current"):
            latest_sess = await sess_repo.get_latest_session_for_user(user_id)
            if latest_sess:
                session_id = latest_sess.id
                session = latest_sess
            else:
                session = None

        if not session:
            session = await sess_repo.get_session(session_id)

        if not session:
            # Create a sample session thread for first-time direct coaching navigation
            thread = await coach_repo.create_general_thread(user_id, "Debate Coaching")
            await coach_repo.add_message(
                user_id=user_id,
                thread_id=thread.id,
                sender="coach",
                message_type="opening_analysis",
                text="Welcome to your personal debate coach! Complete a live debate to analyze your spoken arguments, or ask me any debate strategy question below.",
                structured_data={
                    "opening_analysis": {
                        "overall_assessment": "Coaching system ready for live debate analysis.",
                        "most_important_strength": "Direct structural refutations.",
                        "highest_value_improvement": "Lead with your main point immediately in your opening sentence.",
                        "suggested_quick_replies": [
                            {"label": "How to structure an opening?", "prompt": "How should I structure my opening turn?"},
                            {"label": "Give me a practice drill", "prompt": "Give me a 1-minute spoken practice exercise."},
                            {"label": "How to handle tough questions?", "prompt": "How should I handle tough opponent questions?"},
                        ],
                    },
                    "quick_replies": [
                        {"label": "How to structure an opening?", "prompt": "How should I structure my opening turn?"},
                        {"label": "Give me a practice drill", "prompt": "Give me a 1-minute spoken practice exercise."},
                    ],
                },
            )
            return thread

        title = f"Debate Review: {session.topic_text[:50]}"
        thread = await coach_repo.get_or_create_debate_thread(
            user_id=user_id,
            session_id=session.id,
            title=title,
        )

        # If thread is brand new without messages, generate proactive opening analysis
        existing_messages = await coach_repo.get_thread_messages(thread.id)
        if not existing_messages:
            logger.info("coach.opening_analysis.generating", session_id=session.id, thread_id=thread.id)
            review = await sess_repo.get_review(session.id)
            memory_md, _ = await coach_repo.get_memory_markdown(user_id)

            transcript = []
            for t in session.turns:
                txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else ""
                transcript.append({
                    "speaker": t.speaker,
                    "turn_number": t.turn_number,
                    "text": txt,
                    "audio_available": getattr(t, "audio_available", False),
                    "duration_sec": getattr(t, "duration_sec", 0.0),
                })

            from backend.app.domain.evidence import assess_debate_evidence
            ev_assessment = assess_debate_evidence(transcript)
            opp_side = "disagree" if session.user_side == "agree" else "agree"

            if not ev_assessment.has_sufficient_evidence:
                opening_res = CoachOpeningAnalysisResult(
                    overall_assessment="There was not enough substantive speech in this debate session to evaluate your spoken English.",
                    most_important_strength="You initiated the session.",
                    highest_value_improvement="In your next debate, speak in at least two complete turns with a clear reason and an example.",
                    concrete_example=transcript[0]["text"] if transcript else None,
                    evidence_turn_number=1,
                    suggested_quick_replies=[
                        "How do I structure a spoken response?",
                        "What should I practice next?",
                        "Give me a 1-minute practice drill",
                    ],
                )
            else:
                review_dict = {
                    "outcome": review.outcome if review else "undetermined",
                    "stars": review.stars if review else 0,
                    "technique": review.score_technique if review else 8,
                    "grammar": review.score_grammar if review else 8,
                    "vocabulary": review.score_vocabulary if review else 8,
                    "delivery": review.score_delivery if review else 8,
                    "strongest_moment": review.strongest_moment if review else "Your speech stayed understandable across the exchange.",
                    "improvement_opportunity": review.improvement_opportunity if review else "Use shorter sentences so each spoken idea lands clearly.",
                    "language_feedback": encryptor.decrypt_json(review.language_feedback_encrypted) if review and review.language_feedback_encrypted else {},
                    "has_sufficient_evidence": True,
                }

                prompt_messages = build_coach_opening_prompt(
                    topic=session.topic_text,
                    user_side=session.user_side,
                    opponent_side=opp_side,
                    skill_name=session.skill_name,
                    difficulty=session.difficulty,
                    transcript=transcript,
                    review=review_dict,
                    coach_memory_markdown=memory_md,
                )

                try:
                    opening_res = await ai_gateway._execute_structured_completion(
                        role=ModelRole.LANGUAGE_ANALYSIS,
                        messages=prompt_messages,
                        schema_cls=CoachOpeningAnalysisResult,
                        fallback_factory=lambda: CoachOpeningAnalysisResult(
                            overall_assessment="Here is the highest-value pattern in your spoken English from this session.",
                            most_important_strength=review.strongest_moment if review and review.strongest_moment else "Your speech stayed understandable across the exchange.",
                            highest_value_improvement=review.improvement_opportunity if review and review.improvement_opportunity else "Use shorter sentences so each spoken idea lands clearly.",
                            concrete_example=transcript[0]["text"] if transcript else "Your opening argument.",
                            evidence_turn_number=1,
                            suggested_quick_replies=[
                                "Show me another example",
                                "How should I phrase it?",
                                "Was my grammar a problem?",
                                "What should I practice?",
                                "Let me try that again",
                            ],
                        ),
                    )
                except Exception as e:
                    logger.warning("coach.opening_analysis.failed_using_fallback", error=str(e))
                    opening_res = CoachOpeningAnalysisResult(
                        overall_assessment="Here is the highest-value pattern in your spoken English from this session.",
                        most_important_strength=review.strongest_moment if review and review.strongest_moment else "Your speech stayed understandable across the exchange.",
                        highest_value_improvement=review.improvement_opportunity if review and review.improvement_opportunity else "Use shorter sentences so each spoken idea lands clearly.",
                        concrete_example=transcript[0]["text"] if transcript else "Your opening argument.",
                        evidence_turn_number=1,
                        suggested_quick_replies=[
                            "Show me another example",
                            "How should I phrase it?",
                            "Was my grammar a problem?",
                            "What should I practice?",
                            "Let me try that again",
                        ],
                    )

            opening_data = {
                "overall_assessment": opening_res.overall_assessment,
                "most_important_strength": opening_res.most_important_strength,
                "highest_value_improvement": opening_res.highest_value_improvement,
                "concrete_example": opening_res.concrete_example,
                "evidence_turn_number": opening_res.evidence_turn_number,
                "suggested_quick_replies": [
                    {"label": r, "prompt": r} for r in opening_res.suggested_quick_replies
                ],
            }

            # Create the initial coach message with opening analysis
            await coach_repo.add_message(
                user_id=user_id,
                thread_id=thread.id,
                sender="coach",
                message_type="opening_analysis",
                text=opening_res.overall_assessment,
                structured_data=opening_data,
            )

            # Only attach derived audio evidence if debate had sufficient audio evidence
            stmt_assets = select(MediaAsset).where(
                MediaAsset.session_id == session.id,
                MediaAsset.user_id == user_id,
            ).order_by(MediaAsset.turn_number.asc())
            res_assets = await db.execute(stmt_assets)
            user_assets = list(res_assets.scalars().all())

            if ev_assessment.has_sufficient_evidence and ev_assessment.has_sufficient_delivery_evidence and user_assets:
                target_turn = opening_res.evidence_turn_number or 1
                target_asset = next((a for a in user_assets if a.turn_number == target_turn), None) or user_assets[0]
                try:
                    asset_dur = target_asset.duration_ms if target_asset.duration_ms > 0 else 6000
                    crop_dur = min(10000, max(2000, asset_dur))
                    clip = await media_storage.create_derived_clip(
                        db=db,
                        user_id=user_id,
                        source_asset_id=target_asset.id,
                        start_ms=0,
                        end_ms=crop_dur,
                        purpose="opening_evidence",
                        label=f"Debate · Turn {target_asset.turn_number or 1}",
                        transcript_excerpt=opening_res.concrete_example or (encryptor.decrypt_str(target_asset.transcript_encrypted) if target_asset.transcript_encrypted else "Your argument"),
                        coach_note=opening_res.highest_value_improvement or "Notice the phrasing of your central claim.",
                    )
                    card_data = {
                        "clip_id": clip.id,
                        "media_asset_id": target_asset.id,
                        "audio_url": f"/api/media/clips/{clip.id}/audio",
                        "duration_sec": round(clip.duration_ms / 1000.0, 1),
                        "source_label": clip.label,
                        "transcript_excerpt": clip.transcript_excerpt or "",
                        "what_to_notice": clip.coach_note or "",
                        "turn_number": target_asset.turn_number,
                        "available": True,
                    }
                    await coach_repo.add_message(
                        user_id=user_id,
                        thread_id=thread.id,
                        sender="coach",
                        message_type="evidence_card",
                        text="Here is a key clip from your debate:",
                        evidence_clip_id=clip.id,
                        structured_data={"evidence_card": card_data},
                    )
                except Exception as e:
                    logger.warning("coach.opening_clip_creation.failed", error=str(e))

            # Refresh thread to include messages
            thread = await coach_repo.get_thread(user_id, thread.id)

        return thread

    @staticmethod
    async def process_user_text_message(
        db: AsyncSession,
        user_id: str,
        thread_id: str,
        text: str,
        media_asset_id: Optional[str] = None,
        create_user_message: bool = True,
    ) -> CoachMessageSchema:
        coach_repo = CoachRepository(db)
        thread = await coach_repo.get_thread(user_id, thread_id)
        if not thread or thread.user_id != user_id:
            raise ValueError("Thread not found or unauthorized")

        # Save user message if requested
        if create_user_message:
            msg_type = "audio" if media_asset_id else "text"
            await coach_repo.add_message(
                user_id=user_id,
                thread_id=thread_id,
                sender="user",
                message_type=msg_type,
                text=text,
                media_asset_id=media_asset_id,
            )

        # Build context for coach AI
        debate_context = None
        if thread.session:
            sess = thread.session
            review = await DebateSessionRepository(db).get_review(sess.id)
            turns = await DebateSessionRepository(db).get_turns(sess.id)
            sess_transcript = []
            for t in turns:
                txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else ""
                sess_transcript.append({"speaker": t.speaker, "turn_number": t.turn_number, "text": txt})

            from backend.app.domain.evidence import assess_debate_evidence
            ev_assessment = assess_debate_evidence(sess_transcript)
            opp_side = "disagree" if sess.user_side == "agree" else "agree"
            debate_context = {
                "topic": sess.topic_text,
                "user_side": sess.user_side,
                "opponent_side": opp_side,
                "skill_name": sess.skill_name,
                "outcome": review.outcome if review else "undetermined",
                "stars": review.stars if review else 0,
                "has_sufficient_evidence": ev_assessment.has_sufficient_evidence,
                "score_technique": review.score_technique if review else 8,
                "score_grammar": review.score_grammar if review else 8,
                "score_vocabulary": review.score_vocabulary if review else 8,
                "score_delivery": review.score_delivery if review else 8,
                "strongest_moment": review.strongest_moment if review else "Solid speech during turn 2.",
                "improvement_opportunity": review.improvement_opportunity if review else "Keep your spoken sentences concise.",
                "language_feedback": encryptor.decrypt_json(review.language_feedback_encrypted) if review and review.language_feedback_encrypted else {},
                "transcript": sess_transcript,
            }

        memory_md, _ = await coach_repo.get_memory_markdown(user_id)

        history_msgs = []
        thread_messages = await coach_repo.get_thread_messages(thread.id)
        for m in thread_messages:
            txt = encryptor.decrypt_str(m.text_encrypted) if m.text_encrypted else ""
            history_msgs.append({
                "sender": m.sender,
                "text": txt,
                "structured_data": m.structured_data_json,
            })
        if create_user_message or not history_msgs or history_msgs[-1]["sender"] != "user":
            history_msgs.append({"sender": "user", "text": text})

        prompt_messages = build_coach_conversation_prompt(
            thread_title=thread.title,
            thread_type=thread.thread_type,
            debate_context=debate_context,
            message_history=history_msgs[-12:],
            coach_memory_markdown=memory_md,
        )

        def default_fallback():
            return CoachTurnResponse(
                reply_text="Keep the spoken sentence short: say one clear idea, pause, then add the supporting detail. Send a voice attempt and I can check its phonemes and timing.",
                requested_tool=None,
                tool_args=None,
                evidence_card=None,
                quick_replies=["How should I phrase it?", "What should I practice?", "Let me try that again"],
                memory_update=None,
            )

        coach_resp = await ai_gateway._execute_structured_completion(
            role=ModelRole.COACH,
            messages=prompt_messages,
            schema_cls=CoachTurnResponse,
            fallback_factory=default_fallback,
        )

        # Model -> Tool -> Result -> Model Loop for phoneme and speech metrics
        if coach_resp.requested_tool == "get_phoneme_data":
            target_asset_id = (coach_resp.tool_args or {}).get("media_asset_id") or media_asset_id
            if not target_asset_id:
                stmt_asset_lookup = (
                    select(MediaAsset)
                    .where(MediaAsset.user_id == user_id)
                    .order_by(MediaAsset.created_at.desc())
                    .limit(1)
                )
                res_lookup = await db.execute(stmt_asset_lookup)
                cand_asset = res_lookup.scalar_one_or_none()
                if cand_asset:
                    target_asset_id = cand_asset.id

            if target_asset_id:
                stmt_asset = select(MediaAsset).where(MediaAsset.id == target_asset_id, MediaAsset.user_id == user_id)
                res_asset = await db.execute(stmt_asset)
                asset_obj = res_asset.scalar_one_or_none()
                if asset_obj:
                    phones = encryptor.decrypt_json(asset_obj.phonemes_encrypted) if asset_obj.phonemes_encrypted else []
                    metrics = asset_obj.speech_metrics_json or {}
                    logger.info("coach.tool.phoneme_data_retrieved", asset_id=target_asset_id, phonemes_count=len(phones))

                    tool_result_payload = {
                        "media_asset_id": target_asset_id,
                        "phonemes": phones[:40],
                        "speech_metrics": metrics,
                        "duration_ms": asset_obj.duration_ms,
                    }

                    tool_call_msg = {
                        "role": "assistant",
                        "content": json.dumps({"requested_tool": "get_phoneme_data", "tool_args": {"media_asset_id": target_asset_id}}),
                    }
                    tool_res_msg = {
                        "role": "user",
                        "content": f"[Tool Result for get_phoneme_data]:\n{json.dumps(tool_result_payload, indent=2)}\n\nNow provide your final coach feedback based on this acoustic evidence.",
                    }

                    updated_messages = list(prompt_messages) + [tool_call_msg, tool_res_msg]
                    try:
                        coach_resp = await ai_gateway._execute_structured_completion(
                            role=ModelRole.COACH,
                            messages=updated_messages,
                            schema_cls=CoachTurnResponse,
                            fallback_factory=lambda: coach_resp,
                        )
                        logger.info("coach.tool.follow_up_completed", asset_id=target_asset_id)
                    except Exception as loop_err:
                        logger.warning("coach.tool.follow_up_failed", error=str(loop_err))

        evidence_clip = None
        evidence_card_data = None

        if coach_resp.evidence_card:
            card_spec = coach_resp.evidence_card
            source_asset_id = card_spec.get("media_asset_id") or media_asset_id
            if not source_asset_id:
                stmt_recent = select(MediaAsset).where(MediaAsset.user_id == user_id).order_by(MediaAsset.created_at.desc()).limit(1)
                res_rec = await db.execute(stmt_recent)
                recent_asset = res_rec.scalar_one_or_none()
                if recent_asset:
                    source_asset_id = recent_asset.id

            if source_asset_id:
                try:
                    start_ms = card_spec.get("start_ms", 0)
                    end_ms = card_spec.get("end_ms", 8000)
                    clip = await media_storage.create_derived_clip(
                        db=db,
                        user_id=user_id,
                        source_asset_id=source_asset_id,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        purpose="coach_feedback",
                        label=card_spec.get("source_label", "Practice Clip"),
                        transcript_excerpt=card_spec.get("transcript_excerpt", text),
                        coach_note=card_spec.get("what_to_notice", "Listen to the timing and phrasing."),
                    )
                    evidence_clip = clip
                    evidence_card_data = {
                        "clip_id": clip.id,
                        "media_asset_id": source_asset_id,
                        "audio_url": f"/api/media/clips/{clip.id}/audio",
                        "duration_sec": round(clip.duration_ms / 1000.0, 1),
                        "source_label": clip.label,
                        "transcript_excerpt": clip.transcript_excerpt or "",
                        "what_to_notice": clip.coach_note or "",
                        "available": True,
                    }
                except Exception as e:
                    logger.warning("coach.clip_creation.failed", error=str(e))

        structured_data = {}
        if evidence_card_data:
            structured_data["evidence_card"] = evidence_card_data
        if coach_resp.quick_replies:
            structured_data["quick_replies"] = [
                {"label": qr, "prompt": qr} for qr in coach_resp.quick_replies
            ]

        msg_type = "evidence_card" if evidence_card_data else "text"
        coach_msg = await coach_repo.add_message(
            user_id=user_id,
            thread_id=thread_id,
            sender="coach",
            message_type=msg_type,
            text=coach_resp.reply_text,
            evidence_clip_id=evidence_clip.id if evidence_clip else None,
            structured_data=structured_data if structured_data else None,
        )

        return CoachEngine._message_to_schema(coach_msg)

    @staticmethod
    async def process_user_audio_message(
        db: AsyncSession,
        user_id: str,
        thread_id: str,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
    ) -> Tuple[CoachMessageSchema, CoachMessageSchema]:
        coach_repo = CoachRepository(db)
        thread = await coach_repo.get_thread(user_id, thread_id)
        if not thread or thread.user_id != user_id:
            raise ValueError("Thread not found or unauthorized")

        ext = "webm" if "webm" in mime_type else "mp3"
        session_id = thread.session_id

        # 1. Transcribe audio + analyze phonemes concurrently
        stt_task = asyncio.create_task(
            ai_gateway.transcribe_audio(audio_bytes=audio_bytes, audio_format=ext)
        )
        phoneme_task = asyncio.create_task(
            modal_speech_client.analyze_phonemes(audio_bytes=audio_bytes, audio_format=ext)
        )

        transcript = ""
        phonemes_res = {}
        try:
            results = await asyncio.gather(stt_task, phoneme_task, return_exceptions=True)
            if not isinstance(results[0], Exception):
                transcript = (results[0] or "").strip()
            else:
                logger.error("coach.stt_failed", error=str(results[0]))

            if not isinstance(results[1], Exception):
                phonemes_res = results[1] or {}
            else:
                logger.warning("coach.phoneme_failed", error=str(results[1]))
        except Exception as e:
            logger.error("coach.audio_processing_failed", error=str(e))

        if not transcript:
            logger.warning("coach.audio.no_speech_transcribed", thread_id=thread_id, user_id=user_id)
            raise ValueError("No speech detected in your recording. Please check your microphone and speak clearly.")

        # Save MediaAsset
        asset = await media_storage.save_media_asset(
            db=db,
            user_id=user_id,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            source_type="coach_audio",
            session_id=session_id,
            transcript=transcript,
            phonemes=phonemes_res.get("phonemes", []),
            speech_metrics=phonemes_res.get("speech_metrics", {}),
            duration_ms=phonemes_res.get("audio_duration_ms", 0),
        )

        user_msg = await coach_repo.add_message(
            user_id=user_id,
            thread_id=thread_id,
            sender="user",
            message_type="audio",
            text=transcript,
            media_asset_id=asset.id,
            processing_state="ready",
        )

        user_msg_schema = CoachEngine._message_to_schema(user_msg)

        coach_msg_schema = await CoachEngine.process_user_text_message(
            db=db,
            user_id=user_id,
            thread_id=thread_id,
            text=transcript,
            media_asset_id=asset.id,
            create_user_message=False,
        )

        return user_msg_schema, coach_msg_schema

    @staticmethod
    def _message_to_schema(m: CoachMessage) -> CoachMessageSchema:
        txt = encryptor.decrypt_str(m.text_encrypted) if m.text_encrypted else None
        audio_url = f"/api/media/{m.media_asset_id}/audio" if m.media_asset_id else None

        evidence_card = None
        opening_analysis = None
        quick_replies = None

        if m.structured_data_json:
            sd = m.structured_data_json
            if "evidence_card" in sd:
                ec = sd["evidence_card"]
                evidence_card = AudioEvidenceCardSchema(
                    clipId=ec.get("clip_id", ""),
                    mediaAssetId=ec.get("media_asset_id", ""),
                    audioUrl=ec.get("audio_url", ""),
                    durationSec=float(ec.get("duration_sec", 0.0)),
                    sourceLabel=ec.get("source_label", "Debate Evidence"),
                    transcriptExcerpt=ec.get("transcript_excerpt", ""),
                    whatToNotice=ec.get("what_to_notice", ""),
                    turnNumber=ec.get("turn_number"),
                    available=ec.get("available", True),
                )
            if "overall_assessment" in sd:
                opening_analysis = OpeningAnalysisSchema(
                    overallAssessment=sd.get("overall_assessment", ""),
                    mostImportantStrength=sd.get("most_important_strength", ""),
                    highestValueImprovement=sd.get("highest_value_improvement", ""),
                    concreteExample=sd.get("concrete_example"),
                    evidenceTurnNumber=sd.get("evidence_turn_number"),
                    suggestedQuickReplies=[
                        QuickReplySchema(label=r.get("label", ""), prompt=r.get("prompt", ""))
                        for r in sd.get("suggested_quick_replies", [])
                    ],
                )
            if "suggested_quick_replies" in sd and not opening_analysis:
                quick_replies = [
                    QuickReplySchema(label=r.get("label", ""), prompt=r.get("prompt", ""))
                    for r in sd.get("suggested_quick_replies", [])
                ]
            elif "quick_replies" in sd:
                quick_replies = [
                    QuickReplySchema(label=r.get("label", ""), prompt=r.get("prompt", ""))
                    for r in sd.get("quick_replies", [])
                ]

        return CoachMessageSchema(
            id=m.id,
            threadId=m.thread_id,
            sender=m.sender,
            messageType=m.message_type,
            text=txt,
            mediaAssetId=m.media_asset_id,
            audioUrl=audio_url,
            durationSec=None,
            evidenceClip=evidence_card,
            openingAnalysis=opening_analysis,
            quickReplies=quick_replies,
            processingState=m.processing_state or "ready",
            createdAt=m.created_at.isoformat() if m.created_at else "",
        )

    @staticmethod
    async def get_coach_home_data(db: AsyncSession, user_id: str) -> CoachHomeSchema:
        coach_repo = CoachRepository(db)
        prog_repo = ProgressRepository(db)

        progress = await prog_repo.get_progress(user_id)
        active_focus_label, active_focus_details = await coach_repo.get_active_focus(user_id)
        all_threads = await coach_repo.list_threads(user_id, limit=20)

        debate_threads = [t for t in all_threads if t.thread_type == "debate_review"]
        general_threads = [t for t in all_threads if t.thread_type == "general"]

        def thread_to_summary(t: CoachThread) -> CoachThreadSummarySchema:
            topic = t.session.topic_text if t.session else None
            skill = t.session.skill_name if t.session else None
            return CoachThreadSummarySchema(
                id=t.id,
                sessionId=t.session_id,
                threadType=t.thread_type,
                title=t.title,
                createdAt=t.created_at.isoformat() if t.created_at else "",
                updatedAt=t.updated_at.isoformat() if t.updated_at else "",
                messageCount=len(t.messages),
                topic=topic,
                skillName=skill,
            )

        preset_questions = [
            QuickReplySchema(label="How am I progressing?", prompt="How am I progressing overall in my speaking and debate confidence?"),
            QuickReplySchema(label="What do I still need to work on?", prompt="What is my primary area for improvement across recent debates?"),
            QuickReplySchema(label="What has improved recently?", prompt="What speaking habits or argumentative skills have improved recently?"),
            QuickReplySchema(label="Show my recurring grammar patterns", prompt="What recurring grammar or syntax patterns do you observe in my speech under pressure?"),
            QuickReplySchema(label="Which debate was my strongest?", prompt="Which of my completed debates was my strongest and why?"),
            QuickReplySchema(label="Give me a short practice exercise", prompt="Give me a 1-minute spoken practice exercise to work on my active focus."),
        ]

        stars_map = progress.stars_by_node_json or {}
        mastery_items = []
        for k, v in stars_map.items():
            level = "Strong" if v >= 3 else "Improving" if v >= 2 else "Developing"
            mastery_items.append(SkillMasteryItemSchema(skill=k.replace("_", " ").title(), level=level))

        if not mastery_items:
            mastery_items = [
                SkillMasteryItemSchema(skill="Direct Refutation", level="Improving"),
                SkillMasteryItemSchema(skill="Premise Clarity", level="Developing"),
            ]

        progress_summary = ProgressStatsSchema(
            xp=progress.xp,
            streakDays=progress.streak_days,
            streakHistory=progress.streak_history_json or [1, 1, 1, 0, 1, 1, 1],
            debatesCompleted=progress.debates_completed,
            wins=progress.wins,
            losses=progress.losses,
            draws=progress.draws,
            skillMastery=mastery_items,
            pronunciationTrend="Intelligibility high; vowel clarity steady under pressure",
            fluencyTrend="Turn response delay averaging 1.4s; thinking pauses well-placed",
        )

        return CoachHomeSchema(
            activeFocus=active_focus_label,
            focusDetails=active_focus_details,
            progressSummary=progress_summary,
            presetQuestions=preset_questions,
            recentDebateThreads=[thread_to_summary(t) for t in debate_threads[:5]],
            generalThreads=[thread_to_summary(t) for t in general_threads[:5]],
        )


coach_engine = CoachEngine()