import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.config import settings
from backend.app.services.ai.config import ModelRole, get_role_candidates, AICompletionResult
from backend.app.domain.evidence import (
    assess_debate_evidence,
    MIN_SUBSTANTIVE_USER_TURNS,
    MIN_SUBSTANTIVE_USER_WORDS,
    MIN_SINGLE_TURN_WORDS,
)
from backend.app.persistence.db import async_session_factory
from backend.app.persistence.repositories import (
    DebateSessionRepository,
    ProgressRepository,
    CoachRepository,
)
from backend.tests.test_auth_security_and_durability import create_test_auth_token


def test_role_reasoning_configuration():
    """
    Verifies that model candidates for all roles are configured with appropriate
    reasoning effort and adequate generation token budgets.
    """
    # 1. Debate Opponent: medium reasoning, larger budget
    opponent_cands = get_role_candidates(ModelRole.DEBATE_OPPONENT)
    assert len(opponent_cands) > 0
    for cand in opponent_cands:
        assert cand.reasoning_effort == "medium"
        assert cand.max_tokens >= 2048

    # 2. Debate Reviewer: medium reasoning, much larger budget
    reviewer_cands = get_role_candidates(ModelRole.DEBATE_REVIEWER)
    assert len(reviewer_cands) > 0
    for cand in reviewer_cands:
        assert cand.reasoning_effort == "medium"
        assert cand.max_tokens >= 4096

    # 3. Language Analysis: medium reasoning, larger budget
    analysis_cands = get_role_candidates(ModelRole.LANGUAGE_ANALYSIS)
    assert len(analysis_cands) > 0
    for cand in analysis_cands:
        assert cand.reasoning_effort == "medium"
        assert cand.max_tokens >= 4096

    # 4. Final Language Patch: low/medium reasoning
    patch_cands = get_role_candidates(ModelRole.FINAL_LANGUAGE_PATCH)
    assert len(patch_cands) > 0
    for cand in patch_cands:
        assert cand.reasoning_effort in ("low", "medium")
        assert cand.max_tokens >= 3500

    # 5. Topic Generator: low reasoning
    topic_cands = get_role_candidates(ModelRole.TOPIC_GENERATOR)
    assert len(topic_cands) > 0
    for cand in topic_cands:
        assert cand.reasoning_effort == "low"

    # 6. Coach: low reasoning
    coach_cands = get_role_candidates(ModelRole.COACH)
    assert len(coach_cands) > 0
    for cand in coach_cands:
        assert cand.reasoning_effort == "low"
        assert cand.max_tokens >= 2500

    # 7. JSON Repair: no/minimal reasoning
    json_cands = get_role_candidates(ModelRole.JSON_REPAIR)
    assert len(json_cands) > 0
    for cand in json_cands:
        assert cand.reasoning_effort == "none"


def test_assess_debate_evidence_deterministic_rules():
    """
    Tests deterministic boundary rules for sufficient argumentation and audio evidence.
    """
    # 1. User says only "tell me, why not?" (4 words, 1 turn) -> Insufficient
    insufficient_turns = [
        {"speaker": "opponent", "text": "Why should we change this policy?"},
        {"speaker": "user", "text": "tell me, why not?", "audio_available": False, "duration_sec": 0.0},
    ]
    ev = assess_debate_evidence(insufficient_turns)
    assert ev.has_sufficient_evidence is False
    assert ev.has_sufficient_delivery_evidence is False
    assert ev.total_user_words == 4
    assert ev.substantive_turns_count == 0

    # 2. User has 2 very short turns (e.g. "yes" and "I agree") -> 3 words total -> Insufficient
    two_short_turns = [
        {"speaker": "user", "text": "yes"},
        {"speaker": "opponent", "text": "Elaborate."},
        {"speaker": "user", "text": "I agree"},
    ]
    ev2 = assess_debate_evidence(two_short_turns)
    assert ev2.has_sufficient_evidence is False
    assert ev2.total_user_words == 3

    # 3. User has 2 substantive turns (>= 5 words each) with total words >= 20 -> Sufficient
    substantive_turns = [
        {"speaker": "user", "text": "The main problem is that current incentives favor short-term profits over public safety.", "audio_available": True, "duration_sec": 4.5},
        {"speaker": "opponent", "text": "Regulations could stifle innovation."},
        {"speaker": "user", "text": "Safety regulations establish minimum baselines without preventing healthy competitive research.", "audio_available": True, "duration_sec": 5.0},
    ]
    ev3 = assess_debate_evidence(substantive_turns)
    assert ev3.has_sufficient_evidence is True
    assert ev3.has_sufficient_delivery_evidence is True
    assert ev3.substantive_turns_count == 2
    assert ev3.total_user_words >= 20

    # 4. Text-only debate with sufficient words -> Sufficient evidence but NO delivery evidence
    text_only_turns = [
        {"speaker": "user", "text": "The main problem is that current incentives favor short-term profits over public safety.", "audio_available": False, "duration_sec": 0.0},
        {"speaker": "opponent", "text": "Regulations could stifle innovation."},
        {"speaker": "user", "text": "Safety regulations establish minimum baselines without preventing healthy competitive research.", "audio_available": False, "duration_sec": 0.0},
    ]
    ev4 = assess_debate_evidence(text_only_turns)
    assert ev4.has_sufficient_evidence is True
    assert ev4.has_sufficient_delivery_evidence is False


@pytest.mark.asyncio
async def test_insufficient_evidence_debate_evaluation_and_coach():
    """
    End-to-end test simulating the exact scenario reported by the user:
    User starts debate, says only 'tell me, why not?', and finishes the debate.
    Verifies:
    - outcome is 'undetermined'
    - stars is 0
    - xpEarned is 0
    - scores are None (unrated / no fake 8s)
    - strongestMoment is None / no fake praise
    - coach opening explains there was not enough material
    - coach conversation receives transcript and evidence status
    """
    user_id = f"user-insufficient-{uuid.uuid4().hex[:8]}"
    token = create_test_auth_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start debate
        start_resp = await client.post("/api/debates/start", json={"side": "agree", "onboarding": True}, headers=headers)
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session"]["id"]

        # Submit short turn: "tell me, why not?"
        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={"transcript": "tell me, why not?", "turn_index": 1},
            headers=headers,
        )
        assert turn_resp.status_code == 200

        # Finish debate
        finish_resp = await client.post(f"/api/sessions/{session_id}/finish", headers=headers)
        assert finish_resp.status_code == 200

        # Retrieve review
        review_resp = await client.get(f"/api/sessions/{session_id}/review", headers=headers)
        assert review_resp.status_code == 200
        rev = review_resp.json()

        # 1. Outcome must be undetermined
        assert rev["outcome"] == "undetermined"
        # 2. Stars must be 0
        assert rev["stars"]["stars"] == 0
        # 3. XP must be 0
        assert rev["xpEarned"] == 0
        # 4. Streak must not be extended
        assert rev["streakExtended"] is False
        # 5. Scores must not be fake 8s (must be None / 0)
        assert rev["scoreTechnique"]["score"] is None or rev["scoreTechnique"]["score"] == 0
        assert rev["scoreGrammar"]["score"] is None or rev["scoreGrammar"]["score"] == 0
        assert rev["scoreVocabulary"]["score"] is None or rev["scoreVocabulary"]["score"] == 0
        assert rev["scoreDelivery"]["score"] is None or rev["scoreDelivery"]["score"] == 0
        # 6. No fake strongest moment
        assert rev["strongestMoment"] is None

        # Verify DB progress was NOT awarded fake XP or completed count
        async with async_session_factory() as db:
            prog_repo = ProgressRepository(db)
            coach_repo = CoachRepository(db)
            prog = await prog_repo.get_progress(user_id)
            assert prog.xp == 0
            assert prog.debates_completed == 0
            assert prog.wins == 0

            # Verify coach thread opening analysis
            threads = await coach_repo.list_threads(user_id)
            thread = next((th for th in threads if th.session_id == session_id), None)
            assert thread is not None
            messages = await coach_repo.get_thread_messages(thread.id)
            assert len(messages) > 0
            opening_msg = next((m for m in messages if m.message_type == "opening_analysis"), None)
            assert opening_msg is not None
            # Structured opening data must reflect insufficient material
            opening_data = opening_msg.structured_data_json
            assert "not enough" in opening_data["overall_assessment"].lower() or "insufficient" in opening_data["overall_assessment"].lower()
