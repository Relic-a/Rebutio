import asyncio
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import get_skill
from backend.app.domain.topics import TopicInventoryService
from backend.app.models.db import User
from backend.app.models.schemas import (
    DebateSessionSchema,
    DebateSetupSchema,
    OnboardingPreferencesSchema,
    StartDebateResponseSchema,
)
from backend.app.observability.context import bind_context
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    UserRepository,
)

logger = get_logger("rebutio.onboarding")
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

FIRST_SPAR_TOPICS_BY_INTEREST = {
    "tech": ("social-media", "Social media has made friendships worse.", "counterpoint"),
    "relationships": ("social-media", "Social media has made friendships worse.", "counterpoint"),
    "money": ("money-happiness", "Money can buy happiness.", "take_a_side"),
    "psychology": ("money-happiness", "Money can buy happiness.", "take_a_side"),
    "society": ("phone-ban", "Schools should ban phones entirely during the day.", "cross_examination"),
    "careers": ("four-day", "The four-day work week should become standard.", "rebuttal"),
    "gaming": ("video-games", "Video games are a legitimate competitive sport.", "give_a_reason"),
    "popculture": ("ai-art", "AI-generated images should count as real art.", "counterargument"),
    "science": ("space-money", "Space exploration spending should go to problems on Earth.", "concession"),
    "ethics": ("identity-online", "People should be allowed to use any name and identity online.", "nuance"),
    "sports": ("video-games", "Video games are a legitimate competitive sport.", "give_a_reason"),
    "weird": ("cats-dogs", "Cats are better pets than dogs.", "take_a_side"),
}


@router.post("/preferences")
async def save_onboarding_preferences(
    prefs: OnboardingPreferencesSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    await user_repo.update_preferences(user.id, prefs.model_dump(), onboarded=True)
    logger.info("onboarding.preferences_saved", user_id=user.id, intensity=prefs.intensity, goals_count=len(prefs.goals), interests_count=len(prefs.interests))

    # Populate initial rolling topic inventory in the background
    asyncio.create_task(TopicInventoryService._background_refill(user.id))

    return {"status": "ok"}


@router.post("/spar/start", response_model=StartDebateResponseSchema)
async def start_onboarding_spar(
    side: str = "agree",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)
    sess_repo = DebateSessionRepository(db)
    prefs = user_repo.get_preferences(user) or {}
    interests = prefs.get("interests", [])

    # Pick first spar topic mapped to user interests
    matched_key = next((i for i in interests if i in FIRST_SPAR_TOPICS_BY_INTEREST), "tech")
    topic_id, topic_text, skill_id = FIRST_SPAR_TOPICS_BY_INTEREST.get(
        matched_key, ("social-media", "Social media has made friendships worse.", "counterpoint")
    )

    skill = get_skill(skill_id)
    total_turns = 3  # Onboarding placement debate is always 3 turns
    session_id = f"spar-{uuid.uuid4().hex[:8]}"

    session_record = await sess_repo.create_session(
        session_id=session_id,
        user_id=user.id,
        topic_id=topic_id,
        topic_text=topic_text,
        skill_id=skill.id,
        skill_name=skill.name,
        skill_hint=skill.hint,
        skill_reminder=skill.reminder,
        difficulty="gentle",
        user_side=side,
        total_user_turns=total_turns,
    )

    bind_context(session_id=session_id, user_id=user.id)
    logger.info(
        "debate.session.started",
        session_id=session_id,
        topic_id=topic_id,
        skill_id=skill.id,
        user_side=side,
        total_turns=total_turns,
        difficulty="gentle",
        onboarding=True,
    )

    session_schema = DebateSessionSchema(
        id=session_record.id,
        topic=session_record.topic_text,
        skillTarget={"id": skill.id, "name": skill.name, "hint": skill.hint},
        difficulty="gentle",
        userSide=side,
        totalUserTurns=total_turns,
        currentTurn=1,
        status="active",
        turns=[],
        skillReminder=skill.reminder,
    )

    setup_schema = DebateSetupSchema(
        topic=session_record.topic_text,
        skillTarget={"id": skill.id, "name": skill.name, "hint": skill.hint},
        skillReminder=skill.reminder,
        difficulty="gentle",
        totalUserTurns=total_turns,
        secondsPerTurn=0,
        opponentLines=[],
    )

    return StartDebateResponseSchema(session=session_schema, setup=setup_schema)
