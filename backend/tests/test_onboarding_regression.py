import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
import structlog
from structlog.testing import capture_logs

from backend.app.main import app
from backend.app.observability.diagnostics import detect_prompt_leak
from backend.app.persistence.db import init_db
from backend.app.prompts.debate_opponent import build_opponent_prompt
from backend.app.services.ai.config import AICompletionResult
from backend.app.services.ai.gateway import ai_gateway


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


def test_build_opponent_prompt_anchoring():
    # Empty turn history (opening turn) must be anchored with a user turn
    prompt_messages = build_opponent_prompt(
        topic="Social media has made friendships worse.",
        opponent_side="disagree",
        user_side="agree",
        skill_name="Counterpoint",
        difficulty="gentle",
        intensity="balanced",
        turn_history=[],
        current_turn_number=1,
        total_turns=3,
    )
    assert len(prompt_messages) >= 2
    assert prompt_messages[0]["role"] == "system"
    assert prompt_messages[1]["role"] == "user"
    assert "Social media has made friendships worse." in prompt_messages[1]["content"]
    assert "DISAGREE" in prompt_messages[1]["content"]

    # System prompt strictly prohibits third-person meta-commentary / stage directions
    system_text = prompt_messages[0]["content"]
    assert "NEVER output third-person meta-commentary" in system_text
    assert "Rebutio responds" in system_text
    assert "Speak approximately 2 to 4 sentences" in system_text


@pytest.mark.asyncio
async def test_onboarding_opening_turn_regression():
    """
    Test onboarding opening turn execution:
    - Verifies response is an actual opponent argument
    - Verifies no system/developer instructions leaked
    - Verifies length constraint (2 to 4 sentences)
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Start Onboarding Spar
        spar_resp = await client.post("/api/onboarding/spar/start?side=agree")
        assert spar_resp.status_code == 200
        spar_data = spar_resp.json()
        session_id = spar_data["session"]["id"]
        assert spar_data["session"]["totalUserTurns"] == 3

        # 2. Submit First User Turn
        user_text = "I believe social media has made friendships worse because superficial likes replace deep conversations."
        turn_resp = await client.post(
            f"/api/sessions/{session_id}/turns",
            data={
                "transcript": user_text,
                "client_response_delay_ms": 1200,
                "turn_index": 1,
            },
        )
        assert turn_resp.status_code == 200
        res_data = turn_resp.json()
        assert res_data["finished"] is False
        assert res_data["nextUserTurnNumber"] == 2
        assert res_data["opponentTurn"] is not None

        opp_text = res_data["opponentTurn"]["text"]
        assert opp_text is not None

        # Diagnostic check for prompt leak
        leak_report = detect_prompt_leak(opp_text)
        assert leak_report.is_leak_suspected is False, f"Prompt leak detected in opponent turn: {leak_report.matched_patterns}"

        # Check that system instructions / prompt directives are not in opponent text
        forbidden_phrases = [
            "Rebutio responds",
            "Rebutio must speak first",
            "Rebutio must NOT wait",
            "Rebutio should deliver an opening argument",
            "YOUR IDENTITY:",
            "OUTPUT CONSTRAINTS",
            "Target Skill Focus:",
            "system_prompt",
            "openrouter",
            "router_com",
            "markdown",
        ]
        for phrase in forbidden_phrases:
            assert phrase.lower() not in opp_text.lower(), f"Forbidden phrase '{phrase}' found in opponent text: {opp_text}"

        # Sentence count check (2-4 sentences)
        sentences = [s.strip() for s in opp_text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        assert 2 <= len(sentences) <= 4, f"Expected 2-4 sentences, got {len(sentences)}: {opp_text}"


@pytest.mark.asyncio
async def test_prompt_leak_guardrail_fallback_trigger():
    """
    Simulates a rogue upstream LLM returning prompt instructions.
    Asserts that the prompt-leak heuristic detects it, emits a warning log,
    and falls back to a clean curated response rather than leaking instructions to the user.
    """
    leaked_response_content = (
        "Rebutio responds:\n\n"
        "Rebutio must speak first and open the debate. Rebutio must NOT wait for the user to speak first.\n\n"
        "Rebutio should deliver an opening argument supporting DISAGREE on the motion."
    )

    mock_raw_result = AICompletionResult(
        content=leaked_response_content,
        input_tokens=100,
        output_tokens=35,
        provider_request_id="gen-mock-123",
        finish_reason="stop",
        resolved_model="deepseek/deepseek-v4-pro-0813:nitro",
        upstream_provider="openrouter",
    )

    with capture_logs() as cap_logs:
        with patch.object(ai_gateway.openrouter, "chat_completion_raw", new_callable=AsyncMock) as mock_openrouter, \
             patch.object(ai_gateway.router_com, "chat_completion_raw", new_callable=AsyncMock) as mock_router_com:
            
            mock_openrouter.return_value = mock_raw_result
            mock_router_com.return_value = mock_raw_result

            # Attempt to generate debate response
            result_text = await ai_gateway.generate_debate_response(
                messages=[{"role": "user", "content": "I agree with the motion."}],
                current_turn=1,
            )

    # 1. Verify warning log was emitted
    leak_logs = [l for l in cap_logs if l.get("event") == "ai.prompt_leak_suspected"]
    assert len(leak_logs) >= 1
    assert leak_logs[0]["confidence"] == "high"

    # 2. Verify fallback was triggered
    fallback_logs = [l for l in cap_logs if l.get("event") == "ai.provider_fallback" and l.get("to_provider") == "static_fallback"]
    assert len(fallback_logs) == 1

    # 3. Verify returned text is clean and does NOT contain leaked instructions
    assert "Rebutio must speak first" not in result_text
    assert "Rebutio should deliver" not in result_text
    assert len(result_text) > 20
    assert detect_prompt_leak(result_text).is_leak_suspected is False
