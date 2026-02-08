import asyncio
import inspect
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Union

from .context import HookContext
from .result import HookResult

logger = logging.getLogger(__name__)


HookFunc = Callable[[HookContext], Union[None, HookResult, Dict[str, Any], Awaitable[Any]]]


class HookErrorPolicy(str, Enum):
    FAIL_OPEN = "fail_open"
    FAIL_CLOSE = "fail_close"


@dataclass
class HookHandler:
    func: HookFunc
    priority: int = 0
    when: Optional[Callable[[HookContext], bool]] = None
    timeout: Optional[float] = None
    name: Optional[str] = None
    error_policy: Optional[HookErrorPolicy] = None
    handler_id: Optional[int] = None

    def matches(self, ctx: HookContext) -> bool:
        return True if self.when is None else bool(self.when(ctx))


@dataclass
class HookStats:
    calls: int = 0
    errors: int = 0
    total_ms: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None

    def record(self, duration_ms: float, error: Optional[str] = None) -> None:
        self.calls += 1
        self.total_ms += duration_ms
        if error:
            self.errors += 1
            self.last_error = error
            self.last_error_time = time.time()


class HookManager:
    def __init__(
            self,
            fail_close_events: Optional[Iterable[str]] = None,
            default_timeout: Optional[float] = None,
            default_error_policy: HookErrorPolicy = HookErrorPolicy.FAIL_OPEN,
            run_sync_in_executor: bool = False,
            on_exception: Optional[Callable[[HookContext, Exception], None]] = None,
    ):
        self._handlers: Dict[str, List[HookHandler]] = {}
        self._fail_close_events = set(fail_close_events or [])
        self._default_timeout = default_timeout
        self._default_error_policy = default_error_policy
        self._event_policies: Dict[str, HookErrorPolicy] = {}
        self._run_sync_in_executor = run_sync_in_executor
        self._on_exception = on_exception
        self._stats: Dict[str, HookStats] = {}
        self._next_handler_id = 1

    @staticmethod
    def _resolve_event(event: Any) -> str:
        return event.value if hasattr(event, "value") else str(event)

    def register(
            self,
            event: Any,
            func: HookFunc,
            priority: int = 0,
            when: Optional[Callable[[HookContext], bool]] = None,
            timeout: Optional[float] = None,
            error_policy: Optional[Union[HookErrorPolicy, str]] = None,
    ) -> None:
        event_name = self._resolve_event(event)
        handler = HookHandler(
            func=func,
            priority=priority,
            when=when,
            timeout=timeout if timeout is not None else self._default_timeout,
            name=getattr(func, "__name__", None),
            error_policy=self._normalize_policy(error_policy),
            handler_id=self._next_handler_id,
        )
        self._next_handler_id += 1
        self._handlers.setdefault(event_name, []).append(handler)

    def register_many(self, event: Any, funcs: Union[HookFunc, Iterable[HookFunc]]) -> None:
        if isinstance(funcs, list) or isinstance(funcs, tuple):
            for fn in funcs:
                self.register(event, fn)
        else:
            self.register(event, funcs)

    def register_decorated(self, func: HookFunc) -> None:
        event = getattr(func, "_hook_event", None)
        if not event:
            return
        self.register(
            event=event,
            func=func,
            priority=getattr(func, "_hook_priority", 0),
            when=getattr(func, "_hook_when", None),
            timeout=getattr(func, "_hook_timeout", None),
            error_policy=self._normalize_policy(getattr(func, "_hook_error_policy", None)),
        )

    def register_decorated_many(self, funcs: Iterable[HookFunc]) -> None:
        for fn in funcs:
            self.register_decorated(fn)

    def list_events(self) -> List[str]:
        return list(self._handlers.keys())

    def set_event_policy(self, event: Any, policy: HookErrorPolicy) -> None:
        event_name = self._resolve_event(event)
        self._event_policies[event_name] = policy

    def clear_event(self, event: Any) -> None:
        event_name = self._resolve_event(event)
        self._handlers.pop(event_name, None)

    def unregister(self, event: Any, func: HookFunc) -> None:
        event_name = self._resolve_event(event)
        handlers = self._handlers.get(event_name, [])
        self._handlers[event_name] = [h for h in handlers if h.func is not func]

    def _sorted_handlers(self, event: str) -> List[HookHandler]:
        handlers = self._handlers.get(event, [])
        return sorted(handlers, key=lambda h: h.priority, reverse=True)

    def get_stats(self) -> Dict[str, HookStats]:
        return self._stats

    def _resolve_error_policy(self, event_name: str, handler: HookHandler) -> HookErrorPolicy:
        if handler.error_policy:
            return handler.error_policy
        if event_name in self._event_policies:
            return self._event_policies[event_name]
        if event_name in self._fail_close_events:
            return HookErrorPolicy.FAIL_CLOSE
        return self._default_error_policy

    @staticmethod
    def _normalize_policy(policy: Optional[Union[HookErrorPolicy, str]]) -> Optional[HookErrorPolicy]:
        if policy is None:
            return None
        if isinstance(policy, HookErrorPolicy):
            return policy
        return HookErrorPolicy(str(policy))

    async def _run_handler(self, handler: HookHandler, ctx: HookContext) -> Any:
        if self._run_sync_in_executor and not inspect.iscoroutinefunction(handler.func):
            if handler.timeout:
                return await asyncio.wait_for(asyncio.to_thread(handler.func, ctx), timeout=handler.timeout)
            return await asyncio.to_thread(handler.func, ctx)

        result = handler.func(ctx)
        if inspect.isawaitable(result):
            if handler.timeout:
                return await asyncio.wait_for(result, timeout=handler.timeout)
            return await result

        return result

    async def emit(self, event: Any, ctx: HookContext) -> HookContext:
        event_name = self._resolve_event(event)
        ctx.event = event_name

        for handler in self._sorted_handlers(event_name):
            if not handler.matches(ctx):
                continue

            start = time.perf_counter()
            error_str = None
            try:
                result = await self._run_handler(handler, ctx)
                self._apply_result(ctx, result)
                if isinstance(result, HookResult) and result.stop_propagation:
                    break
            except Exception as e:
                logger.exception(f"Hook error in {event_name}: {e}")
                if self._on_exception:
                    self._on_exception(ctx, e)
                policy = self._resolve_error_policy(event_name, handler)
                error_str = str(e)
                if policy == HookErrorPolicy.FAIL_CLOSE:
                    raise
                continue
            finally:
                self._stats.setdefault(event_name, HookStats()).record(
                    (time.perf_counter() - start) * 1000,
                    error=error_str,
                )

        return ctx

    def emit_sync(self, event: Any, ctx: HookContext) -> HookContext:
        event_name = self._resolve_event(event)
        ctx.event = event_name

        for handler in self._sorted_handlers(event_name):
            if not handler.matches(ctx):
                continue

            start = time.perf_counter()
            error_str = None
            try:
                result = handler.func(ctx)
                if inspect.isawaitable(result):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        logger.warning(
                            f"Async hook called from sync context: {event_name}. "
                            "Scheduled in background."
                        )
                        asyncio.create_task(result)
                        result = None
                    else:
                        result = asyncio.run(result)

                self._apply_result(ctx, result)
                if isinstance(result, HookResult) and result.stop_propagation:
                    break
            except Exception as e:
                logger.exception(f"Hook error in {event_name}: {e}")
                if self._on_exception:
                    self._on_exception(ctx, e)
                policy = self._resolve_error_policy(event_name, handler)
                error_str = str(e)
                if policy == HookErrorPolicy.FAIL_CLOSE:
                    raise
                continue
            finally:
                self._stats.setdefault(event_name, HookStats()).record(
                    (time.perf_counter() - start) * 1000,
                    error=error_str,
                )

        return ctx

    @staticmethod
    def _apply_result(ctx: HookContext, result: Any) -> None:
        if isinstance(result, HookResult):
            if result.replace:
                ctx.data.update(result.replace)
            return

        if isinstance(result, dict):
            ctx.data.update(result)
