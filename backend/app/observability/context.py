import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Union

# Context variables for correlation across async operations
_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_request_id", default=None)
_user_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_user_id", default=None)
_session_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_session_id", default=None)
_turn_id_ctx: contextvars.ContextVar[Optional[Union[str, int]]] = contextvars.ContextVar("rebutio_turn_id", default=None)
_debate_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_debate_id", default=None)
_background_task_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_background_task_id", default=None)
_provider_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("rebutio_provider_request_id", default=None)

CONTEXT_VARS = {
    "request_id": _request_id_ctx,
    "user_id": _user_id_ctx,
    "session_id": _session_id_ctx,
    "turn_id": _turn_id_ctx,
    "debate_id": _debate_id_ctx,
    "background_task_id": _background_task_id_ctx,
    "provider_request_id": _provider_request_id_ctx,
}


def bind_context(**kwargs: Any) -> Dict[str, contextvars.Token]:
    """
    Binds context variables for the current async task/thread.
    Returns tokens that can be used to reset if needed.
    """
    tokens = {}
    for key, val in kwargs.items():
        if key in CONTEXT_VARS:
            tokens[key] = CONTEXT_VARS[key].set(val)
    return tokens


def unbind_context(*keys: str) -> None:
    """Unbinds specified context variables."""
    for key in keys:
        if key in CONTEXT_VARS:
            CONTEXT_VARS[key].set(None)


def clear_context() -> None:
    """Resets all correlation context variables to None."""
    for ctx_var in CONTEXT_VARS.values():
        ctx_var.set(None)


def get_current_context() -> Dict[str, Any]:
    """Returns a dict of all currently set context variables."""
    ctx = {}
    for key, ctx_var in CONTEXT_VARS.items():
        val = ctx_var.get()
        if val is not None:
            ctx[key] = val
    return ctx


@contextmanager
def bound_context(**kwargs: Any) -> Iterator[Dict[str, Any]]:
    """
    Context manager that temporarily binds correlation variables and restores previous values on exit.
    """
    tokens = {}
    for key, val in kwargs.items():
        if key in CONTEXT_VARS:
            tokens[key] = CONTEXT_VARS[key].set(val)
    try:
        yield get_current_context()
    finally:
        for key, token in tokens.items():
            if key in CONTEXT_VARS:
                CONTEXT_VARS[key].reset(token)


def contextvars_processor(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Structlog processor that merges active correlation contextvars into the log event dict.
    Explicit event_dict fields take precedence over context variables.
    """
    for key, ctx_var in CONTEXT_VARS.items():
        val = ctx_var.get()
        if val is not None and key not in event_dict:
            event_dict[key] = val
    return event_dict
