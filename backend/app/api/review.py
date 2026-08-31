from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.orchestration import DebateOrchestrator
from backend.app.models.db import User
from backend.app.models.schemas import (
    DebateReviewSchema,
    ReviewFeedbackRequestSchema,
)
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import DebateSessionRepository

router = APIRouter(prefix="/api/sessions", tags=["reviews"])


@router.get("/{session_id}/review", response_model=DebateReviewSchema)
async def get_debate_review(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from backend.app.models.db import DebateSession

    target_session_id = session_id
    if session_id == "current":
        stmt = select(DebateSession).where(DebateSession.user_id == user.id).order_by(DebateSession.created_at.desc()).limit(1)
        res = await db.execute(stmt)
        latest = res.scalar_one_or_none()
        if latest:
            target_session_id = latest.id
        else:
            raise HTTPException(status_code=404, detail="Debate session not found")

    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(target_session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    review_db = await sess_repo.get_review(target_session_id)
    if not review_db:
        # Finalize on the fly if needed
        return await DebateOrchestrator.finalize_debate_review(target_session_id, user.id)

    return DebateOrchestrator._db_review_to_schema(
        review_db,
        target_session_id,
        session.topic_text,
        session.skill_name,
    )


@router.post("/{session_id}/review-feedback")
async def submit_review_feedback(
    session_id: str,
    req: ReviewFeedbackRequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from backend.app.models.db import DebateSession

    target_session_id = session_id
    if session_id == "current":
        stmt = select(DebateSession).where(DebateSession.user_id == user.id).order_by(DebateSession.created_at.desc()).limit(1)
        res = await db.execute(stmt)
        latest = res.scalar_one_or_none()
        if latest:
            target_session_id = latest.id
        else:
            raise HTTPException(status_code=404, detail="Debate session not found")

    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(target_session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    await sess_repo.save_review_feedback(
        session_id=target_session_id,
        user_id=user.id,
        verdict=req.verdict,
        reason=req.reason,
    )
    return {"status": "ok", "message": "Feedback recorded."}
