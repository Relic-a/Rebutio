import json
import logging
from typing import Any, Dict, List, Optional
import httpx
from backend.app.config import settings

logger = logging.getLogger("rebutio.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code != 200:
                logger.error(f"OpenRouter STT error: HTTP {resp.status_code}")
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
        """
        if not self.is_configured:
            raise ValueError("OpenRouter API key not configured")

        model_id = model or settings.OPENROUTER_TTS_MODEL
        voice_name = voice or settings.REBUTIO_TTS_VOICE
        url = f"{self.base_url}/audio/speech"
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        payload = {
            "model": model_id,
            "input": text,
            "voice": voice_name,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"OpenRouter TTS error: HTTP {resp.status_code}")
                resp.raise_for_status()

            return resp.content

    async def chat_completion(
        self,
        messages: List[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format_json: bool = False,
    ) -> str:
        """
        Executes text chat completion with privacy safeguards:
        data_collection = deny, zdr = true.
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
            },
        }

        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"OpenRouter Chat Completion error: HTTP {resp.status_code}")
                resp.raise_for_status()

            res_json = resp.json()
            choices = res_json.get("choices", [])
            if not choices:
                raise ValueError("OpenRouter returned empty choices")
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()


openrouter_client = OpenRouterClient()
