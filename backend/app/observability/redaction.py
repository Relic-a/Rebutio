import re
from typing import Any, Dict, List, Set, Union

REDACTED_STR = "[REDACTED]"
AUDIO_REDACTED_STR = "[REDACTED_AUDIO]"

# Secret-bearing key patterns (case-insensitive)
# Note: we explicitly preserve token metrics like "input_tokens", "output_tokens", "max_tokens", "total_tokens"
EXACT_SENSITIVE_KEYS: Set[str] = {
    "authorization",
    "auth",
    "api_key",
    "apikey",
    "openrouter_api_key",
    "ramp_router_api_key",
    "hf_token",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "session_secret",
    "rebutio_session_secret",
    "rebutio_data_encryption_key",
    "encryption_key",
    "password",
    "passwd",
    "pwd",
    "cookie",
    "set-cookie",
    "audio",
    "audio_bytes",
    "raw_audio",
    "wav_bytes",
    "mp3_bytes",
    "pcm_bytes",
    "transcript_encrypted",
    "text_encrypted",
    "language_feedback_encrypted",
}

SAFE_TOKEN_METRIC_KEYS: Set[str] = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "max_tokens",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "tokens_per_second",
    "token_count",
}

# Regex patterns for redacting raw authorization/bearer headers in strings
BEARER_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(?:key|token|secret)=([A-Za-z0-9_\-]{16,})", re.IGNORECASE)


def is_sensitive_key(key: str) -> bool:
    low = key.lower()
    if low in SAFE_TOKEN_METRIC_KEYS:
        return False
    if low in EXACT_SENSITIVE_KEYS:
        return True
    # Substring match heuristics
    for sensitive_sub in (
        "api_key",
        "apikey",
        "secret",
        "password",
        "passwd",
        "encryption_key",
        "raw_audio",
        "audio_bytes",
    ):
        if sensitive_sub in low:
            return True
    if low.endswith("_token") and low not in SAFE_TOKEN_METRIC_KEYS:
        return True
    return False


def redact_string(val: str) -> str:
    if not isinstance(val, str):
        return val
    # Redact Bearer tokens in headers or URLs
    cleaned = BEARER_PATTERN.sub(f"Bearer {REDACTED_STR}", val)
    cleaned = API_KEY_PATTERN.sub(r"\1=" + REDACTED_STR, cleaned)
    return cleaned


def redact_value(key: str, val: Any) -> Any:
    low_key = key.lower()

    # Audio byte sequences or buffers
    if "audio" in low_key and isinstance(val, (bytes, bytearray, memoryview)):
        return AUDIO_REDACTED_STR
    if isinstance(val, (bytes, bytearray, memoryview)):
        return f"[BINARY_BYTES len={len(val)}]"

    if is_sensitive_key(key):
        if "audio" in low_key:
            return AUDIO_REDACTED_STR
        return REDACTED_STR

    if isinstance(val, dict):
        return redact_dict(val)
    if isinstance(val, (list, tuple, set)):
        return [redact_value(key, item) for item in val]
    if isinstance(val, str):
        return redact_string(val)
    return val


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    redacted = {}
    for k, v in data.items():
        if is_sensitive_key(str(k)):
            if "audio" in str(k).lower():
                redacted[k] = AUDIO_REDACTED_STR
            else:
                redacted[k] = REDACTED_STR
        elif isinstance(v, dict):
            redacted[k] = redact_dict(v)
        elif isinstance(v, (list, tuple, set)):
            redacted[k] = [redact_value(str(k), item) for item in v]
        elif isinstance(v, str):
            redacted[k] = redact_string(v)
        elif isinstance(v, (bytes, bytearray, memoryview)):
            redacted[k] = AUDIO_REDACTED_STR if "audio" in str(k).lower() else f"[BINARY_BYTES len={len(v)}]"
        else:
            redacted[k] = v
    return redacted


def structlog_redaction_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structlog processor that automatically redacts sensitive fields from all log events.
    """
    return redact_dict(event_dict)
