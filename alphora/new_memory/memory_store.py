# memory/memory_store.py
"""
企业级记忆存储引擎（MemoryStore）

功能：
- 混合索引：ID、时间范围、标签、向量（可选）
- 自动过期清理（TTL）
- 容量限制与 LRU 淘汰
- 线程安全（读操作无锁，写操作加锁）
- 可插拔向量索引后端

设计哲学：
- 默认轻量：不依赖外部库也能运行
- 扩展友好：向量检索可替换为 FAISS/HNSWlib
- 性能优先：热点路径避免不必要的拷贝或锁竞争
"""

import threading
import time
from typing import List, Dict, Optional, Callable, Tuple, Any
from collections import OrderedDict

from .memory_unit import MemoryUnit


class MemoryStore:
    """
    高性能记忆存储容器，适用于单智能体或多租户轻量场景。

    内部结构：
    - `_memories`: 主存储（OrderedDict，按插入顺序，支持 LRU）
    - `_tag_index`: 标签反向索引（tag -> set of IDs）
    - `_vector_index`: 向量列表（仅当启用向量检索时使用）

    线程安全：使用读写锁（写少读多优化）
    """

    def __init__(
            self,
            max_size: int = 10_000,
            enable_vector_index: bool = False,
            similarity_fn: Optional[Callable[[List[float], List[float]], float]] = None,
    ):
        """
        初始化记忆存储。

        参数:
            max_size: 最大记忆数量（超过则触发 LRU 淘汰）
            enable_vector_index: 是否启用向量索引（默认关闭以节省资源）
            similarity_fn: 向量相似度函数，如 cosine_similarity；若未提供，默认使用点积
        """
        if max_size <= 0:
            raise ValueError("max_size 必须大于 0")

        self.max_size = max_size
        self.enable_vector_index = enable_vector_index
        self.similarity_fn = similarity_fn or dot_product_similarity

        # 主存储：有序字典，最新访问/插入的在末尾（便于 LRU）
        self._memories: OrderedDict[str, MemoryUnit] = OrderedDict()

        # 标签反向索引：快速按标签过滤
        self._tag_index: Dict[str, set] = {}

        # 向量索引：仅存储 (id, embedding) 对
        self._vector_index: List[Tuple[str, List[float]]] = []

        # 读写锁：允许多读，写时独占
        self._lock = threading.RLock()

    def add(self, memory: MemoryUnit) -> None:
        """
        添加记忆单元。

        行为：
        - 若 ID 已存在，则覆盖（更新）
        - 自动维护标签索引和向量索引
        - 若超出容量，触发 LRU 淘汰
        - 自动移除已过期记忆（懒清理 + 主动清理结合）
        """
        with self._lock:
            # 清理部分过期项（避免积累过多垃圾）
            self._cleanup_expired(limit=10)

            memory_id = memory.unique_id

            # 如果是更新，先移除旧标签
            if memory_id in self._memories:
                self._remove_from_indexes(memory_id)

            # 插入新记忆（移到末尾，表示最新）
            self._memories[memory_id] = memory
            self._memories.move_to_end(memory_id)

            # 更新索引
            self._add_to_indexes(memory)

            # 检查容量，必要时淘汰最旧的（LRU）
            while len(self._memories) > self.max_size:
                # 弹出最旧的（开头）
                oldest_id, _ = self._memories.popitem(last=False)
                self._remove_from_indexes(oldest_id)

    def get(self, memory_id: str) -> Optional[MemoryUnit]:
        """根据 ID 获取记忆（若存在且未过期）"""
        with self._lock:
            memory = self._memories.get(memory_id)
            if memory is None:
                return None
            if memory.is_expired:
                self._remove(memory_id)
                return None
            memory.access()  # 更新访问时间
            # 由于 access() 修改了对象，需重新插入以更新 OrderedDict 顺序（LRU）
            self._memories.move_to_end(memory_id)
            return memory

    def remove(self, memory_id: str) -> bool:
        """移除指定记忆，返回是否成功"""
        with self._lock:
            return self._remove(memory_id)

    def search_by_tags(self, tags: List[str], match_all: bool = True) -> List[MemoryUnit]:
        """
        按标签搜索记忆。

        参数:
            tags: 要匹配的标签列表
            match_all: True 表示必须包含所有标签，False 表示包含任一即可

        返回:
            未过期的记忆列表（按插入时间倒序）
        """
        if not tags:
            return []

        with self._lock:
            candidate_ids: Optional[set] = None

            for tag in tags:
                ids_with_tag = self._tag_index.get(tag, set())
                if match_all:
                    if candidate_ids is None:
                        candidate_ids = ids_with_tag.copy()
                    else:
                        candidate_ids &= ids_with_tag
                else:
                    if candidate_ids is None:
                        candidate_ids = ids_with_tag.copy()
                    else:
                        candidate_ids |= ids_with_tag

            if not candidate_ids:
                return []

            # 过滤未过期项，并按时间倒序（最新在前）
            result = []
            current_time = time.time()
            for mem_id in reversed(list(self._memories.keys())):
                if mem_id not in candidate_ids:
                    continue
                mem = self._memories[mem_id]
                if mem.created_at <= current_time and not mem.is_expired:
                    result.append(mem)
                # 注意：不过期清理在此处懒处理，也可单独调用 cleanup

            return result

    def search_by_time(
            self,
            start: Optional[float] = None,
            end: Optional[float] = None,
    ) -> List[MemoryUnit]:
        """
        按时间范围搜索记忆。

        参数:
            start: 起始时间戳（秒），None 表示不限开始
            end: 结束时间戳（秒），None 表示不限结束

        返回:
            时间范围内的未过期记忆（按时间正序）
        """
        with self._lock:
            result = []
            for memory in self._memories.values():
                if memory.is_expired:
                    continue
                t = memory.created_at
                if (start is None or t >= start) and (end is None or t <= end):
                    result.append(memory)
            return result

    def search_by_vector(
            self,
            query_embedding: List[float],
            top_k: int = 5,
            score_threshold: float = 0.0,
    ) -> List[Tuple[MemoryUnit, float]]:
        """
        基于向量相似度搜索（仅在 enable_vector_index=True 时有效）。

        参数:
            query_embedding: 查询向量
            top_k: 返回前 K 个结果
            score_threshold: 相似度阈值（低于则忽略）

        返回:
            (记忆, 相似度分数) 列表，按分数降序排列
        """
        if not self.enable_vector_index:
            raise RuntimeError("向量索引未启用，请初始化时设置 enable_vector_index=True")

        with self._lock:
            results: List[Tuple[float, MemoryUnit]] = []

            for mem_id, emb in self._vector_index:
                memory = self._memories.get(mem_id)
                if memory is None or memory.is_expired:
                    continue
                score = self.similarity_fn(query_embedding, emb)
                if score >= score_threshold:
                    results.append((score, memory))

            # 按分数降序排序，取 top_k
            results.sort(key=lambda x: x[0], reverse=True)
            return [(mem, score) for score, mem in results[:top_k]]

    def cleanup(self) -> int:
        """
        主动清理所有过期记忆。

        返回:
            被清理的记忆数量
        """
        with self._lock:
            expired_ids = [
                mem_id for mem_id, mem in self._memories.items() if mem.is_expired
            ]
            for mem_id in expired_ids:
                self._remove(mem_id)
            return len(expired_ids)

    def size(self) -> int:
        """返回当前记忆数量（不含已过期但未清理的）"""
        with self._lock:
            return sum(1 for mem in self._memories.values() if not mem.is_expired)

    def all_memories(self) -> List[MemoryUnit]:
        """返回所有未过期记忆（慎用，大数据量时性能差）"""
        with self._lock:
            return [mem for mem in self._memories.values() if not mem.is_expired]

    # ---------------------
    # 内部辅助方法
    # ---------------------

    def _remove(self, memory_id: str) -> bool:
        """内部移除方法（需持有锁）"""
        if memory_id not in self._memories:
            return False
        self._remove_from_indexes(memory_id)
        del self._memories[memory_id]
        return True

    def _add_to_indexes(self, memory: MemoryUnit) -> None:
        """将记忆加入所有索引（需持有锁）"""
        # 标签索引
        for tag in memory.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(memory.unique_id)

        # 向量索引
        if self.enable_vector_index and memory.embedding is not None:
            self._vector_index.append((memory.unique_id, memory.embedding))

    def _remove_from_indexes(self, memory_id: str) -> None:
        """从所有索引中移除记忆（需持有锁）"""
        # 从标签索引移除
        for tag, id_set in self._tag_index.items():
            id_set.discard(memory_id)

        # 清理空标签
        empty_tags = [tag for tag, id_set in self._tag_index.items() if not id_set]
        for tag in empty_tags:
            del self._tag_index[tag]

        # 从向量索引移除（线性扫描，因向量索引通常不大）
        if self.enable_vector_index:
            self._vector_index = [
                (mid, emb) for mid, emb in self._vector_index if mid != memory_id
            ]

    def _cleanup_expired(self, limit: int = 10) -> None:
        """
        懒清理：在写入时顺带清理少量过期项，避免长时间不调用 cleanup 导致膨胀。
        """
        count = 0
        to_remove = []
        for mem_id, mem in self._memories.items():
            if mem.is_expired:
                to_remove.append(mem_id)
                count += 1
                if count >= limit:
                    break
        for mem_id in to_remove:
            self._remove(mem_id)


# ========================
# 向量相似度工具函数
# ========================

def dot_product_similarity(a: List[float], b: List[float]) -> float:
    """点积相似度（假设向量已归一化，则等价于余弦相似度）"""
    return sum(x * y for x, y in zip(a, b))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """标准余弦相似度（含归一化）"""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)