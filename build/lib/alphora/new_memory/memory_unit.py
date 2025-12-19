# memory/memory_unit.py
"""
生产级记忆单元（MemoryUnit）：功能丰富、性能稳定、结构清晰。

设计原则：
- 显式优于隐式：无魔法行为，逻辑可读性强
- 零成本抽象：未使用的功能不带来运行时开销
- 线程安全：读操作天然安全，写操作建议在单线程上下文（如智能体内部）
- 可序列化：支持跨服务传输与持久化
- 可扩展：衰减策略、嵌入向量等均可按需注入
"""

import uuid
import time
from typing import Any, Dict, Optional, List, Tuple, Callable, Union


class MemoryUnit:
    """
    表示一个原子记忆单元，包含内容、元数据、时效性与认知权重。

    适用于高吞吐智能体系统，支持：
    - 多模态内容（文本、图像引用、结构化事件等）
    - 自动过期（TTL）
    - 可插拔的记忆衰减策略
    - 因果链追踪（用于记忆溯源）
    - 向量嵌入（可选，兼容向量数据库）
    """

    __slots__ = (
        "unique_id",        # 唯一标识符
        "created_at",       # 创建时间（秒，浮点，Unix 时间戳）
        "last_accessed",    # 最后访问时间（用于 LRU 或热度计算）
        "ttl_seconds",      # 生存时间（秒），None 表示永不过期
        "content",          # 记忆内容，字典形式，支持任意结构
        "modality",         # 模态类型，如 "text"、"image"、"structured"
        "score",            # 初始认知权重，范围 [0.0, 1.0]
        "decay_fn",         # 衰减函数：(MemoryUnit, 当前时间) -> 当前分数
        "embedding",        # 向量嵌入（可选），用于语义检索
        "embedding_model",  # 生成嵌入所用的模型名称
        "metadata",         # 用户自定义元数据
        "tags",             # 标签集合，用于快速过滤
        "source",           # 来源（如 "user", "tool", "reflection"）
        "causal_chain",     # 因果链：导致此记忆生成的上游记忆 ID 列表
    )

    def __init__(
            self,
            content: Dict[str, Any],
            *,
            unique_id: Optional[str] = None,
            created_at: Optional[float] = None,
            ttl_seconds: Optional[float] = None,
            modality: str = "text",
            score: float = 1.0,
            decay_fn: Optional[Callable[["MemoryUnit", float], float]] = None,
            embedding: Optional[List[float]] = None,
            embedding_model: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None,
            tags: Optional[List[str]] = None,
            source: Optional[str] = None,
            causal_chain: Optional[List[str]] = None,
    ):
        # 初始化唯一 ID
        self.unique_id = unique_id or str(uuid.uuid4())

        # 时间戳：创建时间和最后访问时间
        self.created_at = created_at or time.time()
        self.last_accessed = self.created_at

        # 生存时间（TTL），None 表示永久有效
        self.ttl_seconds = ttl_seconds

        # 记忆内容与模态
        self.content = content
        self.modality = modality

        # 认知权重：限制在 [0.0, 1.0] 区间内
        self.score = max(0.0, min(1.0, score))

        # 衰减策略函数，默认使用指数衰减
        self.decay_fn = decay_fn or default_decay_fn

        # 向量嵌入（可选）
        self.embedding = embedding
        self.embedding_model = embedding_model

        # 元数据与标签
        self.metadata = metadata or {}
        self.tags = set(tags) if tags else set()
        self.source = source

        # 因果链：记录此记忆由哪些记忆演化而来
        self.causal_chain = list(causal_chain) if causal_chain else []

    def access(self) -> None:
        """标记该记忆被访问，更新最后访问时间（用于热度或缓存淘汰策略）"""
        self.last_accessed = time.time()

    @property
    def age(self) -> float:
        """返回记忆的年龄（单位：秒）"""
        return time.time() - self.created_at

    @property
    def is_expired(self) -> bool:
        """判断记忆是否已过期"""
        if self.ttl_seconds is None:
            return False
        return self.age > self.ttl_seconds

    def current_score(self, at_time: Optional[float] = None) -> float:
        """
        计算当前认知权重（考虑衰减和过期）。

        参数:
            at_time: 用于计算的时间点（默认为当前时间）

        返回:
            当前分数，范围 [0.0, 1.0]，过期则为 0.0
        """
        if self.is_expired:
            return 0.0
        now = at_time or time.time()
        return self.decay_fn(self, now)

    def reinforce(self, increment: float, new_source: Optional[str] = None) -> "MemoryUnit":
        """
        强化记忆：生成一个新记忆单元，分数提升，并记录因果关系。

        注意：此操作是不可变的（返回新实例），保留原始记忆不变。

        参数:
            increment: 分数增量（正数）
            new_source: 新来源（可选）

        返回:
            新的 MemoryUnit 实例
        """
        new_score = min(1.0, self.score + increment)
        return MemoryUnit(
            content=self.content,
            unique_id=str(uuid.uuid4()),  # 新 ID，表示一次新的记忆事件
            created_at=time.time(),
            ttl_seconds=self.ttl_seconds,
            modality=self.modality,
            score=new_score,
            decay_fn=self.decay_fn,
            embedding=self.embedding,
            embedding_model=self.embedding_model,
            metadata=self.metadata.copy(),
            tags=list(self.tags),
            source=new_source or self.source,
            causal_chain=self.causal_chain + [self.unique_id],  # 追加当前 ID 到因果链
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 JSON 兼容的字典（可用于存储或网络传输）"""
        return {
            "unique_id": self.unique_id,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "ttl_seconds": self.ttl_seconds,
            "content": self.content,
            "modality": self.modality,
            "score": self.score,
            "embedding": self.embedding,
            "embedding_model": self.embedding_model,
            "metadata": self.metadata,
            "tags": list(self.tags),
            "source": self.source,
            "causal_chain": self.causal_chain,
            "_version": 2,  # 用于未来兼容性检查
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryUnit":
        """从字典反序列化为 MemoryUnit 实例"""
        if data.get("_version") != 2:
            raise ValueError("不支持的记忆单元版本，请升级处理逻辑")
        return cls(
            content=data["content"],
            unique_id=data["unique_id"],
            created_at=data["created_at"],
            ttl_seconds=data.get("ttl_seconds"),
            modality=data.get("modality", "text"),
            score=data.get("score", 1.0),
            embedding=data.get("embedding"),
            embedding_model=data.get("embedding_model"),
            metadata=data.get("metadata"),
            tags=data.get("tags"),
            source=data.get("source"),
            causal_chain=data.get("causal_chain"),
        )

    def __repr__(self) -> str:
        # 生成简洁可读的调试字符串
        preview = str(self.content)[:60].replace('\n', '\\n')
        return f"MemoryUnit(id={self.unique_id[:8]}..., score={self.score:.2f}, content='{preview}...')"


# ========================
# 内置衰减策略（无状态、零分配）
# ========================

def default_decay_fn(memory: MemoryUnit, now: float) -> float:
    """
    默认衰减策略：指数衰减，半衰期为 1 小时。

    公式：score * (0.5)^(age / half_life)
    """
    half_life_sec = 3600.0  # 1 小时
    age_sec = now - memory.created_at
    decay_factor = 0.5 ** (age_sec / half_life_sec)
    return memory.score * decay_factor


def linear_decay_fn(rate_per_hour: float = 0.1):
    """
    线性衰减工厂函数。

    参数:
        rate_per_hour: 每小时减少的分数（例如 0.1 表示 10 小时后归零）

    返回:
        一个符合 decay_fn 签名的函数
    """
    rate_per_sec = rate_per_hour / 3600.0
    def _decay(memory: MemoryUnit, now: float) -> float:
        age_sec = now - memory.created_at
        return max(0.0, memory.score - rate_per_sec * age_sec)
    return _decay


def no_decay_fn(memory: MemoryUnit, now: float) -> float:
    """永不衰减——适用于需要永久保存的核心记忆"""
    return memory.score