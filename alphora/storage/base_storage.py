"""
Storage Backend 抽象基类

提供统一的存储接口，支持多种后端实现（JSON、SQLite等）
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Iterator, TypeVar, Generic
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import time

T = TypeVar('T')


class StorageType(Enum):
    """存储类型"""
    JSON = "json"
    SQLITE = "sqlite"
    MEMORY = "memory"


@dataclass
class StorageConfig:
    """存储配置"""
    path: Optional[str] = None
    auto_save: bool = True
    save_interval: int = 60  # 自动保存间隔（秒）
    compression: bool = False
    encryption_key: Optional[str] = None


class StorageBackend(ABC):
    """
    存储后端抽象基类
    
    提供类似 Redis 的接口，便于不同后端实现统一调用。
    
    使用示例:
    ```python
    # JSON存储
    storage = JSONStorage("./data/storage.json")
    
    # SQLite存储
    storage = SQLiteStorage("./data/storage.db")
    
    # 基本操作
    storage.set("user:1:name", "Alice")
    name = storage.get("user:1:name")
    
    # 列表操作
    storage.lpush("user:1:history", {"role": "user", "content": "hello"})
    history = storage.lrange("user:1:history", 0, -1)
    
    # 批量操作
    storage.mset({"key1": "value1", "key2": "value2"})
    values = storage.mget(["key1", "key2"])
    ```
    """
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self._last_save_time = time.time()
    
    # ==================== 基本操作 ====================
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取值
        
        Args:
            key: 键名
            default: 默认值
            
        Returns:
            存储的值，不存在则返回default
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置值
        
        Args:
            key: 键名
            value: 值（需要可序列化）
            ttl: 过期时间（秒），None表示永不过期
            
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        删除键
        
        Args:
            key: 键名
            
        Returns:
            是否成功删除
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """
        获取匹配模式的所有键
        
        Args:
            pattern: 匹配模式，支持 * 通配符
                - "*" 匹配所有
                - "user:*" 匹配以 user: 开头的键
                - "*:name" 匹配以 :name 结尾的键
                
        Returns:
            匹配的键列表
        """
        pass
    
    # ==================== 批量操作 ====================
    
    def mget(self, keys: List[str]) -> Dict[str, Any]:
        """
        批量获取
        
        Args:
            keys: 键名列表
            
        Returns:
            键值字典（不存在的键不包含在结果中）
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    def mset(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        批量设置
        
        Args:
            data: 键值字典
            ttl: 过期时间
            
        Returns:
            是否全部成功
        """
        success = True
        for key, value in data.items():
            if not self.set(key, value, ttl):
                success = False
        return success
    
    def mdelete(self, keys: List[str]) -> int:
        """
        批量删除
        
        Args:
            keys: 键名列表
            
        Returns:
            成功删除的数量
        """
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count
    
    # ==================== 列表操作 ====================
    
    @abstractmethod
    def lpush(self, key: str, *values: Any) -> int:
        """
        从左侧插入列表
        
        Args:
            key: 键名
            values: 要插入的值
            
        Returns:
            插入后列表长度
        """
        pass
    
    @abstractmethod
    def rpush(self, key: str, *values: Any) -> int:
        """
        从右侧插入列表
        
        Args:
            key: 键名
            values: 要插入的值
            
        Returns:
            插入后列表长度
        """
        pass
    
    @abstractmethod
    def lpop(self, key: str) -> Optional[Any]:
        """从左侧弹出"""
        pass
    
    @abstractmethod
    def rpop(self, key: str) -> Optional[Any]:
        """从右侧弹出"""
        pass
    
    @abstractmethod
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """
        获取列表范围
        
        Args:
            key: 键名
            start: 起始索引
            end: 结束索引（-1表示到末尾）
            
        Returns:
            列表切片
        """
        pass
    
    @abstractmethod
    def llen(self, key: str) -> int:
        """获取列表长度"""
        pass
    
    @abstractmethod
    def lindex(self, key: str, index: int) -> Optional[Any]:
        """获取列表指定位置元素"""
        pass
    
    @abstractmethod
    def lset(self, key: str, index: int, value: Any) -> bool:
        """设置列表指定位置的值"""
        pass
    
    @abstractmethod
    def lrem(self, key: str, count: int, value: Any) -> int:
        """
        移除列表中的元素
        
        Args:
            key: 键名
            count: 移除数量（0表示全部，正数从头开始，负数从尾开始）
            value: 要移除的值
            
        Returns:
            移除的数量
        """
        pass
    
    # ==================== 哈希操作 ====================
    
    @abstractmethod
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        """获取哈希字段值"""
        pass
    
    @abstractmethod
    def hset(self, key: str, field: str, value: Any) -> bool:
        """设置哈希字段值"""
        pass
    
    @abstractmethod
    def hdel(self, key: str, *fields: str) -> int:
        """删除哈希字段"""
        pass
    
    @abstractmethod
    def hgetall(self, key: str) -> Dict[str, Any]:
        """获取哈希所有字段"""
        pass
    
    @abstractmethod
    def hkeys(self, key: str) -> List[str]:
        """获取哈希所有字段名"""
        pass
    
    @abstractmethod
    def hexists(self, key: str, field: str) -> bool:
        """检查哈希字段是否存在"""
        pass
    
    # ==================== 计数器操作 ====================
    
    def incr(self, key: str, amount: int = 1) -> int:
        """
        递增计数器
        
        Args:
            key: 键名
            amount: 递增量
            
        Returns:
            递增后的值
        """
        current = self.get(key, 0)
        if not isinstance(current, (int, float)):
            current = 0
        new_value = int(current) + amount
        self.set(key, new_value)
        return new_value
    
    def decr(self, key: str, amount: int = 1) -> int:
        """递减计数器"""
        return self.incr(key, -amount)
    
    # ==================== 过期管理 ====================
    
    @abstractmethod
    def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间"""
        pass
    
    @abstractmethod
    def ttl(self, key: str) -> int:
        """
        获取剩余过期时间
        
        Returns:
            剩余秒数，-1表示永不过期，-2表示不存在
        """
        pass
    
    @abstractmethod
    def persist(self, key: str) -> bool:
        """移除过期时间，使键永久有效"""
        pass
    
    # ==================== 事务支持 ====================
    
    @contextmanager
    def transaction(self):
        """
        事务上下文管理器
        
        使用示例:
        ```python
        with storage.transaction():
            storage.set("key1", "value1")
            storage.set("key2", "value2")
        ```
        """
        self._begin_transaction()
        try:
            yield self
            self._commit_transaction()
        except Exception as e:
            self._rollback_transaction()
            raise e
    
    def _begin_transaction(self):
        """开始事务（子类可重写）"""
        pass
    
    def _commit_transaction(self):
        """提交事务（子类可重写）"""
        pass
    
    def _rollback_transaction(self):
        """回滚事务（子类可重写）"""
        pass
    
    # ==================== 持久化 ====================
    
    @abstractmethod
    def save(self) -> bool:
        """持久化到存储"""
        pass
    
    @abstractmethod
    def load(self) -> bool:
        """从存储加载"""
        pass
    
    def maybe_save(self):
        """根据配置决定是否保存"""
        if self.config.auto_save:
            current_time = time.time()
            if current_time - self._last_save_time >= self.config.save_interval:
                self.save()
                self._last_save_time = current_time
    
    # ==================== 工具方法 ====================
    
    @abstractmethod
    def clear(self) -> bool:
        """清空所有数据"""
        pass
    
    @abstractmethod
    def size(self) -> int:
        """获取存储的键数量"""
        pass
    
    def info(self) -> Dict[str, Any]:
        """获取存储信息"""
        return {
            "type": self.__class__.__name__,
            "size": self.size(),
            "config": {
                "path": self.config.path,
                "auto_save": self.config.auto_save,
            }
        }
    
    def __contains__(self, key: str) -> bool:
        return self.exists(key)
    
    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: str, value: Any):
        self.set(key, value)
    
    def __delitem__(self, key: str):
        if not self.delete(key):
            raise KeyError(key)
    
    def __len__(self) -> int:
        return self.size()
    
    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())
    
    # ==================== 上下文管理 ====================
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()
        self.close()
    
    def close(self):
        """关闭存储连接（子类可重写）"""
        pass


class InMemoryStorage(StorageBackend):
    """
    内存存储实现
    
    用于测试或不需要持久化的场景
    """
    
    def __init__(self, config: Optional[StorageConfig] = None):
        super().__init__(config)
        self._data: Dict[str, Any] = {}
        self._expires: Dict[str, float] = {}  # key -> expire_timestamp
        self._lists: Dict[str, List[Any]] = {}
        self._hashes: Dict[str, Dict[str, Any]] = {}
    
    def _check_expired(self, key: str) -> bool:
        """检查并清理过期键"""
        if key in self._expires:
            if time.time() > self._expires[key]:
                self._cleanup_key(key)
                return True
        return False
    
    def _cleanup_key(self, key: str):
        """清理键的所有相关数据"""
        self._data.pop(key, None)
        self._expires.pop(key, None)
        self._lists.pop(key, None)
        self._hashes.pop(key, None)
    
    def get(self, key: str, default: Any = None) -> Any:
        if self._check_expired(key):
            return default
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        self._data[key] = value
        if ttl is not None:
            self._expires[key] = time.time() + ttl
        elif key in self._expires:
            del self._expires[key]
        return True
    
    def delete(self, key: str) -> bool:
        existed = key in self._data or key in self._lists or key in self._hashes
        self._cleanup_key(key)
        return existed
    
    def exists(self, key: str) -> bool:
        if self._check_expired(key):
            return False
        return key in self._data or key in self._lists or key in self._hashes
    
    def keys(self, pattern: str = "*") -> List[str]:
        import fnmatch
        all_keys = set(self._data.keys()) | set(self._lists.keys()) | set(self._hashes.keys())
        # 清理过期键
        for key in list(all_keys):
            self._check_expired(key)
        all_keys = set(self._data.keys()) | set(self._lists.keys()) | set(self._hashes.keys())
        
        if pattern == "*":
            return list(all_keys)
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
    
    # 列表操作
    def lpush(self, key: str, *values: Any) -> int:
        if key not in self._lists:
            self._lists[key] = []
        for v in reversed(values):
            self._lists[key].insert(0, v)
        return len(self._lists[key])
    
    def rpush(self, key: str, *values: Any) -> int:
        if key not in self._lists:
            self._lists[key] = []
        self._lists[key].extend(values)
        return len(self._lists[key])
    
    def lpop(self, key: str) -> Optional[Any]:
        if key not in self._lists or not self._lists[key]:
            return None
        return self._lists[key].pop(0)
    
    def rpop(self, key: str) -> Optional[Any]:
        if key not in self._lists or not self._lists[key]:
            return None
        return self._lists[key].pop()
    
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        if key not in self._lists:
            return []
        lst = self._lists[key]
        if end == -1:
            end = len(lst)
        else:
            end = end + 1
        return lst[start:end]
    
    def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))
    
    def lindex(self, key: str, index: int) -> Optional[Any]:
        if key not in self._lists:
            return None
        try:
            return self._lists[key][index]
        except IndexError:
            return None
    
    def lset(self, key: str, index: int, value: Any) -> bool:
        if key not in self._lists:
            return False
        try:
            self._lists[key][index] = value
            return True
        except IndexError:
            return False
    
    def lrem(self, key: str, count: int, value: Any) -> int:
        if key not in self._lists:
            return 0
        removed = 0
        lst = self._lists[key]
        if count == 0:
            # 移除所有
            while value in lst:
                lst.remove(value)
                removed += 1
        elif count > 0:
            # 从头开始
            for _ in range(count):
                if value in lst:
                    lst.remove(value)
                    removed += 1
                else:
                    break
        else:
            # 从尾开始
            for _ in range(-count):
                try:
                    idx = len(lst) - 1 - lst[::-1].index(value)
                    lst.pop(idx)
                    removed += 1
                except ValueError:
                    break
        return removed
    
    # 哈希操作
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        if key not in self._hashes:
            return default
        return self._hashes[key].get(field, default)
    
    def hset(self, key: str, field: str, value: Any) -> bool:
        if key not in self._hashes:
            self._hashes[key] = {}
        self._hashes[key][field] = value
        return True
    
    def hdel(self, key: str, *fields: str) -> int:
        if key not in self._hashes:
            return 0
        count = 0
        for field in fields:
            if field in self._hashes[key]:
                del self._hashes[key][field]
                count += 1
        return count
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        return self._hashes.get(key, {}).copy()
    
    def hkeys(self, key: str) -> List[str]:
        return list(self._hashes.get(key, {}).keys())
    
    def hexists(self, key: str, field: str) -> bool:
        return field in self._hashes.get(key, {})
    
    # 过期管理
    def expire(self, key: str, seconds: int) -> bool:
        if not self.exists(key):
            return False
        self._expires[key] = time.time() + seconds
        return True
    
    def ttl(self, key: str) -> int:
        if not self.exists(key):
            return -2
        if key not in self._expires:
            return -1
        remaining = int(self._expires[key] - time.time())
        return max(0, remaining)
    
    def persist(self, key: str) -> bool:
        if key in self._expires:
            del self._expires[key]
            return True
        return False
    
    # 持久化（内存存储不做实际持久化）
    def save(self) -> bool:
        return True
    
    def load(self) -> bool:
        return True
    
    def clear(self) -> bool:
        self._data.clear()
        self._expires.clear()
        self._lists.clear()
        self._hashes.clear()
        return True
    
    def size(self) -> int:
        return len(self._data) + len(self._lists) + len(self._hashes)
