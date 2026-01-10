"""
长期记忆 - 持久化的语义记忆

特性：
1. 基于向量的语义搜索
2. 记忆持久化到存储
3. 记忆重要性评分
4. 自动记忆压缩和摘要
5. 记忆关联和链接
"""

import time
import json
import hashlib
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import logging

from alphora.memory.base import BaseMemory
from alphora.memory.memory_unit import MemoryUnit

logger = logging.getLogger(__name__)


@dataclass
class LongTermMemoryUnit(MemoryUnit):
    """长期记忆单元"""
    vector: Optional[List[float]] = None  # 向量表示
    importance: float = 0.5  # 重要性分数 (0-1)
    access_count: int = 0  # 访问次数
    last_accessed: float = field(default_factory=time.time)
    associations: List[str] = field(default_factory=list)  # 关联的记忆ID
    summary: Optional[str] = None  # 记忆摘要
    
    def access(self):
        """记录一次访问"""
        self.access_count += 1
        self.last_accessed = time.time()
        # 访问会增加重要性
        self.importance = min(1.0, self.importance + 0.01)
    
    def calculate_relevance(self, query_vector: List[float]) -> float:
        """计算与查询的相关性"""
        if not self.vector or not query_vector:
            return 0.0
        
        # 余弦相似度
        dot = sum(a * b for a, b in zip(self.vector, query_vector))
        norm1 = sum(a * a for a in self.vector) ** 0.5
        norm2 = sum(b * b for b in query_vector) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot / (norm1 * norm2)
        
        # 综合考虑相似度、重要性和新近度
        recency = 1.0 / (1.0 + (time.time() - self.last_accessed) / 86400)  # 按天衰减
        
        return 0.6 * similarity + 0.3 * self.importance + 0.1 * recency


class LongTermMemory(BaseMemory):
    """
    长期记忆
    
    支持语义搜索的持久化记忆系统。
    
    使用示例：
    ```python
    # 创建长期记忆
    memory = LongTermMemory(
        embedder=embedding_model,
        storage_path="./memory_store"
    )
    
    # 添加记忆
    await memory.aadd_memory(
        role="assistant",
        content="用户喜欢蓝色和科技产品",
        memory_id="user_preferences",
        importance=0.8
    )
    
    # 语义搜索相关记忆
    results = await memory.asearch(
        query="用户的颜色偏好是什么？",
        memory_id="user_preferences",
        top_k=5
    )
    ```
    """
    
    def __init__(
        self,
        embedder: Optional[Any] = None,
        storage_path: Optional[str] = None,
        llm: Optional[Any] = None,  # 用于生成摘要
        max_memories_per_id: int = 1000,
        auto_summarize_threshold: int = 50  # 超过此数量自动生成摘要
    ):
        super().__init__()
        self.embedder = embedder
        self.storage_path = Path(storage_path) if storage_path else None
        self.llm = llm
        self.max_memories_per_id = max_memories_per_id
        self.auto_summarize_threshold = auto_summarize_threshold
        
        # 扩展存储
        self._long_term_memories: Dict[str, List[LongTermMemoryUnit]] = {}
        
        # 加载持久化数据
        if self.storage_path and self.storage_path.exists():
            self._load()
    
    async def aadd_memory(
        self,
        role: str,
        content: str,
        memory_id: str = "default",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        associations: Optional[List[str]] = None
    ):
        """异步添加长期记忆"""
        # 生成向量
        vector = None
        if self.embedder:
            vector = await self.embedder.aget_text_embedding(content)
        
        # 创建记忆单元
        memory_unit = LongTermMemoryUnit(
            content={"role": role, "content": content},
            importance=importance,
            vector=vector,
            metadata=metadata or {},
            associations=associations or []
        )
        
        # 添加到存储
        if memory_id not in self._long_term_memories:
            self._long_term_memories[memory_id] = []
        
        self._long_term_memories[memory_id].append(memory_unit)
        
        # 检查是否需要压缩
        if len(self._long_term_memories[memory_id]) > self.max_memories_per_id:
            await self._compress_memories(memory_id)
        
        # 检查是否需要自动摘要
        if (len(self._long_term_memories[memory_id]) > 0 and 
            len(self._long_term_memories[memory_id]) % self.auto_summarize_threshold == 0):
            await self._generate_summary(memory_id)
        
        # 持久化
        self._save()
        
        return memory_unit.unique_id
    
    def add_memory(
        self,
        role: str,
        content: str,
        memory_id: str = "default",
        importance: float = 0.5,
        decay_factor: float = 0.9,
        increment: float = 0.1
    ):
        """同步添加记忆（兼容基类）"""
        # 同步版本不生成向量
        memory_unit = LongTermMemoryUnit(
            content={"role": role, "content": content},
            importance=importance
        )
        
        if memory_id not in self._long_term_memories:
            self._long_term_memories[memory_id] = []
        
        # 衰减现有记忆的重要性
        for mem in self._long_term_memories[memory_id]:
            mem.importance *= decay_factor
        
        self._long_term_memories[memory_id].append(memory_unit)
        
        # 同时更新基类存储
        super().add_memory(role, content, memory_id, decay_factor, increment)
        
        self._save()
    
    async def asearch(
        self,
        query: str,
        memory_id: str = "default",
        top_k: int = 10,
        min_relevance: float = 0.0,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[LongTermMemoryUnit]:
        """
        语义搜索记忆
        
        Args:
            query: 查询文本
            memory_id: 记忆ID
            top_k: 返回数量
            min_relevance: 最小相关性阈值
            filter_metadata: 元数据过滤
        """
        memories = self._long_term_memories.get(memory_id, [])
        if not memories:
            return []
        
        # 获取查询向量
        query_vector = None
        if self.embedder:
            query_vector = await self.embedder.aget_text_embedding(query)
        
        # 计算相关性并排序
        scored_memories = []
        for mem in memories:
            # 元数据过滤
            if filter_metadata:
                match = all(
                    mem.metadata.get(k) == v
                    for k, v in filter_metadata.items()
                )
                if not match:
                    continue
            
            relevance = mem.calculate_relevance(query_vector) if query_vector else mem.importance
            
            if relevance >= min_relevance:
                scored_memories.append((mem, relevance))
        
        # 排序
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        
        # 返回结果并记录访问
        results = []
        for mem, _ in scored_memories[:top_k]:
            mem.access()
            results.append(mem)
        
        self._save()
        return results
    
    async def _compress_memories(self, memory_id: str):
        """压缩记忆（移除不重要的记忆）"""
        memories = self._long_term_memories.get(memory_id, [])
        if len(memories) <= self.max_memories_per_id:
            return
        
        # 按综合分数排序（重要性 + 访问频率 + 新近度）
        def score_memory(mem: LongTermMemoryUnit) -> float:
            recency = 1.0 / (1.0 + (time.time() - mem.last_accessed) / 86400)
            frequency = min(1.0, mem.access_count / 10)
            return 0.4 * mem.importance + 0.3 * frequency + 0.3 * recency
        
        memories.sort(key=score_memory, reverse=True)
        
        # 保留重要的记忆
        self._long_term_memories[memory_id] = memories[:self.max_memories_per_id]
        
        logger.info(
            f"Compressed memories for '{memory_id}': "
            f"kept {self.max_memories_per_id} out of {len(memories)}"
        )
    
    async def _generate_summary(self, memory_id: str):
        """生成记忆摘要"""
        if not self.llm:
            return
        
        memories = self._long_term_memories.get(memory_id, [])
        if not memories:
            return
        
        # 获取最近的记忆
        recent = sorted(memories, key=lambda m: m.timestamp, reverse=True)[:20]
        
        # 构建摘要提示
        content_list = [
            f"- {m.content.get('role', 'unknown')}: {m.content.get('content', '')}"
            for m in recent
        ]
        
        prompt = f"""请对以下对话内容生成一个简洁的摘要，突出重要信息：

{chr(10).join(content_list)}

摘要："""
        
        try:
            summary = await self.llm.ainvoke(prompt)
            
            # 创建摘要记忆
            summary_unit = LongTermMemoryUnit(
                content={"role": "system", "content": f"[摘要] {summary}"},
                importance=0.9,
                summary=summary
            )
            
            if self.embedder:
                summary_unit.vector = await self.embedder.aget_text_embedding(summary)
            
            self._long_term_memories[memory_id].append(summary_unit)
            
            logger.info(f"Generated summary for '{memory_id}'")
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
    
    def get_memories(self, memory_id: str) -> List[LongTermMemoryUnit]:
        """获取指定ID的所有记忆"""
        return self._long_term_memories.get(memory_id, [])
    
    def get_important_memories(
        self,
        memory_id: str,
        top_n: int = 10,
        min_importance: float = 0.5
    ) -> List[LongTermMemoryUnit]:
        """获取重要记忆"""
        memories = self._long_term_memories.get(memory_id, [])
        important = [m for m in memories if m.importance >= min_importance]
        important.sort(key=lambda m: m.importance, reverse=True)
        return important[:top_n]
    
    def build_history(
        self,
        memory_id: str = "default",
        max_length: Optional[int] = None,
        max_round: int = 5,
        include_timestamp: bool = True,
        include_importance: bool = False
    ) -> str:
        """构建历史对话（包含长期记忆）"""
        # 先获取基类的短期记忆
        short_term = super().build_history(
            memory_id=memory_id,
            max_length=max_length,
            max_round=max_round,
            include_timestamp=include_timestamp
        )
        
        # 获取重要的长期记忆
        important_memories = self.get_important_memories(
            memory_id=memory_id,
            top_n=3,
            min_importance=0.7
        )
        
        if not important_memories:
            return short_term
        
        # 构建长期记忆部分
        long_term_parts = ["[重要记忆]"]
        for mem in important_memories:
            content = mem.content.get("content", "")
            if include_importance:
                long_term_parts.append(f"  (重要性:{mem.importance:.2f}) {content}")
            else:
                long_term_parts.append(f"  - {content}")
        
        long_term_str = "\n".join(long_term_parts)
        
        return f"{long_term_str}\n\n[近期对话]\n{short_term}"
    
    def link_memories(
        self,
        memory_id: str,
        source_id: str,
        target_id: str
    ):
        """链接两个记忆"""
        memories = self._long_term_memories.get(memory_id, [])
        
        source = None
        target = None
        
        for mem in memories:
            if mem.unique_id == source_id:
                source = mem
            if mem.unique_id == target_id:
                target = mem
        
        if source and target:
            if target_id not in source.associations:
                source.associations.append(target_id)
            if source_id not in target.associations:
                target.associations.append(source_id)
            
            self._save()
    
    def _save(self):
        """持久化到文件"""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {}
        for memory_id, memories in self._long_term_memories.items():
            data[memory_id] = [
                {
                    "content": m.content,
                    "score": m.score,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata,
                    "unique_id": m.unique_id,
                    "vector": m.vector,
                    "importance": m.importance,
                    "access_count": m.access_count,
                    "last_accessed": m.last_accessed,
                    "associations": m.associations,
                    "summary": m.summary
                }
                for m in memories
            ]
        
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load(self):
        """从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for memory_id, memories in data.items():
                self._long_term_memories[memory_id] = []
                for m in memories:
                    unit = LongTermMemoryUnit(
                        content=m["content"],
                        score=m.get("score", 1.0),
                        timestamp=m.get("timestamp", time.time()),
                        metadata=m.get("metadata", {}),
                        unique_id=m.get("unique_id")
                    )
                    unit.vector = m.get("vector")
                    unit.importance = m.get("importance", 0.5)
                    unit.access_count = m.get("access_count", 0)
                    unit.last_accessed = m.get("last_accessed", time.time())
                    unit.associations = m.get("associations", [])
                    unit.summary = m.get("summary")
                    
                    self._long_term_memories[memory_id].append(unit)
                    
        except Exception as e:
            logger.error(f"Failed to load long-term memory: {e}")
    
    async def stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_memories = sum(
            len(mems) for mems in self._long_term_memories.values()
        )
        
        stats = {
            "total_memories": total_memories,
            "memory_ids": list(self._long_term_memories.keys()),
            "by_memory_id": {
                mid: {
                    "count": len(mems),
                    "avg_importance": sum(m.importance for m in mems) / len(mems) if mems else 0,
                    "total_accesses": sum(m.access_count for m in mems)
                }
                for mid, mems in self._long_term_memories.items()
            },
            "has_embedder": self.embedder is not None,
            "has_llm": self.llm is not None,
            "storage_path": str(self.storage_path) if self.storage_path else None
        }
        
        return stats
