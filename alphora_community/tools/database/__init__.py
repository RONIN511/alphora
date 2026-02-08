"""
Database 工具模块

为 AI Agent 提供数据库交互能力，支持 SQLite / MySQL / PostgreSQL。

包含两个核心工具：
- DatabaseInspector: 探查数据库结构（表、列、关系、统计）
- DatabaseQuery: 执行 SQL 查询（只读/读写、参数化、多种输出格式）

以及底层支撑模块：
- ConnectionManager: 连接管理与缓存
- DBType: 数据库类型枚举

快速开始：
    from alphora_community.tools.database import DatabaseInspector, DatabaseQuery

    inspector = DatabaseInspector()
    query = DatabaseQuery()

    # 了解数据库结构
    print(await inspector.inspect(connection_string="sqlite:///data.db"))

    # 执行查询
    print(await query.execute(
        connection_string="sqlite:///data.db",
        sql="SELECT * FROM users LIMIT 10"
    ))

依赖安装：
    pip install sqlalchemy          # 必需
    pip install pymysql             # MySQL
    pip install psycopg2-binary     # PostgreSQL
"""

from .inspector import DatabaseInspector
from .query import DatabaseQuery
from .connection import ConnectionManager, DBType

__all__ = [
    "DatabaseInspector",
    "DatabaseQuery",
    "ConnectionManager",
    "DBType",
]
