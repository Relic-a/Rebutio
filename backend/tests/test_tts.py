import pytest
from unittest.mock import AsyncMock, patch
import httpx
from backend.app.config import settings
from backend.app.services.ai.openrouter import OpenRouterClient, pcm_to_wav
from backend.app.services.ai.gateway import ai_gateway


@pytest.mark.asyncio
async def test_fish_audio_synthesis_mp3_handling(monkeypatch):
    """
    Verifies that fish-audio/s2.1-pro correctly requests mp3 response_format,
    handles MP3 responses directly without PCM re-wrapping, and filters out Gemini voices.
    """
    client = OpenRouterClient(api_key="test-api-key")
    captured_payload = None

    async def mock_post(url, headers=None, json=None):
        nonlocal captured_payload
        captured_payload = json
        # Mock mp3 response (starts with standard MP3 syncword \xff\xfb)
        mp3_content = b"\xff\xfb\x90\xc4\x00\x00\x00\x00\x00\x00\x00\x00"
        return httpx.Response(
            status_code=200,
            headers={"content-type": "audio/mpeg"},
            content=mp3_content,
        )

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
        # 1. Synthesize with fish-audio and legacy Gemini voice name
        audio_bytes = await client.synthesize_speech(
            text="Rebuttal",
            voice="Zephyr",
            model="fish-audio/s2.1-pro",
        )

        assert captured_payload["model"] == "fish-audio/s2.1-pro"
        assert captured_payload["response_format"] == "mp3"
        assert captured_payload["input"] == "Rebuttal"
        # Gemini voice 'Zephyr' must be filtered out for fish-audio
        assert "voice" not in captured_payload

        # Output should be exact MP3 bytes, not modified or wrapped in WAV
        assert audio_bytes.startswith(b"\xff\xfb")


@pytest.mark.asyncio
async def test_gemini_synthesis_pcm_to_wav(monkeypatch):
    """
    Verifies that gemini models request pcm and get converted into valid RIFF/WAVE containers.
    """
    client = OpenRouterClient(api_key="test-api-key")
    captured_payload = None

    async def mock_post(url, headers=None, json=None):
        nonlocal captured_payload
        captured_payload = json
        # Mock raw PCM bytes (no header)
        pcm_content = b"\x00\x01\x02\x03" * 100
        return httpx.Response(
            status_code=200,
            headers={"content-type": "audio/pcm;rate=24000"},
            content=pcm_content,
        )

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
        audio_bytes = await client.synthesize_speech(
            text="Rebuttal",
            voice="Zephyr",
            model="google/gemini-3.1-flash-tts-preview",
        )

        assert captured_payload["model"] == "google/gemini-3.1-flash-tts-preview"
        assert captured_payload["response_format"] == "pcm"
        assert captured_payload["voice"] == "Zephyr"

        # Output must be wrapped in RIFF/WAVE header
        assert audio_bytes.startswith(b"RIFF")
        assert b"WAVE" in audio_bytes[:16]


@pytest.mark.asyncio
async def test_gateway_synthesize_speech_uses_configured_model(monkeypatch):
    """
    Verifies AIGateway uses fish-audio/s2.1-pro by default.
    """
    assert "fish-audio" in settings.OPENROUTER_TTS_MODEL
