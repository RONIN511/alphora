from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional

from alphora.hooks.manager import HookManager


@dataclass
class HookPlugin:
    name: str
    handlers: List[Callable] = field(default_factory=list)

    def register(self, manager: HookManager) -> None:
        manager.register_decorated_many(self.handlers)


def load_plugins(manager: HookManager, plugins: Iterable["HookPlugin"]) -> None:
    for plugin in plugins:
        plugin.register(manager)
