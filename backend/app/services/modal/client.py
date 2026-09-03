import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional
from backend.app.config import settings
from backend.app.observability.context import get_current_context
from backend.app.observability.logging import get_logger

logger = get_logger("rebutio.modal")

# Bounded executor for ALL blocking Modal SDK calls. The default
# asyncio.to_thread pool is unbounded: every stalled .remote() call parks
# a thread forever, leaking threads until the worker wedges. This pool
# caps that blast radius; the semaphore below sheds load beyond it.
_MODAL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="modal-worker")
_MODAL_CALL_TIMEOUT_S = 10.0
_MODAL_LOOKUP_TIMEOUT_S = 15.0
_MODAL_LOOKUP_RETRY_COOLDOWN_S = 60.0
_MODAL_MAX_CONCURRENT_CALLS = 4
_MODAL_SLOT_WAIT_S = 2.0


class ModalSpeechClient:
    def __init__(self):
        self._modal_worker = None
        self._lookup_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(_MODAL_MAX_CONCURRENT_CALLS)
        self._last_lookup_failure = 0.0

    @staticmethod
    def _lookup_sync():
        """Blocking Modal handle lookup. Must run off the event loop."""
        import modal
        app_name = settings.MODAL_APP_NAME
        cls = modal.Cls.from_name(app_name, "SpeechAnalysisWorker")
        return cls()

    async def _get_worker(self):
        if self._modal_worker is not None:
            return self._modal_worker
        # Don't hammer Modal while it is down: cooldown between retries
        # instead of caching a failure forever.
        if time.monotonic() - self._last_lookup_failure < _MODAL_LOOKUP_RETRY_COOLDOWN_S:
            return None
        async with self._lookup_lock:
            if self._modal_worker is not None:
                return self._modal_worker
            try:
                loop = asyncio.get_running_loop()
                worker = await asyncio.wait_for(
                    loop.run_in_executor(_MODAL_EXECUTOR, self._lookup_sync),
                    timeout=_MODAL_LOOKUP_TIMEOUT_S,
                )
                self._modal_worker = worker
                logger.info("modal.worker.connected", app_name=settings.MODAL_APP_NAME)
            except Exception as e:
                self._last_lookup_failure = time.monotonic()
                logger.warning("modal.worker.lookup_deferred", error=str(e))
                self._modal_worker = None
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
            worker = await self._get_worker()
            if worker is None:
                logger.warning("modal.phoneme_request.skipped", reason="worker_unavailable")
                return self._fallback(audio_duration_ms, client_response_delay_ms)

            # Shed load instead of queueing unboundedly: if all executor
            # slots are held by stalled calls, fail fast to the fallback.
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=_MODAL_SLOT_WAIT_S)
            except asyncio.TimeoutError:
                logger.warning("modal.phoneme_request.shedded", reason="executor_saturated")
                return self._fallback(audio_duration_ms, client_response_delay_ms)

            try:
                loop = asyncio.get_running_loop()
                # Hard cap so a stalled remote worker degrades to the
                # graceful fallback instead of hanging the request forever.
                # Note: timeout abandons the executor thread but cannot
                # interrupt the blocking C call; bounded pool + semaphore
                # keep that leak contained.
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        _MODAL_EXECUTOR,
                        functools.partial(
                            worker.analyze_phonemes.remote,
                            audio_bytes=audio_bytes,
                            audio_format=audio_format,
                            correlation_id=ctx.get("request_id"),
                            session_id=ctx.get("session_id"),
                            turn_id=ctx.get("turn_id"),
                        ),
                    ),
                    timeout=_MODAL_CALL_TIMEOUT_S,
                )
            finally:
                self._slots.release()

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
        return self._fallback(audio_duration_ms, client_response_delay_ms)

    @staticmethod
    def _fallback(audio_duration_ms: int, client_response_delay_ms: int) -> Dict[str, Any]:
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
