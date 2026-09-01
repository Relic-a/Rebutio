import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.domain.curriculum import get_current_skill_for_user, get_skill
from backend.app.domain.topics import TopicInventoryService
from backend.app.models.db import User
from backend.app.models.schemas import (
    DebateSessionSchema,
    DebateSetupSchema,
    DebateTopicChoiceSchema,
    SkillTargetSchema,
    StartDebateRequestSchema,
    StartDebateResponseSchema,
)
from backend.app.observability.context import bind_context
from backend.app.observability.logging import get_logger
from backend.app.persistence.db import get_db
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    ProgressRepository,
    TopicInventoryRepository,
    UserRepository,
)

logger = get_logger("rebutio.debates")
router = APIRouter(prefix="/api/debates", tags=["debates"])


@router.get("/choices", response_model=List[DebateTopicChoiceSchema])
async def get_debate_choices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topics = await TopicInventoryService.get_or_refill_inventory(db, user_id=user.id, limit=10)
    return [DebateTopicChoiceSchema(**t) for t in topics]


@router.post("/start", response_model=StartDebateResponseSchema)
async def start_debate(
    req: StartDebateRequestSchema,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    topic_repo = TopicInventoryRepository(db)
    sess_repo = DebateSessionRepository(db)
    prog_repo = ProgressRepository(db)
    user_repo = UserRepository(db)

    prog = await prog_repo.get_progress(user.id)
    default_skill = get_current_skill_for_user(prog.stars_by_node_json or {})

    topic_record = None
    if req.topicId:
        topic_record = await topic_repo.get_topic_by_id(user.id, req.topicId)

    if req.onboarding:
        from backend.app.api.onboarding import FIRST_SPAR_TOPICS_BY_INTEREST
        user_prefs = user_repo.get_preferences(user) or {}
        interests = req.interests or user_prefs.get("interests", [])
        matched_key = next((i for i in interests if i in FIRST_SPAR_TOPICS_BY_INTEREST), "tech")
        topic_id, topic_text, skill_id = FIRST_SPAR_TOPICS_BY_INTEREST.get(
            matched_key, ("social-media", "Social media has made friendships worse.", "counterpoint")
        )
        skill = get_skill(skill_id)
        difficulty = "gentle"
        turns = 3
        reminder = skill.reminder
    elif topic_record:
        topic_id = topic_record.topic_id
        topic_text = topic_record.topic_text
        skill = get_skill(topic_record.skill_id)
        difficulty = topic_record.difficulty
        turns = topic_record.turns
        reminder = topic_record.reminder or skill.reminder
    else:
        # Check if topic available in inventory
        available = await topic_repo.get_available_topics(user.id, limit=1)
        if available:
            inv_t = available[0]
            topic_id = inv_t.topic_id
            topic_text = inv_t.topic_text
            skill = get_skill(inv_t.skill_id)
            difficulty = inv_t.difficulty
            turns = inv_t.turns
            reminder = inv_t.reminder or skill.reminder
        else:
            skill = default_skill
            topic_id = req.topicId or f"topic-{uuid.uuid4().hex[:6]}"
            topic_text = "College is no longer worth the financial cost." if not req.topicId else req.topicId
            difficulty = skill.default_difficulty
            turns = skill.default_turns
            reminder = skill.reminder

    session_id = f"session-{uuid.uuid4().hex[:8]}"

    session_db = await sess_repo.create_session(
        session_id=session_id,
        user_id=user.id,
        topic_id=topic_id,
        topic_text=topic_text,
        skill_id=skill.id,
        skill_name=skill.name,
        skill_hint=skill.hint,
        skill_reminder=reminder,
        difficulty=difficulty,
        user_side=req.side,
        total_user_turns=turns,
        is_onboarding=req.onboarding,
    )

    bind_context(session_id=session_id, user_id=user.id)
    logger.info(
        "debate.session.started",
        session_id=session_id,
        topic_id=topic_id,
        skill_id=skill.id,
        user_side=req.side,
        total_turns=turns,
        difficulty=difficulty,
        onboarding=req.onboarding,
    )

    session_schema = DebateSessionSchema(
        id=session_db.id,
        topic=session_db.topic_text,
        skillTarget=SkillTargetSchema(id=skill.id, name=skill.name, hint=skill.hint),
        difficulty=session_db.difficulty,
        userSide=session_db.user_side,
        totalUserTurns=session_db.total_user_turns,
        currentTurn=session_db.current_turn,
        status="active",
        turns=[],
        skillReminder=session_db.skill_reminder,
        isOnboarding=req.onboarding,
    )

    setup_schema = DebateSetupSchema(
        topic=session_db.topic_text,
        skillTarget=SkillTargetSchema(id=skill.id, name=skill.name, hint=skill.hint),
        skillReminder=session_db.skill_reminder,
        difficulty=session_db.difficulty,
        totalUserTurns=session_db.total_user_turns,
        secondsPerTurn=0,
        opponentLines=[],
    )

    return StartDebateResponseSchema(session=session_schema, setup=setup_schema)
