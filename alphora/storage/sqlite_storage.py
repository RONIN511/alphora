"""
SQLite存储实现

特点：
- 适合生产环境
- 支持并发访问
- 查询高效，支持索引
- 支持事务
"""

import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
import fnmatch

from alphora.storage.base_storage import StorageBackend, StorageConfig
from alphora.storage.serializers import (
    JSONSerializer,
    ExtendedJSONEncoder,
    extended_json_decoder,
    safe_serialize,
    safe_deserialize
)


class SQLiteStorage(StorageBackend):
    """
    SQLite存储实现
    
    使用示例:
    ```python
    # 基本使用
    storage = SQLiteStorage("./data/storage.db")
    storage.set("key", "value")
    
    # 带配置
    config = StorageConfig(path="./data/storage.db")
    storage = SQLiteStorage(config=config)
    
    # 事务
    with storage.transaction():
        storage.set("key1", "value1")
        storage.set("key2", "value2")
    
    # 上下文管理
    with SQLiteStorage("./data/storage.db") as storage:
        storage.set("key", "value")
    ```
    """
    
    # 表定义
    SCHEMA = """
    -- 键值存储
    CREATE TABLE IF NOT EXISTS kv_store (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        type TEXT DEFAULT 'data',
        expires_at REAL,
        created_at REAL DEFAULT (strftime('%s', 'now')),
        updated_at REAL DEFAULT (strftime('%s', 'now'))
    );
    
    -- 列表存储
    CREATE TABLE IF NOT EXISTS list_store (
        key TEXT NOT NULL,
        idx INTEGER NOT NULL,
        value TEXT NOT NULL,
        created_at REAL DEFAULT (strftime('%s', 'now')),
        PRIMARY KEY (key, idx)
    );
    
    -- 哈希存储
    CREATE TABLE IF NOT EXISTS hash_store (
        key TEXT NOT NULL,
        field TEXT NOT NULL,
        value TEXT NOT NULL,
        created_at REAL DEFAULT (strftime('%s', 'now')),
        updated_at REAL DEFAULT (strftime('%s', 'now')),
        PRIMARY KEY (key, field)
    );
    
    -- 索引
    CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv_store(expires_at);
    CREATE INDEX IF NOT EXISTS idx_kv_type ON kv_store(type);
    CREATE INDEX IF NOT EXISTS idx_list_key ON list_store(key);
    CREATE INDEX IF NOT EXISTS idx_hash_key ON hash_store(key);
    
    -- 元数据
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """
    
    def __init__(
        self,
        path: Optional[str] = None,
        config: Optional[StorageConfig] = None,
        check_same_thread: bool = False
    ):
        if config is None:
            config = StorageConfig(path=path)
        elif path is not None:
            config.path = path
            
        super().__init__(config)
        
        self._check_same_thread = check_same_thread
        self._local = threading.local()
        self._serializer = JSONSerializer()
        
        # 初始化数据库
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            if not self.config.path:
                # 内存数据库
                conn = sqlite3.connect(
                    ':memory:',
                    check_same_thread=self._check_same_thread
                )
            else:
                path = Path(self.config.path)
                path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(
                    str(path),
                    check_same_thread=self._check_same_thread
                )
            
            conn.row_factory = sqlite3.Row
            # 启用外键
            conn.execute("PRAGMA foreign_keys = ON")
            # 优化性能
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            
            self._local.connection = conn
        
        return self._local.connection
    
    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_connection()
        conn.executescript(self.SCHEMA)
        
        # 设置版本
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("version", "1.0")
        )
        conn.commit()
    
    def _serialize(self, value: Any) -> str:
        """序列化值"""
        return safe_serialize(value, self._serializer)
    
    def _deserialize(self, value: str) -> Any:
        """反序列化值"""
        return safe_deserialize(value, self._serializer)
    
    def _cleanup_expired(self):
        """清理过期数据"""
        conn = self._get_connection()
        now = time.time()
        conn.execute(
            "DELETE FROM kv_store WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,)
        )
        conn.commit()
    
    # ==================== 基本操作 ====================
    
    def get(self, key: str, default: Any = None) -> Any:
        conn = self._get_connection()
        now = time.time()
        
        cursor = conn.execute(
            """SELECT value FROM kv_store 
               WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)""",
            (key, now)
        )
        row = cursor.fetchone()
        
        if row is None:
            return default
        
        return self._deserialize(row['value'])
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        conn = self._get_connection()
        now = time.time()
        expires_at = now + ttl if ttl else None
        
        conn.execute(
            """INSERT OR REPLACE INTO kv_store (key, value, expires_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (key, self._serialize(value), expires_at, now)
        )
        conn.commit()
        return True
    
    def delete(self, key: str) -> bool:
        conn = self._get_connection()
        
        # 删除所有相关数据
        cursor = conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
        count1 = cursor.rowcount
        
        cursor = conn.execute("DELETE FROM list_store WHERE key = ?", (key,))
        count2 = cursor.rowcount
        
        cursor = conn.execute("DELETE FROM hash_store WHERE key = ?", (key,))
        count3 = cursor.rowcount
        
        conn.commit()
        return (count1 + count2 + count3) > 0
    
    def exists(self, key: str) -> bool:
        conn = self._get_connection()
        now = time.time()
        
        # 检查键值存储
        cursor = conn.execute(
            """SELECT 1 FROM kv_store 
               WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)""",
            (key, now)
        )
        if cursor.fetchone():
            return True
        
        # 检查列表
        cursor = conn.execute("SELECT 1 FROM list_store WHERE key = ? LIMIT 1", (key,))
        if cursor.fetchone():
            return True
        
        # 检查哈希
        cursor = conn.execute("SELECT 1 FROM hash_store WHERE key = ? LIMIT 1", (key,))
        if cursor.fetchone():
            return True
        
        return False
    
    def keys(self, pattern: str = "*") -> List[str]:
        conn = self._get_connection()
        now = time.time()
        
        all_keys = set()
        
        # 从键值存储获取
        cursor = conn.execute(
            """SELECT DISTINCT key FROM kv_store 
               WHERE expires_at IS NULL OR expires_at > ?""",
            (now,)
        )
        all_keys.update(row['key'] for row in cursor)
        
        # 从列表获取
        cursor = conn.execute("SELECT DISTINCT key FROM list_store")
        all_keys.update(row['key'] for row in cursor)
        
        # 从哈希获取
        cursor = conn.execute("SELECT DISTINCT key FROM hash_store")
        all_keys.update(row['key'] for row in cursor)
        
        # 过滤
        if pattern == "*":
            return list(all_keys)
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
    
    # ==================== 列表操作 ====================
    
    def _reindex_list(self, key: str, conn: sqlite3.Connection):
        """重新索引列表（保持连续索引）"""
        cursor = conn.execute(
            "SELECT value FROM list_store WHERE key = ? ORDER BY idx",
            (key,)
        )
        values = [row['value'] for row in cursor]
        
        conn.execute("DELETE FROM list_store WHERE key = ?", (key,))
        
        for idx, value in enumerate(values):
            conn.execute(
                "INSERT INTO list_store (key, idx, value) VALUES (?, ?, ?)",
                (key, idx, value)
            )
    
    def lpush(self, key: str, *values: Any) -> int:
        conn = self._get_connection()
        
        # 获取当前最小索引
        cursor = conn.execute(
            "SELECT MIN(idx) as min_idx FROM list_store WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        min_idx = row['min_idx'] if row['min_idx'] is not None else 0
        
        # 插入新值
        for i, value in enumerate(reversed(values)):
            conn.execute(
                "INSERT INTO list_store (key, idx, value) VALUES (?, ?, ?)",
                (key, min_idx - i - 1, self._serialize(value))
            )
        
        # 重新索引
        self._reindex_list(key, conn)
        
        conn.commit()
        return self.llen(key)
    
    def rpush(self, key: str, *values: Any) -> int:
        conn = self._get_connection()
        
        # 获取当前最大索引
        cursor = conn.execute(
            "SELECT MAX(idx) as max_idx FROM list_store WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        max_idx = row['max_idx'] if row['max_idx'] is not None else -1
        
        # 插入新值
        for i, value in enumerate(values):
            conn.execute(
                "INSERT INTO list_store (key, idx, value) VALUES (?, ?, ?)",
                (key, max_idx + i + 1, self._serialize(value))
            )
        
        conn.commit()
        return self.llen(key)
    
    def lpop(self, key: str) -> Optional[Any]:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT idx, value FROM list_store WHERE key = ? ORDER BY idx LIMIT 1",
            (key,)
        )
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        conn.execute(
            "DELETE FROM list_store WHERE key = ? AND idx = ?",
            (key, row['idx'])
        )
        
        self._reindex_list(key, conn)
        conn.commit()
        
        return self._deserialize(row['value'])
    
    def rpop(self, key: str) -> Optional[Any]:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT idx, value FROM list_store WHERE key = ? ORDER BY idx DESC LIMIT 1",
            (key,)
        )
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        conn.execute(
            "DELETE FROM list_store WHERE key = ? AND idx = ?",
            (key, row['idx'])
        )
        conn.commit()
        
        return self._deserialize(row['value'])
    
    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        conn = self._get_connection()
        
        # 获取列表长度
        length = self.llen(key)
        if length == 0:
            return []
        
        # 处理负索引
        if start < 0:
            start = max(0, length + start)
        if end < 0:
            end = length + end
        
        cursor = conn.execute(
            """SELECT value FROM list_store 
               WHERE key = ? ORDER BY idx
               LIMIT ? OFFSET ?""",
            (key, end - start + 1, start)
        )
        
        return [self._deserialize(row['value']) for row in cursor]
    
    def llen(self, key: str) -> int:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) as cnt FROM list_store WHERE key = ?",
            (key,)
        )
        return cursor.fetchone()['cnt']
    
    def lindex(self, key: str, index: int) -> Optional[Any]:
        conn = self._get_connection()
        
        # 处理负索引
        if index < 0:
            length = self.llen(key)
            index = length + index
        
        cursor = conn.execute(
            """SELECT value FROM list_store 
               WHERE key = ? ORDER BY idx
               LIMIT 1 OFFSET ?""",
            (key, index)
        )
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        return self._deserialize(row['value'])
    
    def lset(self, key: str, index: int, value: Any) -> bool:
        conn = self._get_connection()
        
        # 处理负索引
        if index < 0:
            length = self.llen(key)
            index = length + index
        
        # 获取实际的idx
        cursor = conn.execute(
            """SELECT idx FROM list_store 
               WHERE key = ? ORDER BY idx
               LIMIT 1 OFFSET ?""",
            (key, index)
        )
        row = cursor.fetchone()
        
        if row is None:
            return False
        
        conn.execute(
            "UPDATE list_store SET value = ? WHERE key = ? AND idx = ?",
            (self._serialize(value), key, row['idx'])
        )
        conn.commit()
        return True
    
    def lrem(self, key: str, count: int, value: Any) -> int:
        conn = self._get_connection()
        serialized = self._serialize(value)
        
        if count == 0:
            # 删除所有匹配的
            cursor = conn.execute(
                "DELETE FROM list_store WHERE key = ? AND value = ?",
                (key, serialized)
            )
            removed = cursor.rowcount
        elif count > 0:
            # 从头开始删除
            cursor = conn.execute(
                """SELECT idx FROM list_store 
                   WHERE key = ? AND value = ? ORDER BY idx LIMIT ?""",
                (key, serialized, count)
            )
            indices = [row['idx'] for row in cursor]
            removed = len(indices)
            
            for idx in indices:
                conn.execute(
                    "DELETE FROM list_store WHERE key = ? AND idx = ?",
                    (key, idx)
                )
        else:
            # 从尾开始删除
            cursor = conn.execute(
                """SELECT idx FROM list_store 
                   WHERE key = ? AND value = ? ORDER BY idx DESC LIMIT ?""",
                (key, serialized, -count)
            )
            indices = [row['idx'] for row in cursor]
            removed = len(indices)
            
            for idx in indices:
                conn.execute(
                    "DELETE FROM list_store WHERE key = ? AND idx = ?",
                    (key, idx)
                )
        
        if removed > 0:
            self._reindex_list(key, conn)
        
        conn.commit()
        return removed
    
    # ==================== 哈希操作 ====================
    
    def hget(self, key: str, field: str, default: Any = None) -> Any:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT value FROM hash_store WHERE key = ? AND field = ?",
            (key, field)
        )
        row = cursor.fetchone()
        
        if row is None:
            return default
        
        return self._deserialize(row['value'])
    
    def hset(self, key: str, field: str, value: Any) -> bool:
        conn = self._get_connection()
        now = time.time()
        
        conn.execute(
            """INSERT OR REPLACE INTO hash_store (key, field, value, updated_at)
               VALUES (?, ?, ?, ?)""",
            (key, field, self._serialize(value), now)
        )
        conn.commit()
        return True
    
    def hdel(self, key: str, *fields: str) -> int:
        conn = self._get_connection()
        
        total = 0
        for field in fields:
            cursor = conn.execute(
                "DELETE FROM hash_store WHERE key = ? AND field = ?",
                (key, field)
            )
            total += cursor.rowcount
        
        conn.commit()
        return total
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT field, value FROM hash_store WHERE key = ?",
            (key,)
        )
        
        return {row['field']: self._deserialize(row['value']) for row in cursor}
    
    def hkeys(self, key: str) -> List[str]:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT field FROM hash_store WHERE key = ?",
            (key,)
        )
        
        return [row['field'] for row in cursor]
    
    def hexists(self, key: str, field: str) -> bool:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT 1 FROM hash_store WHERE key = ? AND field = ?",
            (key, field)
        )
        return cursor.fetchone() is not None
    
    # ==================== 过期管理 ====================
    
    def expire(self, key: str, seconds: int) -> bool:
        conn = self._get_connection()
        
        # 只对键值存储设置过期
        cursor = conn.execute(
            "UPDATE kv_store SET expires_at = ? WHERE key = ?",
            (time.time() + seconds, key)
        )
        conn.commit()
        return cursor.rowcount > 0
    
    def ttl(self, key: str) -> int:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT expires_at FROM kv_store WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        
        if row is None:
            return -2
        
        if row['expires_at'] is None:
            return -1
        
        remaining = int(row['expires_at'] - time.time())
        return max(0, remaining)
    
    def persist(self, key: str) -> bool:
        conn = self._get_connection()
        
        cursor = conn.execute(
            "UPDATE kv_store SET expires_at = NULL WHERE key = ? AND expires_at IS NOT NULL",
            (key,)
        )
        conn.commit()
        return cursor.rowcount > 0
    
    # ==================== 事务支持 ====================
    
    def _begin_transaction(self):
        conn = self._get_connection()
        conn.execute("BEGIN IMMEDIATE")
    
    def _commit_transaction(self):
        conn = self._get_connection()
        conn.commit()
    
    def _rollback_transaction(self):
        conn = self._get_connection()
        conn.rollback()
    
    # ==================== 持久化 ====================
    
    def save(self) -> bool:
        """SQLite自动持久化，这里只做提交"""
        conn = self._get_connection()
        conn.commit()
        return True
    
    def load(self) -> bool:
        """SQLite自动加载"""
        return True
    
    # ==================== 工具方法 ====================
    
    def clear(self) -> bool:
        conn = self._get_connection()
        conn.execute("DELETE FROM kv_store")
        conn.execute("DELETE FROM list_store")
        conn.execute("DELETE FROM hash_store")
        conn.commit()
        return True
    
    def size(self) -> int:
        conn = self._get_connection()
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM kv_store")
        count1 = cursor.fetchone()['cnt']
        
        cursor = conn.execute("SELECT COUNT(DISTINCT key) as cnt FROM list_store")
        count2 = cursor.fetchone()['cnt']
        
        cursor = conn.execute("SELECT COUNT(DISTINCT key) as cnt FROM hash_store")
        count3 = cursor.fetchone()['cnt']
        
        return count1 + count2 + count3
    
    def vacuum(self):
        """压缩数据库文件"""
        conn = self._get_connection()
        conn.execute("VACUUM")
    
    def close(self):
        """关闭连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    def info(self) -> Dict[str, Any]:
        """获取存储信息"""
        info = super().info()
        
        conn = self._get_connection()
        
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM kv_store")
        info["kv_count"] = cursor.fetchone()['cnt']
        
        cursor = conn.execute("SELECT COUNT(DISTINCT key) as cnt FROM list_store")
        info["list_count"] = cursor.fetchone()['cnt']
        
        cursor = conn.execute("SELECT COUNT(DISTINCT key) as cnt FROM hash_store")
        info["hash_count"] = cursor.fetchone()['cnt']
        
        if self.config.path:
            path = Path(self.config.path)
            if path.exists():
                info["file_size"] = path.stat().st_size
                info["file_path"] = str(path)
        
        return info
    
    def __repr__(self) -> str:
        return f"SQLiteStorage(path={self.config.path}, size={self.size()})"
