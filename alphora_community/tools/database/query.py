"""
DatabaseQuery - SQL 查询执行工具

为 AI Agent 提供安全的 SQL 执行能力，支持：
- 参数化查询（防注入）
- 只读/读写模式
- 多种输出格式（table / csv / json / markdown）
- 快捷聚合方法（count / distinct / aggregate）
- 危险操作拦截

设计要点：
- connection_string 作为方法入参，适配对话中动态获取连接信息的场景
- 默认只读，写操作需要显式开启
- 所有方法返回格式化字符串，Agent 可直接阅读
"""

import time
from typing import Optional, Dict, Any, List

from .connection import ConnectionManager
from .safety import validate_sql, is_select_query
from .formatter import (
    format_query_result,
    format_write_result,
    format_error,
    format_rows_as_table,
)


class DatabaseQuery:
    """
    SQL 查询执行工具

    安全地执行 SQL 查询，带参数化防注入、结果格式化、只读保护。
    所有方法均返回格式化字符串，适合 Agent 直接理解。

    使用示例：
        query = DatabaseQuery()

        # 执行查询
        result = await query.execute(
            connection_string="sqlite:///data.db",
            sql="SELECT * FROM users WHERE age > :min",
            params={"min": 18}
        )

        # 快捷方法
        result = await query.execute(
            connection_string="sqlite:///data.db",
            sql="count",
            table_name="orders",
            where="status = 'active'"
        )
    """

    def __init__(self, sandbox=None):
        """
        Args:
            sandbox: 沙箱实例（用于路径转换），可选
        """
        self._conn_mgr = ConnectionManager(sandbox=sandbox)

    async def execute(
            self,
            connection_string: Optional[str] = None,
            db_path: Optional[str] = None,
            sql: str = "",
            params: Optional[Dict[str, Any]] = None,
            max_rows: int = 500,
            output_format: str = "table",
            allow_write: bool = False,
            table_name: Optional[str] = None,
            where: Optional[str] = None,
            column: Optional[str] = None,
    ) -> str:
        """
        执行 SQL 查询并返回格式化结果。

        这是 Agent 执行数据库操作的唯一入口。支持两种使用方式：
        1. 直接写 SQL（灵活，适合复杂查询）
        2. 快捷模式（简单，适合常见操作）

        【连接方式】
        - connection_string: SQLAlchemy 连接字符串（推荐，支持所有数据库）
            示例: "sqlite:///data.db"
                  "mysql+pymysql://user:password@host:3306/dbname"
                  "postgresql+psycopg2://user:password@host:5432/dbname"
        - db_path: SQLite 文件路径（便捷方式）

        【快捷模式】
        当 sql 为以下关键字时，自动构建 SQL（需配合 table_name）：
        - "count"：统计行数         → SELECT COUNT(*) FROM table [WHERE ...]
        - "distinct"：唯一值列表    → SELECT DISTINCT column FROM table [WHERE ...]
        - "aggregate"：聚合统计     → SELECT COUNT/MIN/MAX/AVG/SUM FROM table
        - "head"：查看前 N 行       → SELECT * FROM table LIMIT max_rows
        - "tail"：查看最后 N 行     → SELECT * FROM table ORDER BY rowid DESC LIMIT max_rows

        Args:
            connection_string (str): 数据库连接字符串。
            db_path (str): SQLite 文件路径（与 connection_string 二选一）。

            sql (str): SQL 语句或快捷指令。
                SQL 模式: "SELECT * FROM users WHERE age > :min_age"
                快捷模式: "count" / "distinct" / "aggregate" / "head" / "tail"

            params (dict): SQL 参数字典（参数化查询，防注入）。
                示例: {"min_age": 18, "status": "active"}
                在 SQL 中使用 :param_name 引用。

            max_rows (int): 最大返回行数，默认 500。

            output_format (str): 输出格式，可选值：
                - "table"：对齐的文本表格（默认，最易阅读）
                - "csv"：CSV 格式
                - "json"：JSON 格式
                - "markdown"：Markdown 表格

            allow_write (bool): 是否允许写操作，默认 False。
                设为 True 后允许 INSERT / UPDATE / DELETE / CREATE 等。

            table_name (str): 【快捷模式】目标表名。
            where (str): 【快捷模式】WHERE 条件（不含 WHERE 关键字）。
                示例: "status = 'active' AND created_at > '2024-01-01'"
            column (str): 【快捷模式 distinct】目标列名。

        Returns:
            str: 格式化的查询结果字符串

        Examples:
            # 简单查询
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="SELECT * FROM users LIMIT 10"
            ... )

            # 参数化查询（防注入）
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="SELECT * FROM orders WHERE status = :s AND total > :min",
            ...     params={"s": "shipped", "min": 100}
            ... )

            # JSON 输出
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="SELECT * FROM config",
            ...     output_format="json"
            ... )

            # 快捷：计数
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="count",
            ...     table_name="orders",
            ...     where="status = 'active'"
            ... )

            # 快捷：唯一值
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="distinct",
            ...     table_name="orders",
            ...     column="status"
            ... )

            # 写操作
            >>> await query.execute(
            ...     connection_string="sqlite:///data.db",
            ...     sql="UPDATE users SET status = 'inactive' WHERE last_login < '2023-01-01'",
            ...     allow_write=True
            ... )
        """
        # 获取引擎
        try:
            engine, db_type = self._conn_mgr.get_engine(connection_string, db_path)
        except (ValueError, FileNotFoundError, ImportError) as e:
            return f"❌ {str(e)}"

        # 快捷模式处理
        sql_lower = sql.strip().lower()
        if sql_lower in ("count", "distinct", "aggregate", "head", "tail"):
            return self._handle_shortcut(engine, sql_lower, table_name, where, column, max_rows, output_format)

        if not sql.strip():
            return "❌ 请提供 SQL 语句或快捷指令（count / distinct / aggregate / head / tail）"

        # SQL 安全校验
        is_valid, error_msg = validate_sql(sql, allow_write)
        if not is_valid:
            return error_msg

        # 执行查询
        from sqlalchemy import text

        is_select = is_select_query(sql)
        start_time = time.time()

        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                elapsed = time.time() - start_time

                if is_select:
                    col_names = list(result.keys())
                    rows = result.fetchmany(max_rows + 1)
                    truncated = len(rows) > max_rows
                    if truncated:
                        rows = rows[:max_rows]

                    return format_query_result(
                        sql, col_names, rows, elapsed, truncated, max_rows, output_format
                    )
                else:
                    conn.commit()
                    return format_write_result(sql, result.rowcount, elapsed)

        except Exception as e:
            elapsed = time.time() - start_time
            return format_error(sql, e, elapsed)

    # ----------------------------------------------------------------
    #  快捷模式实现
    # ----------------------------------------------------------------

    def _handle_shortcut(
            self, engine, mode: str, table_name: Optional[str],
            where: Optional[str], column: Optional[str],
            max_rows: int, output_format: str,
    ) -> str:
        """处理快捷模式"""
        if not table_name:
            return f"❌ 快捷模式 '{mode}' 需要指定 table_name"

        from sqlalchemy import text, inspect as sa_inspect

        # 验证表是否存在
        try:
            inspector = sa_inspect(engine)
            all_tables = inspector.get_table_names()
            if table_name not in all_tables:
                # 模糊匹配
                matches = [t for t in all_tables if table_name.lower() in t.lower()]
                if len(matches) == 1:
                    table_name = matches[0]
                elif matches:
                    return f"❌ 表 '{table_name}' 不存在。相似的表: {', '.join(matches[:10])}"
                else:
                    return f"❌ 表 '{table_name}' 不存在。可用的表: {', '.join(all_tables[:20])}"
        except Exception:
            pass

        where_clause = f" WHERE {where}" if where else ""

        try:
            with engine.connect() as conn:
                if mode == "count":
                    count = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}"{where_clause}')
                    ).scalar()
                    return f"📊 {table_name} 行数: {count}" + (f"  (条件: {where})" if where else "")

                elif mode == "distinct":
                    if not column:
                        return "❌ distinct 模式需要指定 column 参数"
                    result = conn.execute(
                        text(f'SELECT DISTINCT "{column}" FROM "{table_name}"{where_clause} LIMIT {max_rows}')
                    )
                    values = [str(row[0]) for row in result.fetchall()]
                    return (
                        f"📊 {table_name}.{column} 唯一值（{len(values)} 个）:\n"
                        + ", ".join(values)
                    )

                elif mode == "aggregate":
                    columns = inspector.get_columns(table_name)
                    numeric_cols = []
                    for col in columns:
                        type_str = str(col.get("type", "")).upper()
                        if any(t in type_str for t in ["INT", "FLOAT", "REAL", "NUMERIC", "DECIMAL", "DOUBLE"]):
                            numeric_cols.append(col["name"])

                    if not numeric_cols:
                        return f"📊 表 {table_name} 中未发现数值类型的列"

                    lines = [f"📊 表 {table_name} 聚合统计" + (f"  (条件: {where})" if where else ""), ""]
                    for col_name in numeric_cols[:10]:
                        try:
                            agg_sql = (
                                f'SELECT COUNT("{col_name}") as cnt, '
                                f'MIN("{col_name}") as min_val, '
                                f'MAX("{col_name}") as max_val, '
                                f'AVG("{col_name}") as avg_val, '
                                f'SUM("{col_name}") as sum_val '
                                f'FROM "{table_name}"{where_clause}'
                            )
                            row = conn.execute(text(agg_sql)).fetchone()
                            if row:
                                avg_val = f"{row[3]:.2f}" if row[3] is not None else "NULL"
                                lines.append(
                                    f"  {col_name}: "
                                    f"COUNT={row[0]}, MIN={row[1]}, MAX={row[2]}, "
                                    f"AVG={avg_val}, SUM={row[4]}"
                                )
                        except Exception as e:
                            lines.append(f"  {col_name}: (统计失败: {e})")
                    return "\n".join(lines)

                elif mode == "head":
                    sql = f'SELECT * FROM "{table_name}"{where_clause} LIMIT {max_rows}'
                    result = conn.execute(text(sql))
                    col_names = list(result.keys())
                    rows = result.fetchall()
                    if not rows:
                        return f"📊 {table_name}: (无数据)"
                    header = f"📋 {table_name} 前 {len(rows)} 行:\n\n"
                    return header + format_rows_as_table(col_names, rows)

                elif mode == "tail":
                    # 尝试使用 rowid (SQLite) 或子查询
                    try:
                        sql = (
                            f'SELECT * FROM "{table_name}"{where_clause} '
                            f'ORDER BY rowid DESC LIMIT {max_rows}'
                        )
                        result = conn.execute(text(sql))
                    except Exception:
                        # 回退：获取总行数再 OFFSET
                        total = conn.execute(
                            text(f'SELECT COUNT(*) FROM "{table_name}"{where_clause}')
                        ).scalar()
                        offset = max(0, total - max_rows)
                        sql = f'SELECT * FROM "{table_name}"{where_clause} LIMIT {max_rows} OFFSET {offset}'
                        result = conn.execute(text(sql))

                    col_names = list(result.keys())
                    rows = result.fetchall()
                    if not rows:
                        return f"📊 {table_name}: (无数据)"
                    header = f"📋 {table_name} 最后 {len(rows)} 行:\n\n"
                    return header + format_rows_as_table(col_names, rows)

        except Exception as e:
            return f"❌ 执行失败: {str(e)}"

        return f"❌ 未知的快捷模式: {mode}"

    def close(self):
        """关闭所有缓存的数据库连接"""
        self._conn_mgr.close_all()
