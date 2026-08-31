import asyncio
import json
import pytest
from httpx import ASGITransport, AsyncClient
import structlog
from structlog.testing import capture_logs

from backend.app.config import settings
from backend.app.main import app
from backend.app.observability.context import (
    bind_context,
    bound_context,
    clear_context,
    get_current_context,
)
from backend.app.observability.diagnostics import (
    compute_sha256,
    detect_prompt_leak,
    extract_message_structure,
    format_sensitive_debug,
)
from backend.app.observability.logging import get_logger, setup_logging
from backend.app.observability.prompts import get_prompt_version
from backend.app.observability.redaction import (
    is_sensitive_key,
    redact_dict,
    redact_string,
    redact_value,
)
from backend.app.observability.timing import log_duration
from backend.app.persistence.db import init_db


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()


def test_redaction_secrets_and_preservation_of_token_metrics():
    # Sensitive keys must be redacted
    sensitive_data = {
        "authorization": "Bearer secret_token_123456789",
        "api_key": "sk-or-v1-9876543210abcdef",
        "openrouter_api_key": "sk-or-v1-1234567890",
        "token": "sensitive_session_token_xyz",
        "hf_token": "hf_secret_token_abc",
        "rebutio_data_encryption_key": "0123456789abcdef",
        "password": "mypassword",
        "cookie": "session=rebutio_secret",
        "audio_bytes": b"RIFF....WAVEfmt ",
        "raw_audio": b"\x00\x01\x02\x03",
        # Token metrics MUST NOT be redacted
        "input_tokens": 512,
        "output_tokens": 128,
        "total_tokens": 640,
        "max_tokens": 1024,
        "tokens_per_second": 35.4,
        # Normal fields
        "role": "debate_opponent",
        "model": "deepseek/deepseek-v4-pro-0813:nitro",
        "turn_number": 1,
    }

    redacted = redact_dict(sensitive_data)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["openrouter_api_key"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["hf_token"] == "[REDACTED]"
    assert redacted["rebutio_data_encryption_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["audio_bytes"] == "[REDACTED_AUDIO]"
    assert redacted["raw_audio"] == "[REDACTED_AUDIO]"

    # Token metrics are preserved
    assert redacted["input_tokens"] == 512
    assert redacted["output_tokens"] == 128
    assert redacted["total_tokens"] == 640
    assert redacted["max_tokens"] == 1024
    assert redacted["tokens_per_second"] == 35.4

    assert redacted["role"] == "debate_opponent"
    assert redacted["model"] == "deepseek/deepseek-v4-pro-0813:nitro"


def test_bearer_token_string_redaction():
    text_with_bearer = "Sending request with header Authorization: Bearer sk-or-v1-abcdef1234567890 to endpoint"
    cleaned = redact_string(text_with_bearer)
    assert "sk-or-v1-abcdef1234567890" not in cleaned
    assert "Bearer [REDACTED]" in cleaned


def test_context_propagation_async_isolation():
    clear_context()
    assert get_current_context() == {}

    bind_context(request_id="req_123", session_id="sess_abc", turn_id=1)
    ctx = get_current_context()
    assert ctx["request_id"] == "req_123"
    assert ctx["session_id"] == "sess_abc"
    assert ctx["turn_id"] == 1

    with bound_context(turn_id=2, background_task_id="task_999"):
        nested = get_current_context()
        assert nested["turn_id"] == 2
        assert nested["background_task_id"] == "task_999"
        assert nested["request_id"] == "req_123"

    restored = get_current_context()
    assert restored["turn_id"] == 1
    assert "background_task_id" not in restored
    clear_context()


@pytest.mark.asyncio
async def test_concurrent_context_isolation():
    async def worker(worker_id: int):
        clear_context()
        bind_context(request_id=f"req_{worker_id}", user_id=f"user_{worker_id}")
        await asyncio.sleep(0.01)
        ctx = get_current_context()
        assert ctx["request_id"] == f"req_{worker_id}"
        assert ctx["user_id"] == f"user_{worker_id}"

    tasks = [worker(i) for i in range(10)]
    await asyncio.gather(*tasks)
    clear_context()


def test_extract_message_structure():
    messages = [
        {"role": "system", "content": "You are Rebutio debate partner."},
        {"role": "user", "content": "I think social media is beneficial."},
        {"role": "assistant", "content": "While convenience exists, intimacy suffers."},
        {"role": "user", "content": "People can still call each other."},
    ]

    struct_meta = extract_message_structure(messages, structured_output=False)
    assert struct_meta.message_count == 4
    assert struct_meta.system_message_count == 1
    assert struct_meta.user_message_count == 2
    assert struct_meta.assistant_message_count == 1
    assert struct_meta.message_roles == ["system", "user", "assistant", "user"]
    assert len(struct_meta.message_structures) == 4
    assert struct_meta.message_structures[0]["role"] == "system"
    assert struct_meta.message_structures[0]["chars"] == len(messages[0]["content"])
    assert "sha256" in struct_meta.message_structures[0]
    # Ensure content itself is NOT in metadata
    assert "content" not in struct_meta.message_structures[0]


def test_prompt_leak_detection_heuristics():
    # Obvious prompt leak containing instruction language
    leaked_output_1 = (
        "Rebutio responds\n\n"
        "Rebutio must speak first and open the debate. Rebutio must NOT wait for the user to speak first.\n\n"
        "Rebutio should deliver an opening argument supporting DISAGREE..."
    )
    report_1 = detect_prompt_leak(leaked_output_1)
    assert report_1.is_leak_suspected is True
    assert report_1.confidence == "high"
    assert len(report_1.matched_patterns) >= 2

    # Obvious leak with system prompt headings
    leaked_output_2 = (
        "YOUR IDENTITY: You are strictly the user's debate opponent. "
        "OUTPUT CONSTRAINTS: Speak approximately 2 to 4 sentences."
    )
    report_2 = detect_prompt_leak(leaked_output_2)
    assert report_2.is_leak_suspected is True
    assert report_2.confidence == "high"

    # Normal debate argument containing conversational 'must' - MUST NOT trigger leak alert
    normal_argument = (
        "While technology provides instant communication, we must distinguish between speed and depth. "
        "Real friendships require shared physical vulnerability that screens inherently diminish."
    )
    report_normal = detect_prompt_leak(normal_argument)
    assert report_normal.is_leak_suspected is False
    assert report_normal.confidence in ("none", "low")


def test_prompt_versions_explicit():
    assert get_prompt_version("debate_opponent") == "debate_opponent:v1"
    assert get_prompt_version("topic_generator") == "topic_generator:v1"
    assert get_prompt_version("language_analysis") == "language_analysis:v1"
    assert get_prompt_version("final_language_patch") == "final_language_patch:v1"
    assert get_prompt_version("debate_reviewer") == "debate_reviewer:v1"


def test_sensitive_debug_formatting():
    # Bounded truncation
    long_str = "a" * 500
    debug_snippet = format_sensitive_debug(long_str, max_chars=50)
    assert debug_snippet.startswith("[SENSITIVE_DEBUG: ")
    assert "total_len=500" in debug_snippet
    assert len(debug_snippet) < 120


@pytest.mark.asyncio
async def test_timing_helper():
    test_logger = get_logger("test_timing")
    with capture_logs() as cap_logs:
        async with log_duration("speech.transcription", logger=test_logger):
            await asyncio.sleep(0.01)

    completed_events = [l for l in cap_logs if l.get("event") == "speech.transcription.completed"]
    assert len(completed_events) == 1
    assert "duration_ms" in completed_events[0]
    assert completed_events[0]["duration_ms"] > 0


@pytest.mark.asyncio
async def test_request_id_generation_and_header_propagation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Request without incoming ID -> backend generates req_xxx and returns in X-Request-ID
        resp = await client.get("/health")
        assert resp.status_code == 200
        req_id = resp.headers.get("X-Request-ID")
        assert req_id is not None
        assert req_id.startswith("req_")

        # Request with client-supplied X-Request-ID -> backend preserves it
        custom_id = "client_custom_req_998877"
        resp2 = await client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp2.status_code == 200
        assert resp2.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_no_raw_audio_or_user_speech_in_normal_logs():
    with capture_logs() as cap_logs:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/onboarding/spar/start?side=agree",
            )
            assert resp.status_code == 200
            session_id = resp.json()["session"]["id"]

            turn_resp = await client.post(
                f"/api/sessions/{session_id}/turns",
                data={"transcript": "Social media makes relationships superficial.", "client_response_delay_ms": 1000},
            )
            assert turn_resp.status_code == 200

    # Inspect captured logs to ensure no raw transcripts or audio leaks
    for log_entry in cap_logs:
        log_str = json.dumps(log_entry)
        # Should not contain raw user transcript in normal logs
        assert "Social media makes relationships superficial." not in log_str
        # Should not contain raw audio bytes or base64 audio
        assert "RIFF" not in log_str
        assert "audio_bytes" not in log_entry or log_entry["audio_bytes"] == "[REDACTED_AUDIO]"
