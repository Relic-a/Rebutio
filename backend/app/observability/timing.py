import time
from typing import Any, Dict, Optional
import structlog

_fallback_logger = structlog.get_logger("rebutio.timing")


class log_duration:
    """
    Reusable performance timing helper and context manager (sync & async).
    Emits structured completed or failed events with duration_ms.
    """

    def __init__(
        self,
        event_name: str,
        logger: Optional[Any] = None,
        level: str = "info",
        log_start: bool = False,
        **extra_fields: Any,
    ):
        self.event_name = event_name
        self.logger = logger or _fallback_logger
        self.level = level
        self.log_start = log_start
        self.extra_fields = extra_fields
        self.start_time = 0.0

    def _get_log_method(self, lvl: str):
        return getattr(self.logger, lvl, self.logger.info)

    def __enter__(self):
        self.start_time = time.perf_counter()
        if self.log_start:
            self._get_log_method("debug")(
                f"{self.event_name}.started",
                **self.extra_fields,
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        if exc_type is not None:
            self.logger.error(
                f"{self.event_name}.failed",
                duration_ms=elapsed_ms,
                exception_type=exc_type.__name__,
                **self.extra_fields,
            )
        else:
            self._get_log_method(self.level)(
                f"{self.event_name}.completed",
                duration_ms=elapsed_ms,
                **self.extra_fields,
            )
        return False  # Do not swallow exception

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)
