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
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    review_db = await sess_repo.get_review(session_id)
    if not review_db:
        # Finalize on the fly if needed
        return await DebateOrchestrator.finalize_debate_review(session_id, user.id)

    return DebateOrchestrator._db_review_to_schema(
        review_db,
        session_id,
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
    sess_repo = DebateSessionRepository(db)
    session = await sess_repo.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Debate session not found")

    await sess_repo.save_review_feedback(
        session_id=session_id,
        user_id=user.id,
        verdict=req.verdict,
        reason=req.reason,
    )
    return {"status": "ok", "message": "Feedback recorded."}
