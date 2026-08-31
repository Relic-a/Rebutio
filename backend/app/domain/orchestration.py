import asyncio
import datetime
import time
import uuid
from typing import Any, Dict, List, Optional, Set
from fastapi import HTTPException
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
from backend.app.observability.context import bind_context
from backend.app.observability.logging import get_logger
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

logger = get_logger("rebutio.orchestration")

_session_locks: Dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()


async def get_session_lock(session_id: str) -> asyncio.Lock:
    async with _global_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = asyncio.Lock()
        return _session_locks[session_id]


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
        session_lock = await get_session_lock(session.id)
        async with session_lock:
            session_repo = DebateSessionRepository(db)
            fresh_session = await session_repo.get_session(session.id)
            if not fresh_session:
                raise ValueError("Session not found")

            turn_num = fresh_session.current_turn
            total_turns = fresh_session.total_user_turns
            session_id = fresh_session.id
            user_id = user.id

            bind_context(session_id=session_id, turn_id=turn_num, user_id=user_id)

            logger.info(
                "debate.turn.received",
                turn_number=turn_num,
                total_turns=total_turns,
                has_audio=bool(audio_bytes),
                has_transcript=bool(transcript),
                audio_format=audio_format,
                client_response_delay_ms=client_response_delay_ms,
            )

            # State Transition: user_turn_submitted -> opponent_thinking
            logger.info(
                "session.state_changed",
                from_state="user_turn_submitted",
                to_state="opponent_thinking",
                turn_id=turn_num,
            )
            await session_events.emit(session_id, "user.turn_submitted", {"turnNumber": turn_num})
            await session_events.emit(session_id, "opponent.thinking", {"turnNumber": turn_num})

            # -------------------------------------------------------------------
            # 1. Immediate Fan-Out: Branch 1 (MAI STT) & Branch 2 (Modal Phonemes)
            # -------------------------------------------------------------------
            mai_task = None
            modal_task = None

            if audio_bytes and len(audio_bytes) > 0:
                mai_task = asyncio.create_task(
                    ai_gateway.transcribe_audio(audio_bytes=audio_bytes, audio_format=audio_format)
                )
                logger.info("speech.phoneme_processing.dispatched", turn_number=turn_num)
                modal_task = asyncio.create_task(
                    modal_speech_client.analyze_phonemes(
                        audio_bytes=audio_bytes,
                        audio_format=audio_format,
                        client_response_delay_ms=client_response_delay_ms,
                    )
                )
            else:
                user_transcript = (transcript or "").strip()

            if mai_task is not None:
                try:
                    user_transcript = await mai_task
                except Exception as e:
                    logger.error("speech.transcription.failed", error=str(e))
                    if transcript and transcript.strip():
                        user_transcript = transcript.strip()
                    else:
                        raise HTTPException(
                            status_code=502,
                            detail="Transcription service is temporarily unavailable. Please try again or switch to text input.",
                        ) from e

            # Clean and validate transcript text
            clean_transcript = (user_transcript or "").strip()
            if not clean_transcript and transcript and transcript.strip():
                clean_transcript = transcript.strip()

            if not clean_transcript:
                logger.warning("speech.transcription.no_speech_detected", turn_number=turn_num, session_id=session_id)
                raise HTTPException(
                    status_code=422,
                    detail="No speech detected in your recording. Please check your microphone, check your input volume, and try speaking again.",
                )

            user_transcript = clean_transcript

            # Save user turn record
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
            logger.info("debate.turn.committed", turn_number=turn_num, speaker="user", turn_id=user_turn_record.id)

            # Is this the final user turn?
            is_final_turn = (turn_num >= total_turns)

            if not is_final_turn:
                # -------------------------------------------------------------------
                # Non-final turn (turns 1 .. N-1):
                # Modal task runs in background and saves evidence.
                # Debate critical path: DeepSeek opponent -> TTS.
                # -------------------------------------------------------------------
                if modal_task is not None:
                    asyncio.create_task(
                        DebateOrchestrator._save_turn_evidence_background(
                            session_id=session_id,
                            turn_number=turn_num,
                            modal_task=modal_task,
                        )
                    )

                refreshed_session = await session_repo.get_session(session_id)
                turn_history = []
                for t in (refreshed_session.turns if refreshed_session else []):
                    txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else None
                    turn_history.append({"speaker": t.speaker, "text": txt or ""})

                prefs = UserRepository(db).get_preferences(user) or {}
                intensity = prefs.get("intensity", "balanced")
                opp_side = "disagree" if fresh_session.user_side == "agree" else "agree"

                # Penultimate turn check: is this turn N - 1?
                is_penultimate = (turn_num == total_turns - 1)

                opponent_messages = build_opponent_prompt(
                    topic=fresh_session.topic_text,
                    opponent_side=opp_side,
                    user_side=fresh_session.user_side,
                    skill_name=fresh_session.skill_name,
                    difficulty=fresh_session.difficulty,
                    intensity=intensity,
                    turn_history=turn_history,
                    current_turn_number=turn_num,
                    total_turns=total_turns,
                )

                # Opponent generation
                logger.info(
                    "debate.opponent_generation.started",
                    turn_number=turn_num,
                    opponent_side=opp_side,
                    intensity=intensity,
                )
                t_opp_start = time.perf_counter()
                try:
                    opponent_text = await ai_gateway.generate_debate_response(
                        messages=opponent_messages,
                        current_turn=turn_num,
                    )
                    opp_dur_ms = round((time.perf_counter() - t_opp_start) * 1000, 2)
                    logger.info("debate.opponent_generation.completed", turn_number=turn_num, duration_ms=opp_dur_ms)
                except Exception as e:
                    opp_dur_ms = round((time.perf_counter() - t_opp_start) * 1000, 2)
                    logger.error("debate.opponent_generation.failed", turn_number=turn_num, duration_ms=opp_dur_ms, exception_type=e.__class__.__name__)
                    raise

                # Synthesize TTS concurrently
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
                logger.info("debate.turn.committed", turn_number=turn_num, speaker="opponent", turn_id=opponent_turn_record.id)

                # Penultimate turn optimization: Launch Main Luna in background over turns 1..N-1
                if is_penultimate and total_turns > 1:
                    asyncio.create_task(
                        DebateOrchestrator._run_pre_final_luna_analysis(
                            session_id=session_id,
                            user_id=user_id,
                            topic=fresh_session.topic_text,
                            skill_name=fresh_session.skill_name,
                            difficulty=fresh_session.difficulty,
                        )
                    )

                # Await TTS for playback cache
                try:
                    audio_bytes_tts = await tts_task
                    if audio_bytes_tts and len(audio_bytes_tts) > 0:
                        tts_cache.put(session_id, opponent_turn_record.id, audio_bytes_tts)
                except Exception as e:
                    logger.warning("debate.tts.failed", error=str(e))

                next_turn = turn_num + 1
                await session_repo.update_current_turn(
                    session_id=session_id,
                    next_turn_number=next_turn,
                    status="active",
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
                        "available": bool(tts_cache.get(session_id, opponent_turn_record.id)),
                        "audioUrl": f"/api/sessions/{session_id}/turns/{opponent_turn_record.id}/audio",
                    },
                )

                # State Transition: opponent_thinking -> opponent_ready
                logger.info(
                    "session.state_changed",
                    from_state="opponent_thinking",
                    to_state="opponent_ready",
                    turn_id=turn_num,
                    next_turn=next_turn,
                )

                await session_events.emit(
                    session_id,
                    "opponent.turn_ready",
                    {
                        "userTurn": user_turn_schema.model_dump(),
                        "opponentTurn": opponent_turn_schema.model_dump(),
                        "nextTurn": next_turn,
                        "finished": False,
                    },
                )

                return SubmitTurnResponseSchema(
                    userTurn=user_turn_schema,
                    opponentTurn=opponent_turn_schema,
                    nextUserTurnNumber=next_turn,
                    finished=False,
                )

            else:
                # -------------------------------------------------------------------
                # Final user turn (turn N):
                # No opponent response is generated.
                # Await final Modal evidence (with bounded timeout), then finalize review.
                # -------------------------------------------------------------------
                if modal_task is not None:
                    try:
                        final_ev = await asyncio.wait_for(modal_task, timeout=8.0)
                        await session_repo.save_temporary_evidence(
                            session_id=session_id,
                            turn_number=turn_num,
                            evidence_dict=final_ev,
                        )
                        logger.info("speech.phoneme_processing.completed", turn_number=turn_num)
                    except Exception as e:
                        logger.warning("speech.phoneme_processing.timed_out", turn_number=turn_num, error=str(e))

                await session_repo.update_current_turn(
                    session_id=session_id,
                    next_turn_number=total_turns,
                    status="finished",
                )

                user_turn_schema = DebateTurnSchema(
                    id=user_turn_record.id,
                    speaker="user",
                    text=user_transcript,
                    playback={"available": bool(audio_bytes)},
                )

                logger.info(
                    "session.state_changed",
                    from_state="user_turn_submitted",
                    to_state="review_pending",
                    turn_id=turn_num,
                )

                # Emit finished event
                await session_events.emit(session_id, "session.finished", {"sessionId": session_id})

                # Launch review finalization in background
                asyncio.create_task(DebateOrchestrator.finalize_debate_review(session_id, user_id))

                return SubmitTurnResponseSchema(
                    userTurn=user_turn_schema,
                    opponentTurn=None,
                    nextUserTurnNumber=total_turns,
                    finished=True,
                )

    @staticmethod
    async def _save_turn_evidence_background(
        session_id: str,
        turn_number: int,
        modal_task: asyncio.Task,
    ):
        task_id = f"task-evidence-{session_id}-{turn_number}"
        t_start = time.perf_counter()
        logger.info(
            "background_task.started",
            task_type="save_turn_evidence",
            task_id=task_id,
            session_id=session_id,
            turn_number=turn_number,
        )
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
            dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.info(
                "background_task.completed",
                task_type="save_turn_evidence",
                task_id=task_id,
                session_id=session_id,
                turn_number=turn_number,
                duration_ms=dur_ms,
            )
        except Exception as e:
            dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.error(
                "background_task.failed",
                task_type="save_turn_evidence",
                task_id=task_id,
                session_id=session_id,
                turn_number=turn_number,
                duration_ms=dur_ms,
                exception_type=e.__class__.__name__,
            )

    @staticmethod
    async def _run_pre_final_luna_analysis(
        session_id: str,
        user_id: str,
        topic: str,
        skill_name: str,
        difficulty: str,
    ):
        task_id = f"task-preluna-{session_id}"
        t_start = time.perf_counter()
        logger.info(
            "background_task.started",
            task_type="pre_final_luna_analysis",
            task_id=task_id,
            session_id=session_id,
        )
        from backend.app.persistence.db import async_session_factory
        try:
            await asyncio.sleep(0.3)

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

                logger.info(
                    "language_analysis.started",
                    session_id=session_id,
                    target_skill=skill_name,
                    turns_analyzed_count=len(turns_data),
                )

                messages = build_language_analysis_prompt(
                    topic=topic,
                    target_skill=skill_name,
                    difficulty=difficulty,
                    turns_evidence=turns_data,
                    speech_profile=speech_prof,
                )

                pre_final_result = await ai_gateway.analyze_language(messages)
                await sess_repo.save_pre_final_analysis(session_id, pre_final_result.model_dump())
                logger.info("language_analysis.completed", session_id=session_id)

            dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.info(
                "background_task.completed",
                task_type="pre_final_luna_analysis",
                task_id=task_id,
                session_id=session_id,
                duration_ms=dur_ms,
            )
        except Exception as e:
            dur_ms = round((time.perf_counter() - t_start) * 1000, 2)
            logger.error(
                "background_task.failed",
                task_type="pre_final_luna_analysis",
                task_id=task_id,
                session_id=session_id,
                duration_ms=dur_ms,
                exception_type=e.__class__.__name__,
            )

    @staticmethod
    async def finalize_debate_review(session_id: str, user_id: str) -> DebateReviewSchema:
        session_lock = await get_session_lock(session_id)
        async with session_lock:
            bind_context(session_id=session_id, user_id=user_id)
            logger.info("debate_review.started", session_id=session_id)
            await session_events.emit(session_id, "review.pending", {"sessionId": session_id})
            from backend.app.persistence.db import async_session_factory

            t_review_start = time.perf_counter()
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
                    return DebateOrchestrator._db_review_to_schema(
                        existing_review, session_id, session.topic_text, session.skill_name
                    )

                user = await user_repo.get_or_create_user(user_id)

                full_transcript = []
                for t in session.turns:
                    txt = encryptor.decrypt_str(t.text_encrypted) if t.text_encrypted else ""
                    full_transcript.append({"speaker": t.speaker, "turn_number": t.turn_number, "text": txt})

                opp_side = "disagree" if session.user_side == "agree" else "agree"

                # Task A: Independent Debate Reviewer (does not need phonemes)
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

                # Task B: Final Language Patch (uses pre_final analysis + final turn evidence)
                pre_final = await sess_repo.get_pre_final_analysis(session_id)
                all_evidence = await sess_repo.get_all_temporary_evidence(session_id)
                final_turn_evidence = all_evidence[-1] if all_evidence else {}

                if pre_final:
                    logger.info("language_patch.started", session_id=session_id)
                    patch_messages = build_final_patch_prompt(
                        pre_final_analysis=pre_final,
                        final_turn_evidence=final_turn_evidence,
                        topic=session.topic_text,
                        target_skill=session.skill_name,
                    )
                    patch_task = asyncio.create_task(ai_gateway.patch_final_language(patch_messages))
                else:
                    logger.info("language_analysis.started", session_id=session_id)
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

                if isinstance(results[0], Exception):
                    logger.error("debate_review.task_a_failed", error=str(results[0]))
                if isinstance(results[1], Exception):
                    logger.error("debate_review.task_b_failed", error=str(results[1]))

                outcome = reviewer_res.outcome if reviewer_res else "undetermined"
                skill_demo = reviewer_res.target_skill_demonstrated if reviewer_res else False
                mastery_stars = reviewer_res.mastery_stars if reviewer_res else 1
                # Star 1 is guaranteed for completion! Mastery adds stars 2 & 3.
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

                # Record completion & star progression
                await prog_repo.record_debate_completion(
                    user_id=user_id,
                    skill_id=session.skill_id,
                    stars_earned=final_stars,
                    xp_earned=xp_earned,
                    outcome=outcome,
                    streak_extended=True,
                )
                logger.info(
                    "session.progress.updated",
                    skill_id=session.skill_id,
                    stars_earned=final_stars,
                    xp_earned=xp_earned,
                    outcome=outcome,
                )

                # Update compact persistent speech profile
                if patch_res:
                    profile_update = {
                        "last_updated": datetime.date.today().isoformat(),
                        "recurring_pronunciation": [p.model_dump() for p in patch_res.pronunciation_findings if p.reportable],
                        "fluency_summary": patch_res.fluency_finding.summary if patch_res.fluency_finding else "",
                        "grammar_patterns": [patch_res.grammar_finding.recurring_pattern] if patch_res.grammar_finding and patch_res.grammar_finding.recurring_pattern else [],
                        "vocabulary_examples": patch_res.vocabulary_finding.examples if patch_res.vocabulary_finding else [],
                    }
                    await speech_repo.save_profile(user_id, profile_update)

                # Save Review in DB
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

                # Privacy cleanup: delete temporary evidence, pre-final analysis, and transcripts if disabled
                await sess_repo.cleanup_finished_session_privacy(
                    session_id=session_id,
                    save_transcripts=user.save_transcripts,
                )

                # Background topic refill
                asyncio.create_task(TopicInventoryService._background_refill(user_id))

                schema_review = DebateOrchestrator._db_review_to_schema(
                    db_review,
                    session_id,
                    session.topic_text,
                    session.skill_name,
                )

                review_dur_ms = round((time.perf_counter() - t_review_start) * 1000, 2)
                logger.info(
                    "debate_review.completed",
                    session_id=session_id,
                    duration_ms=review_dur_ms,
                    stars=final_stars,
                    outcome=outcome,
                )
                logger.info(
                    "session.state_changed",
                    from_state="review_pending",
                    to_state="review_ready",
                    session_id=session_id,
                )
                logger.info("session.completed", session_id=session_id)

                await session_events.emit(session_id, "review.ready", schema_review.model_dump())
                return schema_review

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
