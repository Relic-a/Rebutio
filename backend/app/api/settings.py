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
    from sqlalchemy import update
    from backend.app.models.db import DebateTurn
    stmt = (
        update(DebateTurn)
        .where(DebateTurn.session_id.in_(
            # sessions belonging to user
            select_stmt = [s.id for s in user.sessions]
        ))
        .values(text_encrypted=None)
    )
    # Perform update if user has sessions
    if user.sessions:
        session_ids = [s.id for s in user.sessions]
        stmt = update(DebateTurn).where(DebateTurn.session_id.in_(session_ids)).values(text_encrypted=None)
        await db.execute(stmt)
        await db.commit()

    return {"status": "ok", "message": "Transcript history cleared."}


@router.delete("/speech-profile")
async def delete_speech_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    speech_repo = SpeechProfileRepository(db)
    await speech_repo.delete_profile(user.id)
    return {"status": "ok", "message": "Speech profile cleared."}
