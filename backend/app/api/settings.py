from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.models.db import User
from backend.app.models.schemas import SettingsUpdateSchema
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    SpeechProfileRepository,
    UserRepository,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    prefs = user_repo.get_preferences(user) or {}
    return {
        "saveTranscripts": user.save_transcripts,
        "captionsEnabled": user.captions_enabled,
        "intensity": prefs.get("intensity", "balanced"),
        "goals": prefs.get("goals", []),
        "interests": prefs.get("interests", []),
        "comfort": prefs.get("comfort", ""),
    }


@router.patch("")
async def update_settings(
    req: SettingsUpdateSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    updated_user = await user_repo.update_settings(
        user_id=user.id,
        save_transcripts=req.saveTranscripts,
        captions_enabled=req.captionsEnabled,
        intensity=req.intensity,
    )
    prefs = user_repo.get_preferences(updated_user) or {}
    return {
        "status": "ok",
        "saveTranscripts": updated_user.save_transcripts,
        "captionsEnabled": updated_user.captions_enabled,
        "intensity": prefs.get("intensity", "balanced"),
    }


@router.delete("/history")
async def delete_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes transcript text across all user sessions while retaining progress metadata.
    """
    from sqlalchemy import select, update
    from backend.app.models.db import DebateSession, DebateTurn

    # Query all session IDs belonging to the user
    stmt_sess = select(DebateSession.id).where(DebateSession.user_id == user.id)
    res = await db.execute(stmt_sess)
    session_ids = list(res.scalars().all())

    if session_ids:
        stmt = update(DebateTurn).where(DebateTurn.session_id.in_(session_ids)).values(text_encrypted=None)
        await db.execute(stmt)
        await db.commit()

    return {"status": "ok", "message": "Transcript history cleared."}


@router.get("/history")
async def list_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists past debate sessions with outcome and stars metadata.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from backend.app.models.db import DebateSession

    stmt = (
        select(DebateSession)
        .where(DebateSession.user_id == user.id, DebateSession.status == "finished")
        .order_by(DebateSession.created_at.desc())
        .options(selectinload(DebateSession.review), selectinload(DebateSession.turns))
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    items = []
    for s in sessions:
        has_transcripts = any(t.text_encrypted is not None for t in s.turns if t.speaker == "user")
        items.append({
            "sessionId": s.id,
            "topic": s.topic_text,
            "skillName": s.skill_name,
            "difficulty": s.difficulty,
            "outcome": s.review.outcome if s.review else "undetermined",
            "stars": s.review.stars if s.review else 1,
            "createdAt": s.created_at.isoformat() if s.created_at else "",
            "transcriptsSaved": has_transcripts,
        })
    return items


@router.delete("/speech-profile")
async def delete_speech_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    speech_repo = SpeechProfileRepository(db)
    await speech_repo.delete_profile(user.id)
    return {"status": "ok", "message": "Speech profile cleared."}

