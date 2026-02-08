from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class HookResult:
    replace: Optional[Dict[str, Any]] = None
    stop_propagation: bool = False
