import json
import logging
from typing import Any, Callable, Dict, Iterable, Optional

from alphora.hooks.context import HookContext

logger = logging.getLogger(__name__)


def log_event(
        level: str = "info",
        message: Optional[str] = None,
        include_data_keys: Optional[Iterable[str]] = None,
) -> Callable[[HookContext], None]:
    """
    Generic logging hook for any event.
    """
    def _hook(ctx: HookContext) -> None:
        payload: Dict[str, Any] = {
            "event": ctx.event,
            "component": ctx.component,
            "trace_id": ctx.trace_id,
        }
        if include_data_keys:
            payload["data"] = {k: ctx.data.get(k) for k in include_data_keys}
        else:
            payload["data"] = ctx.data

        text = message or json.dumps(payload, ensure_ascii=False, default=str)
        getattr(logger, level, logger.info)(text)

    return _hook


def log_tool_execution(
        level: str = "info",
        include_args: bool = False,
        include_result: bool = False,
) -> Callable[[HookContext], None]:
    """
    Specialized logger for tool execution events.
    """
    def _hook(ctx: HookContext) -> None:
        payload: Dict[str, Any] = {
            "event": ctx.event,
            "tool_name": ctx.data.get("tool_name"),
            "tool_call_id": ctx.data.get("tool_call_id"),
        }
        if include_args:
            payload["tool_args"] = ctx.data.get("tool_args")
        if include_result:
            payload["tool_result"] = ctx.data.get("tool_result")

        text = json.dumps(payload, ensure_ascii=False, default=str)
        getattr(logger, level, logger.info)(text)

    return _hook
