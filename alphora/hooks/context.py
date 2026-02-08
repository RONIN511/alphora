from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class HookContext:
    event: str
    component: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: Optional[str] = None

    def with_updates(self, **kwargs) -> "HookContext":
        self.data.update(kwargs)
        return self

    def set(self, key: str, value: Any) -> "HookContext":
        self.data[key] = value
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def copy(self) -> "HookContext":
        return HookContext(
            event=self.event,
            component=self.component,
            data=self.data.copy(),
            timestamp=self.timestamp,
            trace_id=self.trace_id,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event,
            "component": self.component,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
        }
