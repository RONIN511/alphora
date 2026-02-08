import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from alphora.hooks.context import HookContext


@dataclass
class MetricsSnapshot:
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0
    last_ts: Optional[float] = None


@dataclass
class MetricsStore:
    events: Dict[str, MetricsSnapshot] = field(default_factory=dict)

    def record(self, event: str, duration_ms: Optional[float] = None, error: bool = False) -> None:
        snap = self.events.setdefault(event, MetricsSnapshot())
        snap.calls += 1
        if error:
            snap.errors += 1
        if duration_ms is not None:
            snap.total_ms += duration_ms
        snap.last_ts = time.time()

    def as_dict(self) -> Dict[str, Dict[str, Any]]:
        return {
            k: {
                "calls": v.calls,
                "errors": v.errors,
                "total_ms": v.total_ms,
                "last_ts": v.last_ts,
            }
            for k, v in self.events.items()
        }


def make_event_counter(store: MetricsStore) -> Callable[[HookContext], None]:
    """
    Counts events; if tool_result.status == 'error', increments error.
    """
    def _hook(ctx: HookContext) -> None:
        tool_result = ctx.data.get("tool_result")
        error = getattr(tool_result, "status", None) == "error"
        store.record(ctx.event, error=error)

    return _hook
