from typing import Any, Callable, Optional


def hook(
        event: Any,
        priority: int = 0,
        when: Optional[Callable] = None,
        timeout: Optional[float] = None,
        error_policy: Optional[str] = None,
):
    def _decorator(func: Callable):
        setattr(func, "_hook_event", event)
        setattr(func, "_hook_priority", priority)
        setattr(func, "_hook_when", when)
        setattr(func, "_hook_timeout", timeout)
        setattr(func, "_hook_error_policy", error_policy)
        return func

    return _decorator


def is_hook(func: Callable) -> bool:
    return hasattr(func, "_hook_event")
