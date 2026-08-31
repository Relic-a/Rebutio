import pytest
from unittest.mock import AsyncMock, patch
import httpx
from backend.app.config import settings
from backend.app.services.ai.gateway import ai_gateway
from backend.app.services.ai.openrouter import openrouter_client


@pytest.mark.asyncio
async def test_transcription_fallback_to_local_stt_on_provider_error(monkeypatch):
    """
    Regression test: When OpenRouter STT returns 402/502/payment error,
    ai_gateway gracefully falls back to local faster-whisper STT without breaking the turn.
    """
    # Mock OpenRouter transcribe_audio to raise an HTTP 402 error
    async def mock_openrouter_transcribe(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "Client error '402 Payment Required'",
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/audio/transcriptions"),
            response=httpx.Response(402, text='{"error":{"message":"balance required"}}'),
        )

    # Mock local STT client to return a recognized transcript
    async def mock_local_transcribe(audio_bytes, audio_format="webm"):
        return "I agree because face to face interaction is essential."

    with patch.object(openrouter_client, "transcribe_audio", side_effect=mock_openrouter_transcribe):
        with patch("backend.app.services.speech.local_stt.local_stt_client.transcribe_audio", side_effect=mock_local_transcribe):
            result = await ai_gateway.transcribe_audio(b"fake_audio_bytes", audio_format="webm")
            assert result == "I agree because face to face interaction is essential."


@pytest.mark.asyncio
async def test_development_model_configuration_overrides():
    """
    Regression test: Verifies that development configuration overrides (:nitro removal, deepgram/flux-tts:free, flux-jack-en)
    are properly honored by settings and AI gateway.
    """
    assert "deepgram" in settings.OPENROUTER_TTS_MODEL or "flux-tts" in settings.OPENROUTER_TTS_MODEL
    assert settings.REBUTIO_TTS_VOICE == "flux-jack-en"
    assert ":nitro" not in settings.OPENROUTER_DEBATE_MODEL
    assert ":nitro" not in settings.OPENROUTER_ANALYSIS_MODEL
    assert ":nitro" not in settings.OPENROUTER_REVIEW_MODEL
    assert ":nitro" not in settings.OPENROUTER_TOPIC_MODEL
    assert ":nitro" not in settings.OPENROUTER_FINAL_PATCH_MODEL
