"""
Alphora Memory Component

智能记忆管理组件，支持：
- 多类型记忆（短期/长期/工作/情景/反思）
- 可插拔的衰减策略
- 灵活的检索策略
- LLM驱动的记忆反思
- 持久化存储

使用示例:
```python
from alphora.memory import MemoryManager

# 基本使用
memory = MemoryManager()

# 添加记忆
memory.add_memory(
    role="user",
    content="你好，我想学习Python",
    memory_id="chat_001"
)

memory.add_memory(
    role="assistant", 
    content="好的，我来帮你学习Python。你有什么基础吗？",
    memory_id="chat_001"
)

# 构建历史
history = memory.build_history(memory_id="chat_001", max_round=5)
print(history)

# 搜索记忆
results = memory.search("Python", memory_id="chat_001")
for r in results:
    print(f"Score: {r.score:.2f}, Content: {r.memory.get_content_text()[:50]}")

# 使用文件存储
memory = MemoryManager(storage_path="./data/memory.json")

# 使用SQLite存储
memory = MemoryManager(
    storage_path="./data/memory.db",
    storage_type="sqlite"
)

# 启用LLM反思
from alphora.models import OpenAILike
llm = OpenAILike(api_key="...", base_url="...", model_name="...")
memory = MemoryManager(llm=llm, auto_reflect=True)

# 手动触发反思
import asyncio
reflection = asyncio.run(memory.reflect(memory_id="chat_001"))
print(reflection.summary)
```
"""

from alphora.memory.memory_unit import (
    MemoryUnit,
    MemoryType,
    create_memory,
    extract_keywords
)

from alphora.memory.decay import (
    DecayStrategy,
    LinearDecay,
    ExponentialDecay,
    LogarithmicDecay,
    TimeBasedDecay,
    ImportanceAwareDecay,
    AdaptiveDecay,
    CompositeDecay,
    NoDecay,
    get_decay_strategy,
    list_decay_strategies
)

from alphora.memory.retrieval import (
    RetrievalStrategy,
    RetrievalResult,
    KeywordRetrieval,
    FuzzyRetrieval,
    RegexRetrieval,
    TagRetrieval,
    TimeRangeRetrieval,
    HybridRetrieval,
    SemanticRetrieval,
    get_retrieval_strategy,
    search_memories
)

from alphora.memory.reflection import (
    MemoryReflector,
    AutoReflector,
    ReflectionResult
)

from alphora.memory.manager import (
    MemoryManager,
    BaseMemory  # 兼容旧接口
)


__all__ = [
    # 核心类
    "MemoryManager",
    "BaseMemory",  # 兼容
    "MemoryUnit",
    "MemoryType",
    
    # 工厂函数
    "create_memory",
    "extract_keywords",
    
    # 衰减策略
    "DecayStrategy",
    "LinearDecay",
    "ExponentialDecay",
    "LogarithmicDecay",
    "TimeBasedDecay",
    "ImportanceAwareDecay",
    "AdaptiveDecay",
    "CompositeDecay",
    "NoDecay",
    "get_decay_strategy",
    "list_decay_strategies",
    
    # 检索策略
    "RetrievalStrategy",
    "RetrievalResult",
    "KeywordRetrieval",
    "FuzzyRetrieval",
    "RegexRetrieval",
    "TagRetrieval",
    "TimeRangeRetrieval",
    "HybridRetrieval",
    "SemanticRetrieval",
    "get_retrieval_strategy",
    "search_memories",
    
    # 反思
    "MemoryReflector",
    "AutoReflector",
    "ReflectionResult",
]
