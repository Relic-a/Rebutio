import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.domain.curriculum import get_skill
from backend.app.domain.events import session_events
from backend.app.domain.topics import TopicInventoryService
from backend.app.models.db import DebateSession, User
from backend.app.models.schemas import (
    DebateReviewSchema,
    DebateTurnSchema,
    DetailFeedbackSchema,
    FluencyFeedbackSchema,
    LanguageFeedbackSchema,
    PronunciationPatternSchema,
    StarAssessmentSchema,
    SubmitTurnResponseSchema,
)
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    ProgressRepository,
    SpeechProfileRepository,
    UserRepository,
)
from backend.app.prompts.debate_opponent import build_opponent_prompt
from backend.app.prompts.debate_reviewer import build_debate_reviewer_prompt
from backend.app.prompts.final_patch import build_final_patch_prompt
from backend.app.prompts.language_analysis import build_language_analysis_prompt
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.modal.client import modal_speech_client
from backend.app.services.privacy.encryption import encryptor
from backend.app.services.tts.cache import tts_cache

logger = logging.getLogger("rebutio.orchestration")

_finalizing_sessions: Set[str] = set()
_finalizing_lock = asyncio.Lock()


class DebateOrchestrator:
    @staticmethod
    async def process_user_turn(
        db: AsyncSession,
        session: DebateSession,
        user: User,
        audio_bytes: Optional[bytes] = None,
        transcript: Optional[str] = None,
        audio_format: str = "webm",
        client_response_delay_ms: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> SubmitTurnResponseSchema:
        session_repo = DebateSessionRepository(db)
        turn_num = session.current_turn
        total_turns = session.total_user_turns
        session_id = session.id
        user_id = user.id

        await session_events.emit(session_id, "user.turn_submitted", {"turnNumber": turn_num})
        await session_events.emit(session_id, "opponent.thinking", {"turnNumber": turn_num})

        # -------------------------------------------------------------------
        # 1. Immediate Fan-Out: Branch 1 (MAI) & Branch 2 (Modal)
        # -------------------------------------------------------------------
        mai_task = None
        modal_task = None

        if audio_bytes and len(audio_bytes) > 0:
            mai_task = asyncio.create_task(
                ai_gateway.transcribe_audio(audio_bytes=audio_bytes, audio_format=audio_format)
            )
            modal_task = asyncio.create_task(
                modal_speech_client.analyze_phonemes(
                    audio_bytes=audio_bytes,
                    audio_format=audio_format,
                    client_response_delay_ms=client_response_delay_ms,
                )
            )
        else:
            user_transcript = transcript or "I maintain my position based on the evidence presented."

        if mai_task is not None:
            try:
                user_transcript = await mai_task
                if not user_transcript and transcript:
                    user_transcript = transcript
                elif not user_transcript:
                    user_transcript = "I maintain my position on this issue."
            except Exception as e:
                logger.warning(f"MAI STT task failed: {e}")
                user_transcript = transcript or "I maintain my position on this issue."

        user_turn_record = await session_repo.save_turn(
            session_id=session_id,
            turn_number=turn_num,
            speaker="user",
            text=user_transcript,
            audio_available=bool(audio_bytes),
            duration_sec=0.0,
            client_response_delay_ms=client_response_delay_ms,
            idempotency_key=f"{idempotency_key}:user" if idempotency_key else None,
        )

        if modal_task is not None:
            asyncio.create_task(
                DebateOrchestrator._save_turn_evidence_background(
                    session_id=session_id,
                    turn_number=turn_num,
                    modal_task=modal_task,
                )
            )

        # -------------------------------------------------------------------
        # 2. Debate Critical Path: DeepSeek Opponent -> Gemini TTS
        # -------------------------------------------------------------------
        refreshed_session = await session_repo.get_session(session_id)
        turn_history = []
        for t in (refreshed_session.turns if refreshed_session else []):
            txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else None
            turn_history.append({"speaker": t.speaker, "text": txt or ""})

        prefs = UserRepository(db).get_preferences(user) or {}
        intensity = prefs.get("intensity", "balanced")
        opp_side = "disagree" if session.user_side == "agree" else "agree"

        opponent_messages = build_opponent_prompt(
            topic=session.topic_text,
            opponent_side=opp_side,
            user_side=session.user_side,
            skill_name=session.skill_name,
            difficulty=session.difficulty,
            intensity=intensity,
            turn_history=turn_history,
            current_turn_number=turn_num,
            total_turns=total_turns,
        )

        opponent_text = await ai_gateway.generate_debate_response(
            messages=opponent_messages,
            current_turn=turn_num,
        )

        tts_task = asyncio.create_task(
            ai_gateway.synthesize_speech(text=opponent_text, voice=settings.REBUTIO_TTS_VOICE)
        )

        opponent_turn_record = await session_repo.save_turn(
            session_id=session_id,
            turn_number=turn_num,
            speaker="opponent",
            text=opponent_text,
            audio_available=True,
            duration_sec=0.0,
            idempotency_key=f"{idempotency_key}:opponent" if idempotency_key else None,
        )

        try:
            audio_bytes_tts = await tts_task
            if audio_bytes_tts:
                tts_cache.put(session_id, opponent_turn_record.id, audio_bytes_tts)
        except Exception as e:
            logger.warning(f"TTS synthesis failed: {e}")

        # -------------------------------------------------------------------
        # 3. Penultimate Turn Optimization: Launch Main Luna in Background
        # -------------------------------------------------------------------
        is_penultimate = (turn_num == total_turns - 1)
        if is_penultimate and total_turns > 1:
            asyncio.create_task(
                DebateOrchestrator._run_pre_final_luna_analysis(
                    session_id=session_id,
                    user_id=user_id,
                    topic=session.topic_text,
                    skill_name=session.skill_name,
                    difficulty=session.difficulty,
                )
            )

        is_finished = turn_num >= total_turns
        next_turn = min(turn_num + 1, total_turns)

        await session_repo.update_current_turn(
            session_id=session_id,
            next_turn_number=next_turn,
            status="finished" if is_finished else "active",
        )

        user_turn_schema = DebateTurnSchema(
            id=user_turn_record.id,
            speaker="user",
            text=user_transcript,
            playback={"available": bool(audio_bytes)},
        )

        opponent_turn_schema = DebateTurnSchema(
            id=opponent_turn_record.id,
            speaker="opponent",
            text=opponent_text,
            playback={
                "available": True,
                "audioUrl": f"/api/sessions/{session_id}/turns/{opponent_turn_record.id}/audio",
            },
        )

        await session_events.emit(
            session_id,
            "opponent.turn_ready",
            {
                "userTurn": user_turn_schema.model_dump(),
                "opponentTurn": opponent_turn_schema.model_dump(),
                "nextTurn": next_turn,
                "finished": is_finished,
            },
        )

        if is_finished:
            await session_events.emit(session_id, "session.finished", {"sessionId": session_id})
            asyncio.create_task(DebateOrchestrator.finalize_debate_review(session_id, user_id))

        return SubmitTurnResponseSchema(
            userTurn=user_turn_schema,
            opponentTurn=opponent_turn_schema,
            nextUserTurnNumber=next_turn,
            finished=is_finished,
        )

    @staticmethod
    async def _save_turn_evidence_background(
        session_id: str,
        turn_number: int,
        modal_task: asyncio.Task,
    ):
        try:
            evidence = await modal_task
            from backend.app.persistence.db import async_session_factory
            async with async_session_factory() as db:
                repo = DebateSessionRepository(db)
                await repo.save_temporary_evidence(
                    session_id=session_id,
                    turn_number=turn_number,
                    evidence_dict=evidence,
                )
        except Exception as e:
            logger.warning(f"Failed to save turn {turn_number} temporary phoneme evidence: {e}")

    @staticmethod
    async def _run_pre_final_luna_analysis(
        session_id: str,
        user_id: str,
        topic: str,
        skill_name: str,
        difficulty: str,
    ):
        from backend.app.persistence.db import async_session_factory
        try:
            await asyncio.sleep(0.5)

            async with async_session_factory() as db:
                sess_repo = DebateSessionRepository(db)
                speech_repo = SpeechProfileRepository(db)

                session = await sess_repo.get_session(session_id)
                if not session:
                    return

                all_evidence = await sess_repo.get_all_temporary_evidence(session_id)
                speech_prof = await speech_repo.get_profile(user_id)

                turns_data = []
                for turn in session.turns:
                    if turn.speaker == "user":
                        txt = encryptor.decrypt_str(turn.text_encrypted) if turn.text_encrypted else ""
                        matching_ev = next((e for e in all_evidence if e.get("turn_number") == turn.turn_number), {})
                        turns_data.append({
                            "turn_number": turn.turn_number,
                            "transcript": txt,
                            "client_response_delay_ms": turn.client_response_delay_ms,
                            "phoneme_evidence": matching_ev.get("phonemes", []),
                            "speech_metrics": matching_ev.get("speech_metrics", {}),
                        })

                if not turns_data:
                    return

                messages = build_language_analysis_prompt(
                    topic=topic,
                    target_skill=skill_name,
                    difficulty=difficulty,
                    turns_evidence=turns_data,
                    speech_profile=speech_prof,
                )

                pre_final_result = await ai_gateway.analyze_language(messages)
                await sess_repo.save_pre_final_analysis(session_id, pre_final_result.model_dump())
                logger.info(f"Pre-final Luna analysis completed for session {session_id}")
        except Exception as e:
            logger.warning(f"Pre-final Luna analysis failed: {e}")

    @staticmethod
    async def finalize_debate_review(session_id: str, user_id: str) -> DebateReviewSchema:
        # Avoid concurrent duplicate review generations for the same session
        async with _finalizing_lock:
            if session_id in _finalizing_sessions:
                # Wait briefly for in-progress finalization
                for _ in range(30):
                    await asyncio.sleep(0.2)
                    if session_id not in _finalizing_sessions:
                        break
            _finalizing_sessions.add(session_id)

        try:
            await session_events.emit(session_id, "review.pending", {"sessionId": session_id})
            from backend.app.persistence.db import async_session_factory

            async with async_session_factory() as db:
                sess_repo = DebateSessionRepository(db)
                prog_repo = ProgressRepository(db)
                speech_repo = SpeechProfileRepository(db)
                user_repo = UserRepository(db)

                existing_review = await sess_repo.get_review(session_id)
                session = await sess_repo.get_session(session_id)
                if not session:
                    raise ValueError("Session not found")

                if existing_review:
                    return DebateOrchestrator._db_review_to_schema(existing_review, session_id, session.topic_text, session.skill_name)

                user = await user_repo.get_or_create_user(user_id)

                full_transcript = []
                for t in session.turns:
                    txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else ""
                    full_transcript.append({"speaker": t.speaker, "turn_number": t.turn_number, "text": txt})

                opp_side = "disagree" if session.user_side == "agree" else "agree"

                # Task A: Independent Debate Reviewer
                reviewer_messages = build_debate_reviewer_prompt(
                    topic=session.topic_text,
                    user_side=session.user_side,
                    opponent_side=opp_side,
                    skill_id=session.skill_id,
                    skill_name=session.skill_name,
                    difficulty=session.difficulty,
                    full_transcript=full_transcript,
                )
                reviewer_task = asyncio.create_task(ai_gateway.review_debate(reviewer_messages))

                # Task B: Final Language Patch
                pre_final = await sess_repo.get_pre_final_analysis(session_id)
                all_evidence = await sess_repo.get_all_temporary_evidence(session_id)

                final_turn_evidence = all_evidence[-1] if all_evidence else {}

                if pre_final:
                    patch_messages = build_final_patch_prompt(
                        pre_final_analysis=pre_final,
                        final_turn_evidence=final_turn_evidence,
                        topic=session.topic_text,
                        target_skill=session.skill_name,
                    )
                    patch_task = asyncio.create_task(ai_gateway.patch_final_language(patch_messages))
                else:
                    patch_messages = build_language_analysis_prompt(
                        topic=session.topic_text,
                        target_skill=session.skill_name,
                        difficulty=session.difficulty,
                        turns_evidence=[{"turn_number": i + 1, "evidence": ev} for i, ev in enumerate(all_evidence)],
                    )
                    patch_task = asyncio.create_task(ai_gateway.analyze_language(patch_messages))

                results = await asyncio.gather(reviewer_task, patch_task, return_exceptions=True)
                reviewer_res = results[0] if not isinstance(results[0], Exception) else None
                patch_res = results[1] if not isinstance(results[1], Exception) else None

                outcome = reviewer_res.outcome if reviewer_res else "undetermined"
                skill_demo = reviewer_res.target_skill_demonstrated if reviewer_res else True
                mastery_stars = reviewer_res.mastery_stars if reviewer_res else 1
                final_stars = max(1, min(3, mastery_stars))

                arg_feedback = {
                    "strength": reviewer_res.argument_strength if reviewer_res else "You held your ground clearly throughout the exchange.",
                    "improvement": reviewer_res.argument_improvement if reviewer_res else "Push more aggressively on their core assumption next time.",
                    "insight": reviewer_res.strategic_insight if reviewer_res else None,
                }

                skill_assessment = {
                    "targetSkill": session.skill_id,
                    "demonstrated": skill_demo,
                    "summary": reviewer_res.skill_summary if reviewer_res else "Completed all turns under the target skill focus.",
                }

                lang_feedback = None
                if patch_res:
                    pron_list = [
                        PronunciationPatternSchema(
                            sound=p.sound,
                            heardIn=p.heard_in,
                            note=p.note,
                            occurrences=p.occurrences,
                            severity=p.severity,
                        )
                        for p in patch_res.pronunciation_findings
                        if p.reportable
                    ]

                    lang_feedback = {
                        "pronunciation": [p.model_dump() for p in pron_list] if pron_list else [],
                        "fluency": patch_res.fluency_finding.model_dump() if patch_res.fluency_finding else None,
                        "grammar": patch_res.grammar_finding.model_dump() if patch_res.grammar_finding else None,
                        "vocabulary": patch_res.vocabulary_finding.model_dump() if patch_res.vocabulary_finding else None,
                        "clarity": patch_res.clarity_finding.model_dump() if patch_res.clarity_finding else None,
                    }

                xp_earned = 100 + (final_stars * 20)

                await prog_repo.record_debate_completion(
                    user_id=user_id,
                    skill_id=session.skill_id,
                    stars_earned=final_stars,
                    xp_earned=xp_earned,
                    outcome=outcome,
                    streak_extended=True,
                )

                if patch_res:
                    profile_update = {
                        "last_updated": datetime.date.today().isoformat(),
                        "recurring_pronunciation": [p.model_dump() for p in patch_res.pronunciation_findings if p.reportable],
                        "fluency_summary": patch_res.fluency_finding.summary if patch_res.fluency_finding else "",
                        "grammar_patterns": [patch_res.grammar_finding.recurring_pattern] if patch_res.grammar_finding and patch_res.grammar_finding.recurring_pattern else [],
                        "vocabulary_examples": patch_res.vocabulary_finding.examples if patch_res.vocabulary_finding else [],
                    }
                    await speech_repo.save_profile(user_id, profile_update)

                db_review = await sess_repo.save_review(
                    session_id=session_id,
                    user_id=user_id,
                    outcome=outcome,
                    stars=final_stars,
                    completed=True,
                    skill_demonstrated=skill_demo,
                    mastery_note=reviewer_res.mastery_note if reviewer_res else None,
                    skill_assessment=skill_assessment,
                    argument_feedback=arg_feedback,
                    language_feedback=lang_feedback,
                    xp_earned=xp_earned,
                    streak_extended=True,
                    next_level_unlocked=(final_stars >= 1),
                )

                await sess_repo.cleanup_finished_session_privacy(
                    session_id=session_id,
                    save_transcripts=user.save_transcripts,
                )

                schema_review = DebateOrchestrator._db_review_to_schema(
                    db_review,
                    session_id,
                    session.topic_text,
                    session.skill_name,
                )

                await session_events.emit(session_id, "review.ready", schema_review.model_dump())
                return schema_review
        finally:
            async with _finalizing_lock:
                _finalizing_sessions.discard(session_id)

    @staticmethod
    def _db_review_to_schema(
        r,
        session_id: str,
        topic: str,
        skill_name: str,
    ) -> DebateReviewSchema:
        lang_feedback = encryptor.decrypt_json(r.language_feedback_encrypted) if r.language_feedback_encrypted else None

        return DebateReviewSchema(
            outcome=r.outcome,
            stars=StarAssessmentSchema(
                stars=r.stars,
                completed=r.completed,
                skillDemonstrated=r.skill_demonstrated,
                masteryNote=r.mastery_note,
            ),
            skillAssessment=r.skill_assessment_json,
            argumentFeedback=r.argument_feedback_json,
            languageFeedback=lang_feedback,
            xpEarned=r.xp_earned,
            streakExtended=r.streak_extended,
            nextLevelUnlocked=r.next_level_unlocked,
            topic=topic,
            skillName=skill_name,
        )
