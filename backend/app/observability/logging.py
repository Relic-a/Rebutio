import logging
import sys
from typing import Any, Optional
import structlog
from structlog.types import EventDict, Processor

from backend.app.config import settings
from backend.app.observability.context import contextvars_processor
from backend.app.observability.redaction import structlog_redaction_processor

_IS_CONFIGURED = False


def setup_logging(
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    log_ai_content: Optional[bool] = None,
) -> None:
    """
    Centralized logging configuration for Rebutio.
    Configures structlog and standard library logging with context propagation and secret redaction.
    """
    global _IS_CONFIGURED

    level_str = (log_level or getattr(settings, "LOG_LEVEL", "INFO")).upper()
    format_str = (log_format or getattr(settings, "LOG_FORMAT", "console")).lower()
    ai_content_flag = log_ai_content if log_ai_content is not None else getattr(settings, "LOG_AI_CONTENT", False)

    numeric_level = getattr(logging, level_str, logging.INFO)

    shared_processors: list[Processor] = [
        contextvars_processor,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog_redaction_processor,
    ]

    if format_str == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    # Set external third-party library log levels to prevent excessive spam
    logging.getLogger("uvicorn").setLevel(numeric_level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if level_str != "DEBUG" else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING if level_str != "DEBUG" else logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _IS_CONFIGURED = True


def get_logger(name: str = "rebutio") -> structlog.stdlib.BoundLogger:
    """Returns a structured logger with the given name."""
    if not _IS_CONFIGURED:
        setup_logging()
    return structlog.get_logger(name)
