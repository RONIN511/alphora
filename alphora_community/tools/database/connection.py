"""
ConnectionManager - 数据库连接管理

负责 SQLAlchemy Engine 的创建、缓存与生命周期管理。
支持通过 connection_string 或 db_path 连接 SQLite / MySQL / PostgreSQL。

设计要点：
- 同一连接字符串复用同一 Engine（避免重复创建开销）
- 支持沙箱路径自动转换
- 提供统一的数据库类型识别
"""

import os
from enum import Enum
from typing import Optional


class DBType(Enum):
    """数据库类型"""
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    UNKNOWN = "unknown"


class ConnectionManager:
    """
    数据库连接管理器

    为 DatabaseInspector / DatabaseQuery 提供底层连接管理。
    同一个 connection_string 只创建一次 Engine 并缓存复用。

    使用示例：
        manager = ConnectionManager()

        # 通过连接字符串获取引擎
        engine, db_type = manager.get_engine("sqlite:///data.db")

        # 通过 SQLite 文件路径获取引擎
        engine, db_type = manager.get_engine(db_path="/data/sales.db")

        # 关闭所有连接
        manager.close_all()
    """

    def __init__(self, sandbox=None):
        """
        Args:
            sandbox: 沙箱实例（用于路径转换），可选
        """
        self._sandbox = sandbox
        self._engines: dict = {}  # connection_string -> (engine, db_type)

    def get_engine(
            self,
            connection_string: Optional[str] = None,
            db_path: Optional[str] = None,
    ):
        """
        获取或创建数据库引擎

        Args:
            connection_string: SQLAlchemy 连接字符串。
                示例: "sqlite:///data.db", "mysql+pymysql://user:pass@host/db",
                       "postgresql+psycopg2://user:pass@host/db"
            db_path: SQLite 数据库文件路径（便捷方式）。
                会自动转换为 "sqlite:///path" 连接字符串。

        Returns:
            (engine, db_type) 元组

        Raises:
            ValueError: 未提供任何连接信息
            FileNotFoundError: SQLite 文件不存在
            ImportError: 缺少 sqlalchemy
        """
        conn_str = self._resolve_connection_string(connection_string, db_path)

        if conn_str in self._engines:
            return self._engines[conn_str]

        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise ImportError(
                "需要安装 sqlalchemy: pip install sqlalchemy\n"
                "MySQL 还需: pip install pymysql\n"
                "PostgreSQL 还需: pip install psycopg2-binary"
            )

        engine = create_engine(conn_str, echo=False)
        db_type = self._detect_db_type(engine)
        self._engines[conn_str] = (engine, db_type)
        return engine, db_type

    def _resolve_connection_string(
            self,
            connection_string: Optional[str],
            db_path: Optional[str],
    ) -> str:
        """将参数统一解析为 connection_string"""
        if db_path:
            if self._sandbox:
                db_path = self._sandbox.to_host_path(db_path)
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"数据库文件不存在: {db_path}")
            return f"sqlite:///{db_path}"

        if connection_string:
            return connection_string

        raise ValueError(
            "请提供数据库连接信息。\n"
            "方式一: connection_string=\"sqlite:///path/to/db.sqlite\"\n"
            "方式二: connection_string=\"mysql+pymysql://user:pass@host/db\"\n"
            "方式三: db_path=\"/path/to/file.db\"（仅限 SQLite）"
        )

    @staticmethod
    def _detect_db_type(engine) -> DBType:
        """检测数据库类型"""
        dialect = engine.dialect.name.lower()
        if "sqlite" in dialect:
            return DBType.SQLITE
        elif "mysql" in dialect:
            return DBType.MYSQL
        elif "postgres" in dialect:
            return DBType.POSTGRESQL
        return DBType.UNKNOWN

    def close(self, connection_string: str):
        """关闭指定连接"""
        if connection_string in self._engines:
            engine, _ = self._engines.pop(connection_string)
            engine.dispose()

    def close_all(self):
        """关闭所有缓存的连接"""
        for engine, _ in self._engines.values():
            engine.dispose()
        self._engines.clear()
