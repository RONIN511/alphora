"""
Alphora Storage Component

统一的存储组件，支持多种后端实现。

使用示例:
```python
from alphora.storage import JSONStorage, SQLiteStorage, InMemoryStorage

# JSON存储（适合开发调试）
storage = JSONStorage("./data/storage.json")

# SQLite存储（适合生产环境）
storage = SQLiteStorage("./data/storage.db")

# 内存存储（适合测试）
storage = InMemoryStorage()

# 统一接口
storage.set("key", "value")
value = storage.get("key")

# 列表操作
storage.rpush("list", "item1", "item2")
items = storage.lrange("list", 0, -1)

# 哈希操作
storage.hset("hash", "field", "value")
data = storage.hgetall("hash")

# 上下文管理
with JSONStorage("./data/storage.json") as storage:
    storage.set("key", "value")
# 自动保存
```
"""

from alphora.storage.base_storage import (
    StorageBackend,
    StorageConfig,
    StorageType,
    InMemoryStorage
)
from alphora.storage.json_storage import JSONStorage
from alphora.storage.sqlite_storage import SQLiteStorage
from alphora.storage.serializers import (
    Serializer,
    JSONSerializer,
    PickleSerializer,
    SerializationError,
    DeserializationError,
    get_serializer
)


def create_storage(
    storage_type: str = "json",
    path: str = None,
    **kwargs
) -> StorageBackend:
    """
    创建存储实例的工厂函数
    
    Args:
        storage_type: 存储类型 (json, sqlite, memory)
        path: 存储路径
        **kwargs: 传递给存储构造函数的额外参数
        
    Returns:
        StorageBackend实例
        
    示例:
    ```python
    # 创建JSON存储
    storage = create_storage("json", "./data/storage.json")
    
    # 创建SQLite存储
    storage = create_storage("sqlite", "./data/storage.db")
    
    # 创建内存存储
    storage = create_storage("memory")
    ```
    """
    storage_classes = {
        "json": JSONStorage,
        "sqlite": SQLiteStorage,
        "memory": InMemoryStorage,
    }
    
    if storage_type not in storage_classes:
        raise ValueError(
            f"Unknown storage type: {storage_type}. "
            f"Available: {list(storage_classes.keys())}"
        )
    
    return storage_classes[storage_type](path=path, **kwargs)


__all__ = [
    # 基类
    "StorageBackend",
    "StorageConfig",
    "StorageType",
    
    # 存储实现
    "InMemoryStorage",
    "JSONStorage",
    "SQLiteStorage",
    
    # 序列化
    "Serializer",
    "JSONSerializer",
    "PickleSerializer",
    "SerializationError",
    "DeserializationError",
    "get_serializer",
    
    # 工厂函数
    "create_storage",
]
