import asyncio
import time
from typing import Any, Dict, Optional
from backend.app.config import settings
from backend.app.observability.context import get_current_context
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.modal")


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
                logger.info("modal.worker.connected", app_name=app_name)
            except Exception as e:
                logger.warning("modal.worker.lookup_deferred", error=str(e))
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
        Logs safe structural metrics without dumping audio or raw phoneme contents.
        Falls back gracefully if remote worker is unavailable.
        """
        if not audio_bytes:
            return {
                "audio_duration_ms": 0,
                "phonemes": [],
                "speech_metrics": {},
                "client_response_delay_ms": client_response_delay_ms,
            }

        audio_size_bytes = len(audio_bytes)
        audio_duration_ms = max(0, min(30000, audio_size_bytes // 32))
        ctx = get_current_context()

        logger.info(
            "modal.phoneme_request.started",
            audio_size_bytes=audio_size_bytes,
            audio_duration_ms=audio_duration_ms,
            audio_format=audio_format,
            session_id=ctx.get("session_id"),
            turn_id=ctx.get("turn_id"),
        )

        start_time = time.perf_counter()
        try:
            worker = self._get_worker()
            if worker is not None:
                # Call remote Modal function in worker thread
                result = await asyncio.to_thread(
                    worker.analyze_phonemes.remote,
                    audio_bytes=audio_bytes,
                    audio_format=audio_format,
                    correlation_id=ctx.get("request_id"),
                    session_id=ctx.get("session_id"),
                    turn_id=ctx.get("turn_id"),
                )
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                phoneme_count = len(result.get("phonemes", []))
                gaps_count = result.get("speech_metrics", {}).get("in_speech_gaps_count", 0)

                logger.info(
                    "modal.phoneme_request.completed",
                    duration_ms=dur_ms,
                    audio_duration_ms=result.get("audio_duration_ms", audio_duration_ms),
                    phoneme_count=phoneme_count,
                    in_speech_gaps_count=gaps_count,
                    fallback_used=False,
                )
                result["client_response_delay_ms"] = client_response_delay_ms
                return result
        except Exception as e:
            dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(
                "modal.phoneme_request.failed",
                duration_ms=dur_ms,
                exception_type=e.__class__.__name__,
                fallback_used=True,
            )

        # When remote Modal is unavailable, return empty phoneme evidence without fabricating fake phonemes
        return {
            "audio_duration_ms": audio_duration_ms,
            "phonemes": [],
            "speech_metrics": {
                "total_phonemes": 0,
                "in_speech_gaps_count": 0,
                "total_in_speech_pause_duration_ms": 0,
                "first_phone_offset_ms": 0,
                "last_phone_end_ms": 0,
            },
            "client_response_delay_ms": client_response_delay_ms,
            "is_unavailable": True,
        }


modal_speech_client = ModalSpeechClient()
