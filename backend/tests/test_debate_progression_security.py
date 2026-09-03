import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.api.dependencies import sign_user_id
from backend.app.main import app
from backend.app.persistence.db import async_session_factory, init_db
from backend.app.persistence.repositories import (
    ProgressRepository,
    TopicInventoryRepository,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_locked_debate_cannot_be_accessed_via_topic_id():
    """
    Verifies that an attacker or user cannot start a debate for a locked node/skill
    by passing a topicId that belongs to that locked skill.
    """
    user_id = f"user-lock-test-{uuid.uuid4().hex[:8]}"
    token = sign_user_id(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Add a topic belonging to a locked skill (nuance / level 11) to user's inventory
    async with async_session_factory() as db:
        topic_repo = TopicInventoryRepository(db)
        await topic_repo.add_topics(user_id, [{
            "id": "topic-nuance-locked-1",
            "statement": "Economic inequality is an unavoidable consequence of individual liberty.",
            "skill_id": "nuance",
            "difficulty": "sharp",
            "turns": 5,
            "minutes": 8,
            "reminder": "Nuance reminder",
        }])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        # Check path: nuance should be locked
        path_resp = await client.get("/api/path")
        assert path_resp.status_code == 200
        path_data = path_resp.json()
        nuance_node = next(n for n in path_data["nodes"] if n["id"] == "nuance")
        assert nuance_node["status"] == "locked"

        # Attempt to start debate with topicId of the locked skill
        start_resp = await client.post(
            "/api/debates/start",
            json={"topicId": "topic-nuance-locked-1", "side": "agree"},
        )
        assert start_resp.status_code == 403
        detail = start_resp.json()["detail"]
        assert "locked" in detail.lower()


@pytest.mark.asyncio
async def test_locked_debate_cannot_be_accessed_via_skill_or_order_number():
    """
    Verifies that passing skill ID or level/order number (e.g. '2', 'give_a_reason', 'level-2')
    is blocked with 403 Forbidden when that skill is locked.
    """
    user_id = f"user-lock-ident-{uuid.uuid4().hex[:8]}"
    token = sign_user_id(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        # Level 2 ('give_a_reason') is locked for a fresh user
        for target in ["give_a_reason", "2", "level-2", "debate-2", "uniforms"]:
            resp = await client.post(
                "/api/debates/start",
                json={"topicId": target, "side": "agree"},
            )
            assert resp.status_code == 403, f"Expected 403 for locked target '{target}', got {resp.status_code}"
            assert "locked" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unlocked_debate_starts_successfully():
    """
    Verifies that Level 1 ('take_a_side', '1', 'cats-dogs') is allowed for a fresh user.
    """
    user_id = f"user-unlocked-{uuid.uuid4().hex[:8]}"
    token = sign_user_id(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        resp = await client.post(
            "/api/debates/start",
            json={"topicId": "1", "side": "agree"},
        )
        assert resp.status_code == 200
        sess = resp.json()["session"]
        assert sess["skillTarget"]["id"] == "take_a_side"


@pytest.mark.asyncio
async def test_level_unlocks_after_earning_star_on_previous_level():
    """
    Verifies that completing Level 1 (>=1 star) unlocks Level 2 ('give_a_reason'),
    allowing Level 2 to start, while Level 3 remains strictly locked (403).
    """
    user_id = f"user-progression-{uuid.uuid4().hex[:8]}"
    token = sign_user_id(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Grant 1 star on take_a_side
    async with async_session_factory() as db:
        from backend.app.persistence.repositories import UserRepository
        user_repo = UserRepository(db)
        await user_repo.get_or_create_user(user_id)
        prog_repo = ProgressRepository(db)
        await prog_repo.record_debate_completion(
            user_id=user_id,
            skill_id="take_a_side",
            stars_earned=1,
            xp_earned=50,
            outcome="user_win",
            streak_extended=True,
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        # Level 2 ('give_a_reason') should now be unlocked
        resp_lvl2 = await client.post(
            "/api/debates/start",
            json={"topicId": "give_a_reason", "side": "agree"},
        )
        assert resp_lvl2.status_code == 200
        assert resp_lvl2.json()["session"]["skillTarget"]["id"] == "give_a_reason"

        # Level 3 ('back_it_up') must still be locked
        resp_lvl3 = await client.post(
            "/api/debates/start",
            json={"topicId": "back_it_up", "side": "agree"},
        )
        assert resp_lvl3.status_code == 403
        assert "locked" in resp_lvl3.json()["detail"].lower()


@pytest.mark.asyncio
async def test_choices_endpoint_never_exposes_locked_topics():
    """
    Verifies that /api/debates/choices only returns topics for unlocked skills.
    """
    user_id = f"user-choices-{uuid.uuid4().hex[:8]}"
    token = sign_user_id(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Populate inventory with topics for an unlocked skill and a locked skill
    async with async_session_factory() as db:
        topic_repo = TopicInventoryRepository(db)
        await topic_repo.add_topics(user_id, [
            {
                "id": "topic-unlocked-1",
                "statement": "Cats are better pets than dogs.",
                "skill_id": "take_a_side",
                "difficulty": "gentle",
            },
            {
                "id": "topic-locked-1",
                "statement": "Nuance topic that should not leak.",
                "skill_id": "nuance",
                "difficulty": "sharp",
            },
        ])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        choices_resp = await client.get("/api/debates/choices")
        assert choices_resp.status_code == 200
        choices = choices_resp.json()
        assert len(choices) > 0

        # Verify no choices belong to locked skills
        for c in choices:
            assert c["skill"] == "take_a_side"
