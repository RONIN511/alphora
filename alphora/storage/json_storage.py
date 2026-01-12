"""
JSON文件存储实现

特点：
- 单文件存储，人类可读
- 适合开发调试和轻量级部署
- 支持自动保存
- 支持压缩
"""

import json
import time
import gzip
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import fnmatch

from alphora.storage.base_storage import StorageBackend, StorageConfig
from alphora.storage.serializers import JSONSerializer, ExtendedJSONEncoder, extended_json_decoder


class JSONStorage(StorageBackend):
    """
    JSON文件存储
    
    使用示例:
    ```python
    # 基本使用
    storage = JSONStorage("./data/storage.json")
    storage.set("key", "value")
    storage.save()
    
    # 带配置
    config = StorageConfig(
        path="./data/storage.json",
        auto_save=True,
        save_interval=30,
        compression=True
    )
    storage = JSONStorage(config=config)
    
    # 上下文管理
    with JSONStorage("./data/storage.json") as storage:
        storage.set("key", "value")
    # 自动保存
    ```
    """
    
    def __init__(
        self,
        path: Optional[str] = None,
        config: Optional[StorageConfig] = None,
        auto_load: bool = True
    ):
        if config is None:
            config = StorageConfig(path=path)
        elif path is not None:
            config.path = path
            
        super().__init__(config)
        
        self._data: Dict[str, Any] = {}
        self._lists: Dict[str, List[Any]] = {}
        self._hashes: Dict[str, Dict[str, Any]] = {}
        self._expires: Dict[str, float] = {}
        
        self._lock = threading.RLock()
        self._dirty = False  # 标记是否有未保存的更改
        
        self._serializer = JSONSerializer(indent=2)
        
        # 自动加载
        if auto_load and self.config.path:
            self.load()
    
    def _get_path(self) -> Path:
        """获取存储路径"""
        if not self.config.path:
            raise ValueError("Storage path not configured")
        path = Path(self.config.path)
        if self.config.compression and not path.suffix.endswith('.gz'):
            path = path.with_suffix(path.suffix + '.gz')
        return path
    
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
        self._dirty = True
    
    def _mark_dirty(self):
        """标记数据已修改"""
        self._dirty = True
        self.maybe_save()
    
    # ==================== 基本操作 ====================
    
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if self._check_expired(key):
                return default
            return self._data.get(key, default)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        with self._lock:
            self._data[key] = value
            if ttl is not None:
                self._expires[key] = time.time() + ttl
            elif key in self._expires:
                del self._expires[key]
            self._mark_dirty()
            return True
    
    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._data or key in self._lists or key in self._hashes
            if existed:
                self._cleanup_key(key)
            return existed
    
    def exists(self, key: str) -> bool:
        with self._lock:
            if self._check_expired(key):
                return False
            return key in self._data or key in self._lists or key in self._hashes
    
    def keys(self, pattern: str = "*") -> List[str]:
        with self._lock:
            # 清理过期键
            all_keys = set(self._data.keys()) | set(self._lists.keys()) | set(self._hashes.keys())
            for key in list(all_keys):
                self._check_expired(key)
            
            all_keys = set(self._data.keys()) | set(self._lists.keys()) | set(self._hashes.keys())
            
            if pattern == "*":
                return list(all_keys)
            return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
    
    # ==================== 列表操作 ====================
    
    def lpush(self, key: str, *values: Any) -> int:
        with self._lock:
            if key not in self._lists:
                self._lists[key] = []
            for v in reversed(values):
                self._lists[key].insert(0, v)
            self._mark_dirty()
            return len(self._lists[key])
    
    def rpush(self, key: str, *values: Any) -> int:
        with self._lock:
            if key not in self._lists:
                self._lists[key] = []
            self._lists[key].extend(values)
            self._mark_dirty()
            return len(self._lists[key])
    
    def lpop(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._lists or not self._lists[key]:
                return None
            self._mark_dirty()
            return self._lists[key].pop(0)
    
    def rpop(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._lists or not self._lists[key]:
                return None
            self._mark_dirty()
            return self._lists[key].pop()
    
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        with self._lock:
            if key not in self._lists:
                return []
            lst = self._lists[key]
            if end == -1:
                end = len(lst)
            else:
                end = end + 1
            return lst[start:end]
    
    def llen(self, key: str) -> int:
        with self._lock:
            return len(self._lists.get(key, []))
    
    def lindex(self, key: str, index: int) -> Optional[Any]:
        with self._lock:
            if key not in self._lists:
                return None
            try:
                return self._lists[key][index]
            except IndexError:
                return None
    
    def lset(self, key: str, index: int, value: Any) -> bool:
        with self._lock:
            if key not in self._lists:
                return False
            try:
                self._lists[key][index] = value
                self._mark_dirty()
                return True
            except IndexError:
                return False
    
    def lrem(self, key: str, count: int, value: Any) -> int:
        with self._lock:
            if key not in self._lists:
                return 0
            removed = 0
            lst = self._lists[key]
            if count == 0:
                original_len = len(lst)
                self._lists[key] = [x for x in lst if x != value]
                removed = original_len - len(self._lists[key])
            elif count > 0:
                for _ in range(count):
                    if value in lst:
                        lst.remove(value)
                        removed += 1
                    else:
                        break
            else:
                for _ in range(-count):
                    try:
                        idx = len(lst) - 1 - lst[::-1].index(value)
                        lst.pop(idx)
                        removed += 1
                    except ValueError:
                        break
            if removed > 0:
                self._mark_dirty()
            return removed
    
    # ==================== 哈希操作 ====================
    
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        with self._lock:
            if key not in self._hashes:
                return default
            return self._hashes[key].get(field, default)
    
    def hset(self, key: str, field: str, value: Any) -> bool:
        with self._lock:
            if key not in self._hashes:
                self._hashes[key] = {}
            self._hashes[key][field] = value
            self._mark_dirty()
            return True
    
    def hdel(self, key: str, *fields: str) -> int:
        with self._lock:
            if key not in self._hashes:
                return 0
            count = 0
            for field in fields:
                if field in self._hashes[key]:
                    del self._hashes[key][field]
                    count += 1
            if count > 0:
                self._mark_dirty()
            return count
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        with self._lock:
            return self._hashes.get(key, {}).copy()
    
    def hkeys(self, key: str) -> List[str]:
        with self._lock:
            return list(self._hashes.get(key, {}).keys())
    
    def hexists(self, key: str, field: str) -> bool:
        with self._lock:
            return field in self._hashes.get(key, {})
    
    # ==================== 过期管理 ====================
    
    def expire(self, key: str, seconds: int) -> bool:
        with self._lock:
            if not self.exists(key):
                return False
            self._expires[key] = time.time() + seconds
            self._mark_dirty()
            return True
    
    def ttl(self, key: str) -> int:
        with self._lock:
            if not self.exists(key):
                return -2
            if key not in self._expires:
                return -1
            remaining = int(self._expires[key] - time.time())
            return max(0, remaining)
    
    def persist(self, key: str) -> bool:
        with self._lock:
            if key in self._expires:
                del self._expires[key]
                self._mark_dirty()
                return True
            return False
    
    # ==================== 持久化 ====================
    
    def save(self) -> bool:
        """保存到文件"""
        if not self.config.path:
            return False
        
        with self._lock:
            path = self._get_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # 准备数据
            data = {
                "__meta__": {
                    "version": "1.0",
                    "saved_at": time.time(),
                    "type": "alphora_storage"
                },
                "data": self._data,
                "lists": self._lists,
                "hashes": self._hashes,
                "expires": self._expires
            }
            
            # 写入临时文件然后重命名（原子操作）
            temp_path = path.with_suffix('.tmp')
            
            try:
                content = json.dumps(
                    data,
                    cls=ExtendedJSONEncoder,
                    indent=2,
                    ensure_ascii=False
                )
                
                if self.config.compression:
                    with gzip.open(temp_path, 'wt', encoding='utf-8') as f:
                        f.write(content)
                else:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                
                # 原子重命名
                shutil.move(str(temp_path), str(path))
                self._dirty = False
                self._last_save_time = time.time()
                return True
                
            except Exception as e:
                if temp_path.exists():
                    temp_path.unlink()
                raise e
    
    def load(self) -> bool:
        """从文件加载"""
        if not self.config.path:
            return False
        
        path = self._get_path()
        
        # 尝试非压缩版本
        if not path.exists():
            alt_path = Path(self.config.path)
            if alt_path.exists():
                path = alt_path
            else:
                return False
        
        with self._lock:
            try:
                if path.suffix == '.gz':
                    with gzip.open(path, 'rt', encoding='utf-8') as f:
                        content = f.read()
                else:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                
                data = json.loads(content, object_hook=extended_json_decoder)
                
                # 验证格式
                if data.get("__meta__", {}).get("type") != "alphora_storage":
                    # 兼容旧格式
                    self._data = data
                    self._lists = {}
                    self._hashes = {}
                    self._expires = {}
                else:
                    self._data = data.get("data", {})
                    self._lists = data.get("lists", {})
                    self._hashes = data.get("hashes", {})
                    self._expires = data.get("expires", {})
                
                # 清理过期数据
                self._cleanup_all_expired()
                
                self._dirty = False
                return True
                
            except (json.JSONDecodeError, IOError) as e:
                # 尝试加载备份
                backup_path = path.with_suffix('.bak')
                if backup_path.exists():
                    shutil.copy(str(backup_path), str(path))
                    return self.load()
                return False
    
    def _cleanup_all_expired(self):
        """清理所有过期数据"""
        now = time.time()
        expired_keys = [k for k, exp in self._expires.items() if now > exp]
        for key in expired_keys:
            self._cleanup_key(key)
    
    # ==================== 工具方法 ====================
    
    def clear(self) -> bool:
        with self._lock:
            self._data.clear()
            self._lists.clear()
            self._hashes.clear()
            self._expires.clear()
            self._mark_dirty()
            return True
    
    def size(self) -> int:
        with self._lock:
            return len(self._data) + len(self._lists) + len(self._hashes)
    
    def backup(self, backup_path: Optional[str] = None) -> bool:
        """创建备份"""
        if not self.config.path:
            return False
        
        path = self._get_path()
        if not path.exists():
            return False
        
        if backup_path:
            target = Path(backup_path)
        else:
            target = path.with_suffix('.bak')
        
        shutil.copy(str(path), str(target))
        return True
    
    def compact(self) -> bool:
        """压缩存储文件（移除过期数据并重新保存）"""
        with self._lock:
            self._cleanup_all_expired()
            return self.save()
    
    def info(self) -> Dict[str, Any]:
        """获取存储信息"""
        info = super().info()
        
        path = self._get_path() if self.config.path else None
        if path and path.exists():
            info["file_size"] = path.stat().st_size
            info["file_path"] = str(path)
        
        info.update({
            "data_count": len(self._data),
            "list_count": len(self._lists),
            "hash_count": len(self._hashes),
            "expires_count": len(self._expires),
            "dirty": self._dirty,
            "compression": self.config.compression
        })
        
        return info
    
    def __repr__(self) -> str:
        return f"JSONStorage(path={self.config.path}, size={self.size()}, dirty={self._dirty})"
