import io
import json
from typing import Any, Dict, List, Optional
import wave
import httpx
from backend.app.config import settings
from backend.app.observability.logging import get_logger
from backend.app.services.ai.config import AICompletionResult

logger = get_logger("rebutio.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wraps raw 16-bit PCM audio bytes in a standard RIFF/WAVE container header."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return wav_io.getvalue()


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://rebutio.app",
            "X-Title": "Rebutio Spoken English Debate",
        }

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        audio_format: str = "webm",
        model: Optional[str] = None,
    ) -> str:
        """
        Transcribes raw audio using OpenRouter's dedicated STT endpoint with MAI-Transcribe.
        Sends original raw audio bytes with English language hint.
        """
        if not self.is_configured:
            raise ValueError("OpenRouter API key not configured")

        model_id = model or settings.OPENROUTER_TRANSCRIPTION_MODEL
        url = f"{self.base_url}/audio/transcriptions"
        headers = self._get_headers()

        mime_map = {
            "webm": "audio/webm",
            "mp4": "audio/mp4",
            "wav": "audio/wav",
            "ogg": "audio/ogg",
            "m4a": "audio/m4a",
        }
        mime_type = mime_map.get(audio_format.lower(), "audio/webm")
        filename = f"turn_audio.{audio_format.lower()}"

        files = {
            "file": (filename, audio_bytes, mime_type),
        }
        data = {
            "model": model_id,
            "language": "en",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                logger.error("openrouter.stt.error", status_code=resp.status_code)
                resp.raise_for_status()

            result = resp.json()
            return result.get("text", "").strip()

    async def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
    ) -> bytes:
        """
        Synthesizes speech using OpenRouter's dedicated TTS endpoint.
        Handles both MP3-compatible models (Fish Audio S2.1 Pro, etc.) and raw PCM outputs
        (Gemini Flash TTS), packaging PCM into valid browser-playable WAV containers.
        """
        if not self.is_configured:
            raise ValueError("OpenRouter API key not configured")

        model_id = model or settings.OPENROUTER_TTS_MODEL
        voice_name = voice if voice is not None else settings.REBUTIO_TTS_VOICE
        url = f"{self.base_url}/audio/speech"
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        is_gemini = "gemini" in model_id.lower()
        is_fish = "fish" in model_id.lower()
        fmt = "pcm" if is_gemini else "mp3"

        payload: Dict[str, Any] = {
            "model": model_id,
            "input": text,
            "response_format": fmt,
        }

        # Filter out Gemini preset voice names if model is Fish Audio or doesn't support them
        gemini_presets = {"zephyr", "puck", "aoede", "charon", "kore", "fenrir"}
        if voice_name and str(voice_name).strip():
            cleaned_voice = str(voice_name).strip()
            if is_fish and cleaned_voice.lower() in gemini_presets:
                # Omit voice parameter for Fish Audio so OpenRouter uses the default voice
                pass
            else:
                payload["voice"] = cleaned_voice
        elif is_gemini:
            payload["voice"] = "Zephyr"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("openrouter.tts.error", status_code=resp.status_code, error_body=resp.text[:300])
                resp.raise_for_status()

            raw_bytes = resp.content
            content_type = resp.headers.get("content-type", "").lower()

            # If response is already standard MP3 or WAV, return bytes directly
            if raw_bytes.startswith(b"ID3") or raw_bytes.startswith(b"\xff\xfb") or raw_bytes.startswith(b"RIFF") or "audio/mpeg" in content_type:
                return raw_bytes

            # If response is raw PCM, package into standard WAV container
            sample_rate = 24000
            if "rate=" in content_type:
                try:
                    sample_rate = int(content_type.split("rate=")[1].split(";")[0])
                except Exception:
                    sample_rate = 44100 if is_fish else 24000
            elif is_fish:
                sample_rate = 44100

            return pcm_to_wav(raw_bytes, sample_rate=sample_rate, channels=1, sample_width=2)

    async def chat_completion_raw(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
    ) -> AICompletionResult:
        """
        Executes text chat completion with privacy safeguards:
        data_collection = deny, zdr = true, require_parameters = true.
        Returns AICompletionResult with content and usage/request metadata.
        """
        if not self.is_configured:
            raise ValueError("OpenRouter API key not configured")

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "provider": {
                "data_collection": "deny",
                "zdr": True,
                "require_parameters": True,
            },
        }

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("openrouter.chat.error", status_code=resp.status_code)
                resp.raise_for_status()

            res_json = resp.json()
            choices = res_json.get("choices", [])
            if not choices:
                raise ValueError("OpenRouter returned empty choices")

            first_choice = choices[0]
            content = first_choice.get("message", {}).get("content", "").strip()
            finish_reason = first_choice.get("finish_reason")
            
            usage = res_json.get("usage", {})
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            
            provider_req_id = res_json.get("id") or resp.headers.get("x-request-id")
            resolved_model = res_json.get("model")
            upstream_provider = res_json.get("provider")

            return AICompletionResult(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider_request_id=provider_req_id,
                finish_reason=finish_reason,
                resolved_model=resolved_model,
                upstream_provider=upstream_provider,
            )

    async def chat_completion(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
    ) -> str:
        result = await self.chat_completion_raw(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format_json=response_format_json,
        )
        return result.content


openrouter_client = OpenRouterClient()
