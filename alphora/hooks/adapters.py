from typing import Any, Callable, Dict, Iterable, Optional, Union

from .manager import HookManager


HookInput = Union[Callable, Iterable[Callable]]


def _normalize_funcs(funcs: HookInput) -> Iterable[Callable]:
    if isinstance(funcs, (list, tuple, set)):
        return list(funcs)
    return [funcs]


def build_manager(
        hooks: Optional[Union[HookManager, Dict[Any, HookInput]]] = None,
        short_map: Optional[Dict[str, Any]] = None,
        decorated: Optional[Iterable[Callable]] = None,
        manager_options: Optional[Dict[str, Any]] = None,
        **short_hooks: HookInput,
) -> HookManager:
    if isinstance(hooks, HookManager):
        manager = hooks
    else:
        manager = HookManager(**(manager_options or {}))

    if hooks and isinstance(hooks, dict):
        for event, funcs in hooks.items():
            for fn in _normalize_funcs(funcs):
                manager.register(event, fn)

    if short_map:
        for short_name, event in short_map.items():
            if short_name in short_hooks and short_hooks[short_name] is not None:
                for fn in _normalize_funcs(short_hooks[short_name]):
                    manager.register(event, fn)

    if decorated:
        manager.register_decorated_many(decorated)

    return manager
