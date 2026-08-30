import asyncio
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.domain.curriculum import (
    CURRICULUM_SKILLS,
    get_current_skill_for_user,
    get_skill,
)
from backend.app.persistence.repositories import (
    ProgressRepository,
    SpeechProfileRepository,
    TopicInventoryRepository,
    UserRepository,
)
from backend.app.prompts.topic_generator import build_topic_generator_prompt
from backend.app.services.ai.gateway import ai_gateway

logger = logging.getLogger("rebutio.topics")


class TopicInventoryService:
    @staticmethod
    async def get_or_refill_inventory(
        db: AsyncSession,
        user_id: str,
        limit: int = 10,
    ) -> List[dict]:
        """
        Retrieves active unconsumed topics for the user.
        If inventory is below threshold, triggers an asynchronous refill.
        """
        topic_repo = TopicInventoryRepository(db)
        existing = await topic_repo.get_available_topics(user_id, limit=limit)

        # Convert to choice dictionaries matching frontend expectation
        choices = []
        for t in existing:
            skill = get_skill(t.skill_id)
            choices.append({
                "id": t.topic_id,
                "topic": t.topic_text,
                "skill": t.skill_id,
                "difficulty": t.difficulty,
                "turns": t.turns,
                "minutes": t.estimated_minutes,
                "reminder": t.reminder or skill.reminder,
            })

        # Check if refill is needed
        if len(choices) <= settings.INVENTORY_REFILL_THRESHOLD:
            # Trigger background refill
            asyncio.create_task(TopicInventoryService._background_refill(user_id))

        # If inventory was completely empty, generate synchronous fallback
        if not choices:
            fallback_topic = await TopicInventoryService.generate_synchronous_fallback(db, user_id)
            choices.append(fallback_topic)

        return choices

    @staticmethod
    async def generate_synchronous_fallback(db: AsyncSession, user_id: str) -> dict:
        user_repo = UserRepository(db)
        prog_repo = ProgressRepository(db)

        user = await user_repo.get_or_create_user(user_id)
        prog = await prog_repo.get_progress(user_id)
        skill = get_current_skill_for_user(prog.stars_by_node_json or {})

        topic_data = {
            "id": f"topic-fallback-{skill.id}",
            "statement": "College is no longer worth the financial cost.",
            "skill_id": skill.id,
            "difficulty": skill.default_difficulty,
            "turns": skill.default_turns,
            "minutes": skill.default_minutes,
            "reminder": skill.reminder,
        }

        topic_repo = TopicInventoryRepository(db)
        await topic_repo.add_topics(user_id, [topic_data])

        return {
            "id": topic_data["id"],
            "topic": topic_data["statement"],
            "skill": topic_data["skill_id"],
            "difficulty": topic_data["difficulty"],
            "turns": topic_data["turns"],
            "minutes": topic_data["minutes"],
            "reminder": topic_data["reminder"],
        }

    @staticmethod
    async def _background_refill(user_id: str):
        """
        Background task to refill topic inventory without blocking UI responses.
        """
        from backend.app.persistence.db import async_session_factory
        try:
            async with async_session_factory() as db:
                user_repo = UserRepository(db)
                prog_repo = ProgressRepository(db)
                speech_repo = SpeechProfileRepository(db)
                topic_repo = TopicInventoryRepository(db)

                user = await user_repo.get_or_create_user(user_id)
                prefs = user_repo.get_preferences(user) or {}
                prog = await prog_repo.get_progress(user_id)
                speech_prof = await speech_repo.get_profile(user_id)

                skill = get_current_skill_for_user(prog.stars_by_node_json or {})
                current_topics = await topic_repo.get_available_topics(user_id, limit=20)
                recent_topics = [t.topic_text for t in current_topics]

                needed = max(1, settings.INVENTORY_TARGET_COUNT - len(current_topics))
                interests = prefs.get("interests", [])

                messages = build_topic_generator_prompt(
                    skill_id=skill.id,
                    skill_name=skill.name,
                    difficulty=skill.default_difficulty,
                    user_interests=interests,
                    recent_topics=recent_topics,
                    compact_speech_findings=speech_prof,
                    count=needed,
                )

                generated = await ai_gateway.generate_topics(messages, skill_id=skill.id)

                to_insert = []
                for item in generated.topics:
                    to_insert.append({
                        "id": item.id,
                        "statement": item.statement,
                        "skill_id": skill.id,
                        "difficulty": item.estimated_difficulty or skill.default_difficulty,
                        "turns": skill.default_turns,
                        "minutes": skill.default_minutes,
                        "reminder": skill.reminder,
                    })

                if to_insert:
                    await topic_repo.add_topics(user_id, to_insert)
                    logger.info(f"Refilled {len(to_insert)} debate topics for user {user_id}")
        except Exception as e:
            logger.warning(f"Background topic refill failed: {e}")
