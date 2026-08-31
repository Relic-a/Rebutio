import asyncio
import os
import tempfile
from typing import Optional
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.local_stt")


class LocalSTTClient:
    def __init__(self, model_size: str = "tiny.en"):
        self.model_size = model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                logger.info("local_stt.model_loaded", model=self.model_size)
            except Exception as e:
                logger.error("local_stt.model_load_failed", error=str(e))
                raise
        return self._model

    def _sync_transcribe(self, audio_bytes: bytes, audio_format: str = "webm") -> str:
        model = self._get_model()
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            segments, info = model.transcribe(tmp_path, beam_size=5, language="en")
            text = " ".join([seg.text for seg in segments]).strip()
            return text
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def transcribe_audio(self, audio_bytes: bytes, audio_format: str = "webm") -> str:
        return await asyncio.to_thread(self._sync_transcribe, audio_bytes, audio_format)


local_stt_client = LocalSTTClient()
