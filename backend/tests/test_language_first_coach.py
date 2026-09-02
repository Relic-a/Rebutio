import uuid
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.app.api.dependencies import sign_user_id
from backend.app.main import app
from backend.app.models.db import DebateReview, DebateSession, User
from backend.app.models.schemas import (
    CoachOpeningAnalysisResult,
    CoachTurnResponse,
)
from backend.app.persistence.db import async_session_factory
from backend.app.persistence.repositories import (
    CoachRepository,
    DebateSessionRepository,
    UserRepository,
)
from backend.app.prompts.coach import COACH_OPENING_PROMPT, COACH_SYSTEM_PROMPT
from backend.app.prompts.debate_reviewer import DEBATE_REVIEWER_SYSTEM_PROMPT
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.coach.engine import CoachEngine
from backend.app.services.privacy.encryption import encryptor

client = TestClient(app)


def test_coach_and_reviewer_prompt_contracts():
    """Verify system prompts are language-first and mention pronunciation practice."""
    assert "[[pronounce:word or short phrase]]" in COACH_SYSTEM_PROMPT
    assert "spoken-English coach" in COACH_SYSTEM_PROMPT
    assert "[[pronounce:word]]" in COACH_OPENING_PROMPT
    assert "spoken-language evidence" in COACH_OPENING_PROMPT
    assert "Debate adjudication is secondary context for a language-learning app" in DEBATE_REVIEWER_SYSTEM_PROMPT


def test_pronunciation_endpoint_success():
    cookie_val = sign_user_id(f"test-user-pronounce-{uuid.uuid4().hex[:8]}")
    cookies = {"rebutio_session": cookie_val}

    fake_mp3 = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x00fake mp3 audio data"
    with patch.object(ai_gateway, "synthesize_speech", AsyncMock(return_value=fake_mp3)):
        res = client.get("/api/coach/pronunciation?text=consequential", cookies=cookies)
        assert res.status_code == 200
        assert res.content == fake_mp3
        assert res.headers["content-type"] == "audio/mpeg"
        assert "max-age=86400" in res.headers.get("cache-control", "")


def test_pronunciation_endpoint_validation():
    cookie_val = sign_user_id(f"test-user-pronounce-{uuid.uuid4().hex[:8]}")
    cookies = {"rebutio_session": cookie_val}

    # Empty text
    res_empty = client.get("/api/coach/pronunciation?text=   ", cookies=cookies)
    assert res_empty.status_code == 422

    # Text exceeding 60 characters
    long_text = "a" * 61
    res_long = client.get(f"/api/coach/pronunciation?text={long_text}", cookies=cookies)
    assert res_long.status_code == 422


def test_pronunciation_endpoint_service_unavailable():
    cookie_val = sign_user_id(f"test-user-pronounce-{uuid.uuid4().hex[:8]}")
    cookies = {"rebutio_session": cookie_val}

    with patch.object(ai_gateway, "synthesize_speech", AsyncMock(return_value=None)):
        res = client.get("/api/coach/pronunciation?text=test", cookies=cookies)
        assert res.status_code == 503
        assert "temporarily unavailable" in res.json()["detail"]


@pytest.mark.asyncio
async def test_coach_opening_analysis_language_first_context():
    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        session_repo = DebateSessionRepository(db)
        coach_repo = CoachRepository(db)

        uid = f"test-user-{uuid.uuid4().hex[:8]}"
        sid = f"session-{uuid.uuid4().hex[:8]}"
        user = await user_repo.get_or_create_user(uid)
        session = await session_repo.create_session(
            session_id=sid,
            user_id=user.id,
            topic_id="topic-ubi",
            topic_text="Universal Basic Income is essential.",
            skill_id="give_a_reason",
            skill_name="Give a Reason",
            skill_hint="State reasons",
            skill_reminder="Remember reasons",
            difficulty="steady",
            user_side="agree",
            total_user_turns=4,
        )

        # Add turns so evidence assessment passes
        await session_repo.save_turn(
            session_id=session.id,
            turn_number=1,
            speaker="user",
            text="I argue that a universal basic income is essential because it secures economic stability for every citizen in this changing economy.",
            audio_available=True,
            duration_sec=7.0,
        )
        await session_repo.save_turn(
            session_id=session.id,
            turn_number=2,
            speaker="opponent",
            text="However, universal payments may induce severe inflation across basic consumer goods.",
            audio_available=False,
            duration_sec=6.0,
        )
        await session_repo.save_turn(
            session_id=session.id,
            turn_number=3,
            speaker="user",
            text="Furthermore, automated industries make social safety nets increasingly critical for future generations.",
            audio_available=True,
            duration_sec=6.5,
        )

        # Save review with language feedback
        review = DebateReview(
            session_id=session.id,
            user_id=user.id,
            outcome="user_win",
            score_technique=8,
            score_grammar=9,
            score_vocabulary=7,
            score_delivery=8,
            strongest_moment="Clear phonetic contrast in [[pronounce:inevitable]]",
            improvement_opportunity="Practice the vowel sound in [[pronounce:economy]]",
            language_feedback_encrypted=encryptor.encrypt_json({
                "pronunciation_findings": [
                    {"sound": "/iː/", "heard_in": ["economy"], "note": "Vowel reduction needed"}
                ],
                "grammar_findings": [],
                "vocabulary_findings": [],
            }),
        )
        db.add(review)
        await db.commit()

        captured_messages = []

        async def fake_structured_completion(*args, **kwargs):
            nonlocal captured_messages
            messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
            captured_messages = messages
            return CoachOpeningAnalysisResult(
                overall_assessment="Your spoken clarity was strong, with practice needed on [[pronounce:economy]].",
                most_important_strength="Vowel clarity in [[pronounce:inevitable]].",
                highest_value_improvement="Work on vowel reduction in [[pronounce:economy]].",
                concrete_example="I think this economy is inevitable.",
                evidence_turn_number=1,
                suggested_quick_replies=["Can we drill the word economy?"],
            )

        with patch.object(ai_gateway, "_execute_structured_completion", side_effect=fake_structured_completion):
            thread = await CoachEngine.get_or_create_debate_coach_thread(db, user.id, session.id)
            assert thread is not None
            messages = await coach_repo.get_thread_messages(thread.id)
            assert len(messages) >= 1
            opening_msg = messages[0]
            assert opening_msg.message_type == "opening_analysis"
            data = opening_msg.structured_data_json
            assert "[[pronounce:economy]]" in data["overall_assessment"]
            assert "[[pronounce:inevitable]]" in data["most_important_strength"]

            # Verify prompt received decrypted language_feedback
            prompt_str = str(captured_messages)
            assert "economy" in prompt_str


@pytest.mark.asyncio
async def test_coach_session_turn_receives_language_feedback_context():
    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        session_repo = DebateSessionRepository(db)
        coach_repo = CoachRepository(db)

        uid = f"test-user-{uuid.uuid4().hex[:8]}"
        sid = f"session-{uuid.uuid4().hex[:8]}"
        user = await user_repo.get_or_create_user(uid)
        session = await session_repo.create_session(
            session_id=sid,
            user_id=user.id,
            topic_id="topic-ai",
            topic_text="AI safety is paramount.",
            skill_id="give_a_reason",
            skill_name="Give a Reason",
            skill_hint="State reasons",
            skill_reminder="Remember reasons",
            difficulty="steady",
            user_side="agree",
            total_user_turns=4,
        )

        review = DebateReview(
            session_id=session.id,
            user_id=user.id,
            outcome="user_win",
            score_technique=8,
            score_grammar=9,
            score_vocabulary=7,
            score_delivery=8,
            strongest_moment="Precise articulation of technical terminology.",
            improvement_opportunity="Slow down when transitioning between paragraphs.",
            language_feedback_encrypted=encryptor.encrypt_json({
                "pronunciation_findings": [{"sound": "/θ/", "heard_in": ["threshold"], "note": "Clear th-sound"}],
            }),
        )
        db.add(review)
        await db.commit()

        # Initialize thread
        thread = await coach_repo.get_or_create_debate_thread(user.id, session.id, "AI Safety")

        captured_messages = []

        async def fake_turn_completion(*args, **kwargs):
            nonlocal captured_messages
            messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
            captured_messages = messages
            return CoachTurnResponse(
                reply_text="Let's practice pronouncing [[pronounce:threshold]] with a clear /θ/ sound.",
                requested_tool=None,
                tool_args=None,
                evidence_card=None,
                quick_replies=["Here is my attempt: threshold"],
                memory_update=None,
            )

        with patch.object(ai_gateway, "_execute_structured_completion", side_effect=fake_turn_completion):
            coach_reply = await CoachEngine.process_user_text_message(
                db=db,
                user_id=user.id,
                thread_id=thread.id,
                text="How can I improve my pronunciation?",
            )
            assert coach_reply.sender == "coach"
            assert "[[pronounce:threshold]]" in coach_reply.text

            # Check that language_feedback was fed into the prompt context
            prompt_str = str(captured_messages)
            assert "threshold" in prompt_str
