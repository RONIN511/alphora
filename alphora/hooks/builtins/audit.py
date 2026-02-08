import json
import os
from typing import Any, Callable, Dict, Optional

from alphora.hooks.context import HookContext


def jsonl_audit_writer(
        file_path: str,
        include_data: bool = True,
        extra: Optional[Dict[str, Any]] = None,
) -> Callable[[HookContext], None]:
    """
    Append audit events to a JSONL file.
    """
    def _hook(ctx: HookContext) -> None:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        record = {
            "event": ctx.event,
            "component": ctx.component,
            "timestamp": ctx.timestamp.isoformat(),
            "trace_id": ctx.trace_id,
        }
        if include_data:
            record["data"] = ctx.data
        if extra:
            record.update(extra)

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return _hook
