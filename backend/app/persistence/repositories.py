import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.db import (
    CoachMemory,
    CoachMessage,
    CoachThread,
    DebateReview,
    DebateSession,
    DebateTurn,
    DerivedAudioClip,
    LearningProgress,
    MediaAsset,
    ReviewFeedback,
    SpeechProfile,
    TemporaryTurnEvidence,
    TopicInventory,
    User,
    utcnow,
)
from backend.app.observability.logging import get_logger
from backend.app.services.privacy.encryption import encryptor

logger = get_logger("rebutio.persistence")

# ---------------------------------------------------------------------------
# Streak helpers (date-based, once-per-day semantics)
# ---------------------------------------------------------------------------

EMPTY_STREAK_HISTORY: List[int] = [0, 0, 0, 0, 0, 0, 0]


def _today_iso() -> str:
    return datetime.date.today().isoformat()


def _parse_iso_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def normalize_streak_history(history: Any) -> List[int]:
    """Coerce stored history into a 7-int list of 0/1, tolerating legacy data."""
    if not isinstance(history, list):
        return list(EMPTY_STREAK_HISTORY)
    cleaned = [1 if v else 0 for v in history[:7]]
    while len(cleaned) < 7:
        cleaned.insert(0, 0)
    return cleaned


def resolve_streak(
    current_streak_days: int,
    last_activity_date: Optional[str],
    history: Any,
    qualifies: bool,
    today_iso: Optional[str] = None,
) -> Tuple[int, List[int], Optional[str], bool]:
    """Apply once-per-day streak rules.

    Returns (new_streak_days, new_history, new_last_activity_date, actually_extended).
    - qualifies=False (insufficient evidence): nothing changes, extended=False.
    - Same-day repeat: no increment, extended=False, history today marked active.
    - Consecutive day (gap==1): +1, extended=True.
    - New user or broken streak (gap>=2 / no history): restart at 1, extended=True.
    """
    today = today_iso or _today_iso()
    hist = normalize_streak_history(history)

    if not qualifies:
        return current_streak_days or 0, hist, last_activity_date, False

    if last_activity_date == today:
        hist[-1] = 1
        return current_streak_days or 0, hist, last_activity_date, False

    last = _parse_iso_date(last_activity_date)
    if last is not None:
        try:
            gap = (datetime.date.fromisoformat(today) - last).days
        except (ValueError, TypeError):
            gap = 2
    else:
        gap = None

    if gap == 1:
        new_streak = (current_streak_days or 0) + 1
        new_hist = hist[1:] + [1]
        return new_streak, new_hist, today, True

    # New streak (first activity, or broken streak after a missed day)
    if gap is None:
        return 1, [0, 0, 0, 0, 0, 0, 1], today, True
    if gap is not None and gap >= 7:
        return 1, [0, 0, 0, 0, 0, 0, 1], today, True
    # gap between 2 and 6, or unparseable/negative: roll history forward by gap
    shift = gap if gap is not None and gap > 0 else 2
    shift = min(shift, 7)
    new_hist = (hist + [0] * 7)[shift:shift + 7]
    new_hist[-1] = 1
    return 1, new_hist, today, True

DEFAULT_STARTER_MEMORY = """# Rebutio Coach Memory

## User Preferences & Goals
- Focus: Structure arguments clearly, respond directly to counterpoints, maintain steady pacing under pressure.

## Historical Summary
- No historical debate summaries yet.

## Recent Debates
"""


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user(self, user_id: Optional[str] = None) -> User:
        if user_id:
            stmt = select(User).where(User.id == user_id).options(
                selectinload(User.progress),
                selectinload(User.speech_profile),
                selectinload(User.coach_memory),
            )
            res = await self.db.execute(stmt)
            user = res.scalar_one_or_none()
            if user:
                # Ensure CoachMemory exists
                if not user.coach_memory:
                    coach_mem = CoachMemory(
                        user_id=user.id,
                        memory_markdown_encrypted=encryptor.encrypt_str(DEFAULT_STARTER_MEMORY),
                        revision=1,
                    )
                    self.db.add(coach_mem)
                    await self.db.commit()
                    await self.db.refresh(user)
                return user

        new_user_id = user_id or str(uuid.uuid4())
        user = User(
            id=new_user_id,
            onboarded=False,
            preferences_encrypted=None,
            save_transcripts=False,
            captions_enabled=True,
        )
        self.db.add(user)
        await self.db.flush()

        progress = LearningProgress(
            user_id=new_user_id,
            xp=0,
            streak_days=0,
            streak_history_json=list(EMPTY_STREAK_HISTORY),
            debates_completed=0,
            wins=0,
            losses=0,
            draws=0,
            stars_by_node_json={},
            placement_completed=False,
            placement_skill_id=None,
        )
        self.db.add(progress)

        speech_prof = SpeechProfile(
            user_id=new_user_id,
            profile_encrypted=None,
        )
        self.db.add(speech_prof)

        coach_mem = CoachMemory(
            user_id=new_user_id,
            memory_markdown_encrypted=encryptor.encrypt_str(DEFAULT_STARTER_MEMORY),
            revision=1,
        )
        self.db.add(coach_mem)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_preferences(self, user_id: str, prefs_dict: dict, onboarded: bool = True) -> User:
        encrypted_prefs = encryptor.encrypt_json(prefs_dict)
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                preferences_encrypted=encrypted_prefs,
                onboarded=onboarded,
                updated_at=utcnow(),
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return await self.get_or_create_user(user_id)

    async def update_settings(
        self,
        user_id: str,
        save_transcripts: Optional[bool] = None,
        captions_enabled: Optional[bool] = None,
        intensity: Optional[str] = None,
    ) -> User:
        user = await self.get_or_create_user(user_id)
        values = {"updated_at": utcnow()}
        if save_transcripts is not None:
            values["save_transcripts"] = save_transcripts
        if captions_enabled is not None:
            values["captions_enabled"] = captions_enabled

        if intensity is not None:
            current_prefs = encryptor.decrypt_json(user.preferences_encrypted) or {}
            current_prefs["intensity"] = intensity
            values["preferences_encrypted"] = encryptor.encrypt_json(current_prefs)

        stmt = update(User).where(User.id == user_id).values(**values)
        await self.db.execute(stmt)
        await self.db.commit()
        return await self.get_or_create_user(user_id)

    def get_preferences(self, user: User) -> Optional[dict]:
        return encryptor.decrypt_json(user.preferences_encrypted)


class ProgressRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_progress(self, user_id: str) -> LearningProgress:
        stmt = select(LearningProgress).where(LearningProgress.user_id == user_id)
        res = await self.db.execute(stmt)
        progress = res.scalar_one_or_none()
        if not progress:
            progress = LearningProgress(
                user_id=user_id,
                xp=0,
                streak_days=0,
                streak_history_json=list(EMPTY_STREAK_HISTORY),
                debates_completed=0,
                wins=0,
                losses=0,
                draws=0,
                stars_by_node_json={},
                placement_completed=False,
                placement_skill_id=None,
            )
            self.db.add(progress)
            await self.db.commit()
            await self.db.refresh(progress)
            return progress

        # Lazy streak maintenance on read so the API never shows a stale streak:
        # - brand-new users with no activity must show 0, not a placeholder
        # - a missed full day breaks the streak (reset to 0, roll history)
        changed = False
        if not progress.last_activity_date and (progress.debates_completed or 0) == 0:
            if (progress.streak_days or 0) != 0 or normalize_streak_history(
                progress.streak_history_json
            ) != EMPTY_STREAK_HISTORY:
                progress.streak_days = 0
                progress.streak_history_json = list(EMPTY_STREAK_HISTORY)
                changed = True
        else:
            last = _parse_iso_date(progress.last_activity_date)
            if last is not None:
                gap = (datetime.date.today() - last).days
                if gap >= 2 and (progress.streak_days or 0) != 0:
                    progress.streak_days = 0
                    hist = normalize_streak_history(progress.streak_history_json)
                    shift = min(gap, 7)
                    progress.streak_history_json = (hist + [0] * 7)[shift:shift + 7]
                    changed = True
        if changed:
            await self.db.commit()
            await self.db.refresh(progress)
        return progress

    async def record_debate_completion(
        self,
        user_id: str,
        skill_id: str,
        stars_earned: int,
        xp_earned: int,
        outcome: str,
        streak_extended: bool,
        is_onboarding: bool = False,
        session_id: Optional[str] = None,
    ) -> Tuple[LearningProgress, bool]:
        """Record a finished debate. Returns (progress, streak_actually_extended).

        The returned flag reflects once-per-day rules: a qualifying debate only
        extends the streak when it is the first qualifying debate of that day.
        """
        prog = await self.get_progress(user_id)

        completed_sessions = list(prog.completed_session_ids_json or [])
        if session_id and session_id in completed_sessions:
            logger.info("progress.already_recorded_for_session", session_id=session_id, user_id=user_id)
            return prog, False

        if session_id:
            completed_sessions.append(session_id)
            prog.completed_session_ids_json = completed_sessions

        new_wins = prog.wins + (1 if outcome == "user_win" else 0)
        new_losses = prog.losses + (1 if outcome == "opponent_win" else 0)
        new_draws = prog.draws + (1 if outcome == "draw" else 0)
        new_streak, new_history, new_last_activity, actually_extended = resolve_streak(
            prog.streak_days or 0,
            prog.last_activity_date,
            prog.streak_history_json,
            qualifies=streak_extended,
        )

        prog.xp += xp_earned
        prog.streak_days = new_streak
        prog.streak_history_json = new_history
        # Only qualifying (sufficient-evidence) debates that extend the streak
        # update the activity date. Same-day repeats keep today's date;
        # insufficient debates leave it untouched so they can't start/extend
        # a streak.
        if actually_extended:
            prog.last_activity_date = new_last_activity
        if stars_earned > 0 or outcome in ("user_win", "opponent_win", "draw"):
            prog.debates_completed += 1
        prog.wins = new_wins
        prog.losses = new_losses
        prog.draws = new_draws

        if not is_onboarding and stars_earned > 0:
            stars_map = dict(prog.stars_by_node_json or {})
            prev_stars = stars_map.get(skill_id, 0)
            stars_map[skill_id] = max(prev_stars, stars_earned)
            prog.stars_by_node_json = stars_map

        await self.db.commit()
        await self.db.refresh(prog)
        return prog, actually_extended


class SpeechProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_profile(self, user_id: str) -> Optional[dict]:
        stmt = select(SpeechProfile).where(SpeechProfile.user_id == user_id)
        res = await self.db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record or not record.profile_encrypted:
            return None
        return encryptor.decrypt_json(record.profile_encrypted)

    async def save_profile(self, user_id: str, profile_dict: dict):
        encrypted = encryptor.encrypt_json(profile_dict)
        stmt = select(SpeechProfile).where(SpeechProfile.user_id == user_id)
        res = await self.db.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            record.profile_encrypted = encrypted
            record.updated_at = utcnow()
        else:
            self.db.add(SpeechProfile(user_id=user_id, profile_encrypted=encrypted))
        await self.db.commit()

    async def delete_profile(self, user_id: str):
        stmt = update(SpeechProfile).where(SpeechProfile.user_id == user_id).values(profile_encrypted=None, updated_at=utcnow())
        await self.db.execute(stmt)
        await self.db.commit()
        logger.info("privacy.speech_profile_deleted", user_id=user_id)


class TopicInventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_available_topics(self, user_id: str, limit: int = 10) -> List[TopicInventory]:
        stmt = (
            select(TopicInventory)
            .where(TopicInventory.user_id == user_id, TopicInventory.consumed == False)
            .order_by(TopicInventory.created_at.asc())
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def count_available_topics(self, user_id: str) -> int:
        stmt = select(TopicInventory).where(TopicInventory.user_id == user_id, TopicInventory.consumed == False)
        res = await self.db.execute(stmt)
        return len(list(res.scalars().all()))

    async def get_topic_by_id(self, user_id: str, topic_id: str) -> Optional[TopicInventory]:
        stmt = (
            select(TopicInventory)
            .where(
                TopicInventory.user_id == user_id,
                TopicInventory.topic_id == topic_id,
            )
            .order_by(TopicInventory.consumed.asc(), TopicInventory.created_at.desc())
            .limit(1)
        )
        res = await self.db.execute(stmt)
        return res.scalars().first()

    async def add_topics(self, user_id: str, topics: List[dict]):
        for t in topics:
            item = TopicInventory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                topic_id=t.get("id") or str(uuid.uuid4()),
                topic_text=t["statement"],
                skill_id=t["skill_id"],
                difficulty=t.get("difficulty", "steady"),
                turns=t.get("turns", 4),
                estimated_minutes=t.get("minutes", 6),
                reminder=t.get("reminder", ""),
                consumed=False,
            )
            self.db.add(item)
        await self.db.commit()

    async def mark_consumed(self, user_id: str, topic_id: str):
        stmt = (
            update(TopicInventory)
            .where(TopicInventory.user_id == user_id, TopicInventory.topic_id == topic_id)
            .values(consumed=True)
        )
        await self.db.execute(stmt)
        await self.db.commit()


class DebateSessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def mark_active_sessions_abandoned(self, user_id: str):
        stmt = (
            update(DebateSession)
            .where(DebateSession.user_id == user_id, DebateSession.status == "active")
            .values(status="abandoned", updated_at=utcnow())
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        topic_id: str,
        topic_text: str,
        skill_id: str,
        skill_name: str,
        skill_hint: str,
        skill_reminder: str,
        difficulty: str,
        user_side: str,
        total_user_turns: int,
        is_onboarding: bool = False,
    ) -> DebateSession:
        # Mark any previous active debates as abandoned - at most 1 active debate per user
        await self.mark_active_sessions_abandoned(user_id)

        sess = DebateSession(
            id=session_id,
            user_id=user_id,
            topic_id=topic_id,
            topic_text=topic_text,
            skill_id=skill_id,
            skill_name=skill_name,
            skill_hint=skill_hint,
            skill_reminder=skill_reminder,
            difficulty=difficulty,
            user_side=user_side,
            total_user_turns=total_user_turns,
            current_turn=1,
            status="active",
            is_onboarding=is_onboarding,
        )
        self.db.add(sess)
        await self.db.commit()
        await self.db.refresh(sess)
        return sess

    async def get_session(self, session_id: str) -> Optional[DebateSession]:
        stmt = (
            select(DebateSession)
            .where(DebateSession.id == session_id)
            .options(
                selectinload(DebateSession.turns),
                selectinload(DebateSession.review),
                selectinload(DebateSession.evidence),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_turns(self, session_id: str) -> List[DebateTurn]:
        stmt = (
            select(DebateTurn)
            .where(DebateTurn.session_id == session_id)
            .order_by(DebateTurn.turn_number.asc(), DebateTurn.created_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_active_session_for_user(self, user_id: str) -> Optional[DebateSession]:
        stmt = (
            select(DebateSession)
            .where(DebateSession.user_id == user_id, DebateSession.status == "active")
            .order_by(DebateSession.created_at.desc())
            .options(selectinload(DebateSession.turns))
            .limit(1)
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_session_for_user(self, user_id: str) -> Optional[DebateSession]:
        stmt = (
            select(DebateSession)
            .where(DebateSession.user_id == user_id)
            .order_by(DebateSession.created_at.desc())
            .options(
                selectinload(DebateSession.turns),
                selectinload(DebateSession.review),
            )
            .limit(1)
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def save_turn(
        self,
        session_id: str,
        turn_number: int,
        speaker: str,
        text: Optional[str],
        audio_available: bool = False,
        duration_sec: float = 0.0,
        client_response_delay_ms: int = 0,
        idempotency_key: Optional[str] = None,
        move: Optional[str] = None,
        requires_response: bool = True,
        addressed_claim: Optional[str] = None,
        conversation_state: str = "unresolved",
        media_asset_id: Optional[str] = None,
    ) -> DebateTurn:
        if idempotency_key:
            stmt = select(DebateTurn).where(
                DebateTurn.session_id == session_id,
                DebateTurn.idempotency_key == idempotency_key,
            )
            res = await self.db.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                return existing

        turn_id = f"t-{speaker[0]}-{turn_number}-{uuid.uuid4().hex[:6]}"
        encrypted_text = encryptor.encrypt_str(text) if text else None

        turn = DebateTurn(
            id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            speaker=speaker,
            text_encrypted=encrypted_text,
            audio_available=audio_available,
            duration_sec=duration_sec,
            client_response_delay_ms=client_response_delay_ms,
            idempotency_key=idempotency_key,
            move=move,
            requires_response=requires_response,
            addressed_claim=addressed_claim,
            conversation_state=conversation_state,
            media_asset_id=media_asset_id,
        )
        self.db.add(turn)
        await self.db.commit()
        await self.db.refresh(turn)
        return turn

    async def update_current_turn(self, session_id: str, next_turn_number: int, status: Optional[str] = None):
        values = {"current_turn": next_turn_number, "updated_at": utcnow()}
        if status:
            values["status"] = status
        stmt = update(DebateSession).where(DebateSession.id == session_id).values(**values)
        await self.db.execute(stmt)
        await self.db.commit()

    async def save_pre_final_analysis(self, session_id: str, analysis_dict: dict):
        encrypted = encryptor.encrypt_json(analysis_dict)
        stmt = update(DebateSession).where(DebateSession.id == session_id).values(pre_final_analysis_encrypted=encrypted)
        await self.db.execute(stmt)
        await self.db.commit()

    async def get_pre_final_analysis(self, session_id: str) -> Optional[dict]:
        sess = await self.get_session(session_id)
        if not sess or not sess.pre_final_analysis_encrypted:
            return None
        return encryptor.decrypt_json(sess.pre_final_analysis_encrypted)

    async def save_temporary_evidence(self, session_id: str, turn_number: int, evidence_dict: dict):
        encrypted = encryptor.encrypt_json(evidence_dict)
        stmt = select(TemporaryTurnEvidence).where(
            TemporaryTurnEvidence.session_id == session_id,
            TemporaryTurnEvidence.turn_number == turn_number,
        )
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.evidence_encrypted = encrypted
        else:
            self.db.add(TemporaryTurnEvidence(
                id=str(uuid.uuid4()),
                session_id=session_id,
                turn_number=turn_number,
                evidence_encrypted=encrypted,
            ))
        await self.db.commit()

    async def get_all_temporary_evidence(self, session_id: str) -> List[dict]:
        stmt = (
            select(TemporaryTurnEvidence)
            .where(TemporaryTurnEvidence.session_id == session_id)
            .order_by(TemporaryTurnEvidence.turn_number.asc())
        )
        res = await self.db.execute(stmt)
        records = res.scalars().all()
        return [encryptor.decrypt_json(r.evidence_encrypted) for r in records if r.evidence_encrypted]

    async def delete_temporary_evidence(self, session_id: str):
        stmt = delete(TemporaryTurnEvidence).where(TemporaryTurnEvidence.session_id == session_id)
        await self.db.execute(stmt)
        await self.db.commit()

    async def save_review(
        self,
        session_id: str,
        user_id: str,
        outcome: str,
        stars: int,
        completed: bool = True,
        skill_demonstrated: bool = False,
        mastery_note: Optional[str] = None,
        skill_assessment: Optional[dict] = None,
        argument_feedback: Optional[dict] = None,
        language_feedback: Optional[dict] = None,
        xp_earned: int = 0,
        streak_extended: bool = False,
        next_level_unlocked: bool = False,
        score_technique: Optional[int] = None,
        score_grammar: Optional[int] = None,
        score_vocabulary: Optional[int] = None,
        score_delivery: Optional[int] = None,
        score_technique_rubric: Optional[str] = None,
        score_grammar_rubric: Optional[str] = None,
        score_vocabulary_rubric: Optional[str] = None,
        score_delivery_rubric: Optional[str] = None,
        strongest_moment: Optional[str] = None,
        improvement_opportunity: Optional[str] = None,
        grammar_advice: Optional[str] = None,
        vocabulary_advice: Optional[str] = None,
        pronunciation_advice: Optional[str] = None,
    ) -> DebateReview:
        stmt = select(DebateReview).where(DebateReview.session_id == session_id)
        res = await self.db.execute(stmt)
        existing = res.scalar_one_or_none()

        encrypted_lang = encryptor.encrypt_json(language_feedback) if language_feedback else None

        if existing:
            existing.outcome = outcome
            existing.stars = stars
            existing.completed = completed
            existing.skill_demonstrated = skill_demonstrated
            existing.mastery_note = mastery_note
            existing.skill_assessment_json = skill_assessment
            existing.argument_feedback_json = argument_feedback
            existing.language_feedback_encrypted = encrypted_lang
            existing.xp_earned = xp_earned
            existing.streak_extended = streak_extended
            existing.next_level_unlocked = next_level_unlocked
            existing.score_technique = score_technique
            existing.score_grammar = score_grammar
            existing.score_vocabulary = score_vocabulary
            existing.score_delivery = score_delivery
            existing.score_technique_rubric = score_technique_rubric
            existing.score_grammar_rubric = score_grammar_rubric
            existing.score_vocabulary_rubric = score_vocabulary_rubric
            existing.score_delivery_rubric = score_delivery_rubric
            existing.strongest_moment = strongest_moment
            existing.improvement_opportunity = improvement_opportunity
            existing.grammar_advice = grammar_advice
            existing.vocabulary_advice = vocabulary_advice
            existing.pronunciation_advice = pronunciation_advice
            review = existing
        else:
            review = DebateReview(
                session_id=session_id,
                user_id=user_id,
                outcome=outcome,
                stars=stars,
                completed=completed,
                skill_demonstrated=skill_demonstrated,
                mastery_note=mastery_note,
                skill_assessment_json=skill_assessment,
                argument_feedback_json=argument_feedback,
                language_feedback_encrypted=encrypted_lang,
                xp_earned=xp_earned,
                streak_extended=streak_extended,
                next_level_unlocked=next_level_unlocked,
                score_technique=score_technique,
                score_grammar=score_grammar,
                score_vocabulary=score_vocabulary,
                score_delivery=score_delivery,
                score_technique_rubric=score_technique_rubric,
                score_grammar_rubric=score_grammar_rubric,
                score_vocabulary_rubric=score_vocabulary_rubric,
                score_delivery_rubric=score_delivery_rubric,
                strongest_moment=strongest_moment,
                improvement_opportunity=improvement_opportunity,
                grammar_advice=grammar_advice,
                vocabulary_advice=vocabulary_advice,
                pronunciation_advice=pronunciation_advice,
            )
            self.db.add(review)

        await self.db.commit()
        return review

    async def get_review(self, session_id: str) -> Optional[DebateReview]:
        stmt = select(DebateReview).where(DebateReview.session_id == session_id)
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def save_review_feedback(self, session_id: str, user_id: str, verdict: str, reason: Optional[str] = None):
        fb = ReviewFeedback(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            verdict=verdict,
            reason=reason,
        )
        self.db.add(fb)
        await self.db.commit()

    async def cleanup_finished_session_privacy(self, session_id: str, save_transcripts: bool):
        await self.delete_temporary_evidence(session_id)
        stmt_pre = update(DebateSession).where(DebateSession.id == session_id).values(pre_final_analysis_encrypted=None)
        await self.db.execute(stmt_pre)
        logger.info("privacy.session_evidence_deleted", session_id=session_id)
        if not save_transcripts:
            stmt = update(DebateTurn).where(DebateTurn.session_id == session_id).values(text_encrypted=None)
            await self.db.execute(stmt)
            logger.info("privacy.transcript_deleted", session_id=session_id)
        await self.db.commit()

    async def cleanup_abandoned_evidence(self, hours: int = 24):
        cutoff = utcnow() - datetime.timedelta(hours=hours)
        stmt = delete(TemporaryTurnEvidence).where(TemporaryTurnEvidence.created_at < cutoff)
        await self.db.execute(stmt)
        await self.db.commit()
        logger.info("privacy.history_retention_applied", retention_hours=hours)


# ---------------------------------------------------------------------------
# Coach Repository & Coach Memory
# ---------------------------------------------------------------------------

class CoachRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_debate_thread(self, user_id: str, session_id: str, title: str) -> CoachThread:
        stmt = (
            select(CoachThread)
            .where(CoachThread.user_id == user_id, CoachThread.session_id == session_id)
            .options(
                selectinload(CoachThread.messages).selectinload(CoachMessage.evidence_clip),
                selectinload(CoachThread.session),
            )
        )
        res = await self.db.execute(stmt)
        thread = res.scalar_one_or_none()
        if thread:
            return thread

        thread_id = f"thread-deb-{uuid.uuid4().hex[:8]}"
        thread = CoachThread(
            id=thread_id,
            user_id=user_id,
            session_id=session_id,
            thread_type="debate_review",
            title=title,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.db.add(thread)
        await self.db.commit()
        loaded = await self.get_thread(user_id, thread_id)
        return loaded if loaded is not None else thread

    async def create_general_thread(self, user_id: str, title: str = "General Coaching") -> CoachThread:
        thread_id = f"thread-gen-{uuid.uuid4().hex[:8]}"
        thread = CoachThread(
            id=thread_id,
            user_id=user_id,
            session_id=None,
            thread_type="general",
            title=title,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.db.add(thread)
        await self.db.commit()
        loaded = await self.get_thread(user_id, thread_id)
        return loaded if loaded is not None else thread

    async def get_thread(self, user_id: str, thread_id: str) -> Optional[CoachThread]:
        stmt = (
            select(CoachThread)
            .where(CoachThread.id == thread_id, CoachThread.user_id == user_id)
            .options(
                selectinload(CoachThread.messages).selectinload(CoachMessage.evidence_clip),
                selectinload(CoachThread.session),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_thread_messages(self, thread_id: str) -> List[CoachMessage]:
        stmt = (
            select(CoachMessage)
            .where(CoachMessage.thread_id == thread_id)
            .options(selectinload(CoachMessage.evidence_clip))
            .order_by(CoachMessage.created_at.asc())
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def list_threads(self, user_id: str, limit: int = 30) -> List[CoachThread]:
        stmt = (
            select(CoachThread)
            .where(CoachThread.user_id == user_id)
            .order_by(CoachThread.updated_at.desc())
            .options(
                selectinload(CoachThread.messages),
                selectinload(CoachThread.session),
            )
            .limit(limit)
        )
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def add_message(
        self,
        user_id: str,
        thread_id: str,
        sender: str,
        message_type: str,
        text: Optional[str] = None,
        media_asset_id: Optional[str] = None,
        evidence_clip_id: Optional[str] = None,
        structured_data: Optional[dict] = None,
        processing_state: str = "ready",
    ) -> CoachMessage:
        msg_id = f"msg-{uuid.uuid4().hex[:10]}"
        encrypted_text = encryptor.encrypt_str(text) if text else None

        msg = CoachMessage(
            id=msg_id,
            thread_id=thread_id,
            user_id=user_id,
            sender=sender,
            message_type=message_type,
            text_encrypted=encrypted_text,
            media_asset_id=media_asset_id,
            evidence_clip_id=evidence_clip_id,
            structured_data_json=structured_data,
            processing_state=processing_state,
            created_at=utcnow(),
        )
        self.db.add(msg)

        stmt_thread = (
            update(CoachThread)
            .where(CoachThread.id == thread_id)
            .values(updated_at=utcnow())
        )
        await self.db.execute(stmt_thread)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def update_message_processing_state(
        self,
        msg_id: str,
        processing_state: str,
        text: Optional[str] = None,
        structured_data: Optional[dict] = None,
    ):
        values = {"processing_state": processing_state}
        if text is not None:
            values["text_encrypted"] = encryptor.encrypt_str(text)
        if structured_data is not None:
            values["structured_data_json"] = structured_data

        stmt = update(CoachMessage).where(CoachMessage.id == msg_id).values(**values)
        await self.db.execute(stmt)
        await self.db.commit()

    # -----------------------------------------------------------------------
    # Canonical Markdown Memory Methods
    # -----------------------------------------------------------------------

    async def get_memory_markdown(self, user_id: str) -> Tuple[str, int]:
        stmt = select(CoachMemory).where(CoachMemory.user_id == user_id)
        res = await self.db.execute(stmt)
        mem = res.scalar_one_or_none()
        if not mem or not mem.memory_markdown_encrypted:
            return DEFAULT_STARTER_MEMORY, 0
        decrypted = encryptor.decrypt_str(mem.memory_markdown_encrypted)
        return (decrypted or DEFAULT_STARTER_MEMORY), mem.revision

    async def save_memory_markdown(self, user_id: str, markdown: str, expected_revision: int = 0) -> Tuple[bool, Optional[int]]:
        encrypted = encryptor.encrypt_str(markdown)
        stmt = select(CoachMemory.revision).where(CoachMemory.user_id == user_id)
        res = await self.db.execute(stmt)
        current_rev = res.scalar_one_or_none()

        if current_rev is None:
            new_rev = 1
            mem = CoachMemory(
                user_id=user_id,
                memory_markdown_encrypted=encrypted,
                revision=new_rev,
                updated_at=utcnow(),
            )
            self.db.add(mem)
            await self.db.commit()
            logger.info("coach.memory.saved", user_id=user_id, revision=new_rev)
            return True, new_rev

        # Optimistic concurrency check:
        # UPDATE coach_memory SET markdown = ..., revision = revision + 1
        # WHERE user_id = :user_id AND revision = :expected_revision
        update_stmt = (
            update(CoachMemory)
            .where(CoachMemory.user_id == user_id, CoachMemory.revision == expected_revision)
            .values(
                memory_markdown_encrypted=encrypted,
                revision=expected_revision + 1,
                updated_at=utcnow(),
            )
        )
        update_res = await self.db.execute(update_stmt)
        if update_res.rowcount == 0:
            logger.warning("coach.memory.revision_conflict", user_id=user_id, expected_rev=expected_revision)
            return False, None

        await self.db.commit()
        new_rev = expected_revision + 1
        logger.info("coach.memory.saved", user_id=user_id, revision=new_rev)
        return True, new_rev

    async def apply_user_memory_correction(
        self,
        user_id: str,
        correction_text: str,
        action: str = "update",
        label: Optional[str] = None,
    ) -> str:
        current_md, rev = await self.get_memory_markdown(user_id)
        today = datetime.date.today().isoformat()
        prefix = f"- [{today}] Correction ({label or 'General'}): {correction_text}\n"

        def _insert_correction(md: str) -> str:
            if "## User Preferences & Goals" in md:
                parts = md.split("## User Preferences & Goals", 1)
                return parts[0] + "## User Preferences & Goals\n" + prefix + parts[1]
            return f"{md}\n\n## User Preferences & Goals\n{prefix}"

        updated_md = _insert_correction(current_md)
        saved, _ = await self.save_memory_markdown(user_id, updated_md, expected_revision=rev)
        if not saved:
            # Reload latest markdown and retry once
            latest_md, latest_rev = await self.get_memory_markdown(user_id)
            updated_md = _insert_correction(latest_md)
            await self.save_memory_markdown(user_id, updated_md, expected_revision=latest_rev)

        logger.info("coach.memory.correction_applied", user_id=user_id, action=action)
        return updated_md

    async def get_active_focus(self, user_id: str) -> Tuple[str, Optional[str]]:
        current_md, _ = await self.get_memory_markdown(user_id)
        lines = [line.strip() for line in current_md.splitlines() if line.strip().startswith("- ")]
        for line in lines:
            if "Focus:" in line or "Primary Focus" in line:
                content = line.replace("- ", "", 1).strip()
                return "Debate Technique & Flow", content
        return "Early Premise Clarity", "Focus on stating your central claim within the first 10 seconds of speaking."
