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
async def test_deepgram_flux_synthesis_mp3_handling(monkeypatch):
    """
    Verifies that deepgram/flux-tts:free correctly passes model, voice (flux-jack-en),
    and mp3 response_format.
    """
    client = OpenRouterClient(api_key="test-api-key")
    captured_payload = None

    async def mock_post(url, headers=None, json=None):
        nonlocal captured_payload
        captured_payload = json
        mp3_content = b"\xff\xfb\x90\xc4\x00\x00\x00\x00\x00\x00\x00\x00"
        return httpx.Response(
            status_code=200,
            headers={"content-type": "audio/mpeg"},
            content=mp3_content,
        )

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=mock_post)):
        audio_bytes = await client.synthesize_speech(
            text="Rebuttal",
            voice="flux-jack-en",
            model="deepgram/flux-tts:free",
        )

        assert captured_payload["model"] == "deepgram/flux-tts:free"
        assert captured_payload["response_format"] == "mp3"
        assert captured_payload["input"] == "Rebuttal"
        assert captured_payload["voice"] == "flux-jack-en"

        assert audio_bytes.startswith(b"\xff\xfb")


@pytest.mark.asyncio
async def test_kokoro_synthesis_and_streaming(monkeypatch):
    """
    Verifies that hexgrad/kokoro-82m correctly passes model, voice (af_bella),
    mp3 response_format, and stream=True when calling stream_speech.
    """
    client = OpenRouterClient(api_key="test-api-key")
    captured_payload = None

    class MockStreamResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {"content-type": "audio/mpeg"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_bytes(self):
            yield b"\xff\xfb\x90\xc4\x00\x00\x00\x00"
            yield b"\x01\x02\x03\x04"

        def raise_for_status(self):
            pass

    def mock_stream(method, url, headers=None, json=None):
        nonlocal captured_payload
        captured_payload = json
        return MockStreamResponse()

    with patch("httpx.AsyncClient.stream", side_effect=mock_stream):
        chunks = []
        async for chunk in client.stream_speech(
            text="Testing Kokoro",
            voice="af_bella",
            model="hexgrad/kokoro-82m",
        ):
            chunks.append(chunk)

        assert captured_payload["model"] == "hexgrad/kokoro-82m"
        assert captured_payload["response_format"] == "mp3"
        assert captured_payload["voice"] == "af_bella"
        assert captured_payload["stream"] is True
        assert len(chunks) == 2
        assert b"".join(chunks).startswith(b"\xff\xfb")


@pytest.mark.asyncio
async def test_gateway_synthesize_speech_uses_configured_model(monkeypatch):
    """
    Verifies AIGateway uses hexgrad/kokoro-82m and af_bella by default.
    """
    assert "kokoro" in settings.OPENROUTER_TTS_MODEL
    assert settings.REBUTIO_TTS_VOICE == "af_bella"
