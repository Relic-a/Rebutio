import asyncio
import logging
from typing import Any, Dict, Optional
from backend.app.config import settings

logger = logging.getLogger("rebutio.modal")


class ModalSpeechClient:
    def __init__(self):
        self._modal_worker = None
        self._initialized = False

    def _get_worker(self):
        if not self._initialized:
            try:
                import modal
                app_name = settings.MODAL_APP_NAME
                cls = modal.Cls.from_name(app_name, "SpeechAnalysisWorker")
                self._modal_worker = cls()
                logger.info(f"Connected to remote Modal SpeechAnalysisWorker on app: {app_name}")
            except Exception as e:
                logger.warning(f"Remote Modal class lookup deferred/unavailable: {e}")
                self._modal_worker = None
            self._initialized = True
        return self._modal_worker

    async def analyze_phonemes(
        self,
        audio_bytes: bytes,
        audio_format: str = "webm",
        client_response_delay_ms: int = 0,
    ) -> Dict[str, Any]:
        """
        Executes DeepFilterNet3 + KoelLabs CTC remotely on Modal.
        Falls back to lightweight synthetic phoneme estimation if remote worker is unavailable.
        """
        if not audio_bytes:
            return {
                "audio_duration_ms": 0,
                "phonemes": [],
                "speech_metrics": {},
                "client_response_delay_ms": client_response_delay_ms,
            }

        try:
            worker = self._get_worker()
            if worker is not None:
                # Call remote Modal function in worker thread
                result = await asyncio.to_thread(
                    worker.analyze_phonemes.remote,
                    audio_bytes=audio_bytes,
                    audio_format=audio_format,
                )
                result["client_response_delay_ms"] = client_response_delay_ms
                return result
        except Exception as e:
            logger.warning(f"Remote Modal speech analysis call failed: {e}. Using fallback evidence.")

        # Fallback simulation for local development / testing when Modal app is not deployed
        duration_ms = max(1000, min(30000, len(audio_bytes) // 32))
        dummy_phonemes = [
            {"phone": "h", "start_ms": 100, "end_ms": 180},
            {"phone": "ɛ", "start_ms": 180, "end_ms": 300},
            {"phone": "l", "start_ms": 300, "end_ms": 420},
            {"phone": "oʊ", "start_ms": 420, "end_ms": 600},
            {"phone": "ð", "start_ms": 700, "end_ms": 780},
            {"phone": "ɪ", "start_ms": 780, "end_ms": 860},
            {"phone": "s", "start_ms": 860, "end_ms": 940},
        ]
        return {
            "audio_duration_ms": duration_ms,
            "phonemes": dummy_phonemes,
            "speech_metrics": {
                "total_phonemes": len(dummy_phonemes),
                "in_speech_gaps_count": 1,
                "total_in_speech_pause_duration_ms": 100,
                "first_phone_offset_ms": 100,
                "last_phone_end_ms": 940,
            },
            "client_response_delay_ms": client_response_delay_ms,
            "is_fallback": True,
        }


modal_speech_client = ModalSpeechClient()
