from typing import Any, Dict, List, Tuple
from itertools import cycle
import random
from openai import OpenAI, AsyncOpenAI


class _LLMLoadBalancer:
    """llm负载均衡器"""

    def __init__(self, strategy: str = "round_robin"):
        if strategy not in ("round_robin", "random"):
            raise ValueError("strategy must be 'round_robin' or 'random'")
        self.strategy = strategy

        self._sync_backends: List[Tuple[OpenAI, Dict[str, Any]]] = []
        self._async_backends: List[Tuple[AsyncOpenAI, Dict[str, Any]]] = []

        self._sync_cycle = None
        self._async_cycle = None

    def add_client(
            self,
            sync_client: OpenAI,
            async_client: AsyncOpenAI,
            completion_params: Dict[str, Any]
    ):
        """
        同时注册一对同步/异步客户端，共享相同的 completion_params。
        保证两者在负载均衡中处于相同位置（策略对齐）。
        """
        if not isinstance(sync_client, OpenAI):
            raise TypeError("sync_client must be an instance of OpenAI")
        if not isinstance(async_client, AsyncOpenAI):
            raise TypeError("async_client must be an instance of AsyncOpenAI")
        if not isinstance(completion_params, dict):
            raise TypeError("completion_params must be a dict")

        # 深拷贝 params 避免外部修改影响
        params_copy = completion_params.copy()

        self._sync_backends.append((sync_client, params_copy))
        self._async_backends.append((async_client, params_copy))

        # 重建 cycle（仅当使用 round_robin）
        if self.strategy == "round_robin":
            self._sync_cycle = cycle(range(len(self._sync_backends)))
            self._async_cycle = cycle(range(len(self._async_backends)))

    def get_next_sync_backend(self) -> Tuple[OpenAI, Dict[str, Any]]:
        if not self._sync_backends:
            raise RuntimeError("No synchronous backends registered.")
        if self.strategy == "round_robin":
            idx = next(self._sync_cycle)
        else:
            idx = random.randrange(len(self._sync_backends))
        return self._sync_backends[idx]

    def get_next_async_backend(self) -> Tuple[AsyncOpenAI, Dict[str, Any]]:
        if not self._async_backends:
            raise RuntimeError("No asynchronous backends registered.")
        if self.strategy == "round_robin":
            idx = next(self._async_cycle)
        else:
            idx = random.randrange(len(self._async_backends))
        return self._async_backends[idx]

    def size(self) -> int:
        """返回后端对的数量"""
        return len(self._sync_backends)  # == len(self._async_backends)