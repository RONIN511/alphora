"""
DatabaseInspector - 数据库结构探查工具

为 AI Agent 提供数据库结构探查能力，支持：
- 数据库全局概览（表列表、行数、外键关系）
- 表结构详情（列定义、类型、主键、外键、索引、数据采样）
- 数据预览（分页浏览）
- 外键关系图
- 建表 DDL
- 表名/列名模糊搜索

设计要点：
- connection_string 作为方法入参，适配对话中动态获取连接信息的场景
- 内部通过 ConnectionManager 缓存引擎，避免重复创建
- 所有方法返回格式化字符串，Agent 可直接阅读
"""

from typing import Optional, List, Tuple

from .connection import ConnectionManager, DBType


class DatabaseInspector:
    """
    数据库结构探查工具

    用于了解数据库"长什么样"：有哪些表、每张表什么结构、表之间什么关系。
    所有方法均返回格式化字符串，适合 Agent 直接理解。

    使用示例：
        inspector = DatabaseInspector()

        # 数据库概览
        result = await inspector.inspect(
            connection_string="sqlite:///data.db"
        )

        # 表结构
        result = await inspector.inspect(
            connection_string="mysql+pymysql://user:pass@host/db",
            table_name="orders"
        )

        # 数据预览（分页）
        result = await inspector.inspect(
            connection_string="sqlite:///data.db",
            table_name="orders",
            purpose="sample",
            limit=20,
            offset=100
        )
    """

    def __init__(self, sandbox=None):
        """
        Args:
            sandbox: 沙箱实例（用于路径转换），可选
        """
        self._conn_mgr = ConnectionManager(sandbox=sandbox)

    async def inspect(
            self,
            connection_string: Optional[str] = None,
            db_path: Optional[str] = None,
            table_name: Optional[str] = None,
            purpose: str = "auto",
            keyword: Optional[str] = None,
            sample_rows: int = 5,
            limit: int = 50,
            offset: int = 0,
    ) -> str:
        """
        探查数据库结构。

        这是 Agent 了解数据库的唯一入口，根据参数自动选择探查模式：
        - 不传 table_name → 数据库全局概览
        - 传了 table_name → 该表的详细结构
        - purpose="sample" → 数据预览（支持分页）
        - keyword → 全局搜索表名/列名

        【连接方式】
        - connection_string: SQLAlchemy 连接字符串（推荐，支持所有数据库）
            示例: "sqlite:///data.db"
                  "mysql+pymysql://user:password@host:3306/dbname"
                  "postgresql+psycopg2://user:password@host:5432/dbname"
        - db_path: SQLite 文件路径（便捷方式）

        Args:
            connection_string (str): 数据库连接字符串。
            db_path (str): SQLite 数据库文件路径（便捷方式，与 connection_string 二选一）。

            table_name (str): 目标表名。不传则返回数据库概览。
                支持模糊匹配：输入 "user" 可匹配到 "users" 或 "user_profile"。

            purpose (str): 探查目的，可选值：
                - "auto"：自动推断（默认）
                    - 无 table_name → overview
                    - 有 table_name → describe
                    - 有 keyword → search
                - "overview"：数据库全局概览（所有表 + 行数 + 关系）
                - "describe"：表详细结构（列定义 + 索引 + 采样数据）
                - "sample"：数据预览（支持 limit/offset 分页）
                - "relationships"：外键关系
                - "ddl"：建表 SQL
                - "search"：搜索表名或列名
                - "stats"：表统计信息（行数、空值比例、唯一值数等）

            keyword (str): 搜索关键词。搜索表名和列名中包含该词的对象。
                提供此参数会自动切换为 search 模式。

            sample_rows (int): describe 模式下的采样行数，默认 5。
            limit (int): sample 模式的返回行数，默认 50。
            offset (int): sample 模式的起始偏移，默认 0。

        Returns:
            str: 格式化的结构描述字符串

        Examples:
            # 数据库概览
            >>> await inspector.inspect(connection_string="sqlite:///data.db")

            # 表结构详情
            >>> await inspector.inspect(connection_string="sqlite:///data.db", table_name="users")

            # 数据预览（分页）
            >>> await inspector.inspect(
            ...     connection_string="sqlite:///data.db",
            ...     table_name="orders", purpose="sample", limit=20, offset=100
            ... )

            # 搜索包含 "user" 的表和列
            >>> await inspector.inspect(connection_string="sqlite:///data.db", keyword="user")

            # 建表 SQL
            >>> await inspector.inspect(
            ...     connection_string="sqlite:///data.db",
            ...     table_name="orders", purpose="ddl"
            ... )

            # 表统计信息
            >>> await inspector.inspect(
            ...     connection_string="sqlite:///data.db",
            ...     table_name="orders", purpose="stats"
            ... )
        """
        # 获取引擎
        try:
            engine, db_type = self._conn_mgr.get_engine(connection_string, db_path)
        except (ValueError, FileNotFoundError, ImportError) as e:
            return f"❌ {str(e)}"

        # 智能推断 purpose
        if keyword and purpose == "auto":
            purpose = "search"
        elif purpose == "auto":
            purpose = "describe" if table_name else "overview"

        # 获取 inspector
        try:
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(engine)
        except Exception as e:
            return f"❌ 无法连接数据库: {e}"

        # 分发到对应处理方法
        dispatch = {
            "overview": lambda: self._overview(engine, db_type, inspector),
            "describe": lambda: self._describe(engine, inspector, table_name, sample_rows),
            "sample": lambda: self._sample(engine, inspector, table_name, limit, offset),
            "relationships": lambda: self._relationships(inspector, table_name),
            "ddl": lambda: self._ddl(engine, db_type, inspector, table_name),
            "search": lambda: self._search(inspector, keyword),
            "stats": lambda: self._stats(engine, inspector, table_name),
        }

        handler = dispatch.get(purpose)
        if not handler:
            return f"❌ 未知的 purpose: '{purpose}'。可选: {', '.join(dispatch.keys())}"

        # 参数校验
        if purpose in ("describe", "sample", "ddl", "stats") and not table_name:
            return f"❌ {purpose} 模式需要指定 table_name"
        if purpose == "search" and not keyword:
            return "❌ search 模式需要指定 keyword"

        try:
            return handler()
        except Exception as e:
            return f"❌ 探查出错: {str(e)}"

    # ----------------------------------------------------------------
    #  内部实现
    # ----------------------------------------------------------------

    @staticmethod
    def _resolve_table(inspector, table_name: str) -> Tuple[Optional[str], Optional[str]]:
        """解析表名（支持模糊匹配），返回 (实际表名, 错误信息)"""
        all_tables = inspector.get_table_names()

        if table_name in all_tables:
            return table_name, None

        # 模糊匹配
        matches = [t for t in all_tables if table_name.lower() in t.lower()]
        if matches:
            if len(matches) == 1:
                return matches[0], None
            return None, f"❌ 表 '{table_name}' 不存在。相似的表: {', '.join(matches[:10])}"

        return None, f"❌ 表 '{table_name}' 不存在。\n可用的表: {', '.join(all_tables[:20])}"

    def _overview(self, engine, db_type, inspector) -> str:
        """数据库全局概览"""
        from sqlalchemy import text

        table_names = inspector.get_table_names()
        lines = [
            f"🗄️ 数据库概览 ({db_type.value})",
            f"📊 表数量: {len(table_names)}",
            "",
            "【数据表】",
        ]

        with engine.connect() as conn:
            for name in table_names:
                try:
                    row_count = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
                except Exception:
                    row_count = "?"
                columns = inspector.get_columns(name)
                pk = inspector.get_pk_constraint(name)
                pk_cols = pk.get("constrained_columns", []) if pk else []
                pk_str = f"  PK: {', '.join(pk_cols)}" if pk_cols else ""
                lines.append(f"  • {name} — {row_count} 行 × {len(columns)} 列{pk_str}")

        # 视图
        try:
            views = inspector.get_view_names()
            if views:
                lines.append("")
                lines.append(f"【视图】({len(views)} 个)")
                for v in views:
                    lines.append(f"  • {v}")
        except Exception:
            pass

        # 外键关系摘要
        rels = []
        for name in table_names:
            try:
                for fk in inspector.get_foreign_keys(name):
                    ref = fk.get("referred_table", "?")
                    src = ", ".join(fk.get("constrained_columns", []))
                    dst = ", ".join(fk.get("referred_columns", []))
                    rels.append(f"  {name}.{src} → {ref}.{dst}")
            except Exception:
                pass

        if rels:
            lines.append("")
            lines.append("【外键关系】")
            lines.extend(rels[:30])

        return "\n".join(lines)

    def _describe(self, engine, inspector, table_name: str, sample_rows: int) -> str:
        """表详细结构"""
        from sqlalchemy import text

        resolved, error = self._resolve_table(inspector, table_name)
        if error:
            return error
        table_name = resolved

        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        pk_cols = set(pk.get("constrained_columns", [])) if pk else set()
        fks = inspector.get_foreign_keys(table_name)
        indexes = inspector.get_indexes(table_name)

        fk_map = {}
        for fk in fks:
            for col, ref_col in zip(
                    fk.get("constrained_columns", []),
                    fk.get("referred_columns", [])
            ):
                fk_map[col] = f"→ {fk.get('referred_table', '?')}.{ref_col}"

        with engine.connect() as conn:
            try:
                row_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            except Exception:
                row_count = "?"

        lines = [
            f"📋 表: {table_name}",
            f"📊 {row_count} 行 × {len(columns)} 列",
            "",
            "【列定义】",
        ]

        for col in columns:
            name = col["name"]
            col_type = str(col.get("type", "UNKNOWN"))
            flags = []
            if name in pk_cols:
                flags.append("PK")
            if not col.get("nullable", True):
                flags.append("NOT NULL")
            if col.get("default") is not None:
                flags.append(f"DEFAULT={col['default']}")
            if col.get("autoincrement"):
                flags.append("AUTO_INC")
            if name in fk_map:
                flags.append(f"FK {fk_map[name]}")
            flags_str = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(f"  • {name}: {col_type}{flags_str}")

        if indexes:
            lines.append("")
            lines.append("【索引】")
            for idx in indexes:
                u = "UNIQUE " if idx.get("unique") else ""
                cols = ", ".join(idx.get("column_names", []))
                lines.append(f"  • {u}{idx.get('name', '?')}: ({cols})")

        # 数据采样
        if row_count and row_count != "?" and row_count > 0 and sample_rows > 0:
            lines.append("")
            lines.append(f"【数据采样（前 {min(sample_rows, row_count)} 行）】")
            with engine.connect() as conn:
                try:
                    result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT {sample_rows}'))
                    col_names = list(result.keys())
                    rows = result.fetchall()
                    if rows:
                        from .formatter import format_rows_as_table
                        lines.append(format_rows_as_table(col_names, rows))
                except Exception as e:
                    lines.append(f"  (采样失败: {e})")

        return "\n".join(lines)

    def _sample(self, engine, inspector, table_name: str, limit: int, offset: int) -> str:
        """数据预览（分页）"""
        from sqlalchemy import text
        from .formatter import format_rows_as_table

        resolved, error = self._resolve_table(inspector, table_name)
        if error:
            return error
        table_name = resolved

        with engine.connect() as conn:
            try:
                total = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                result = conn.execute(
                    text(f'SELECT * FROM "{table_name}" LIMIT {min(limit, 500)} OFFSET {offset}')
                )
                col_names = list(result.keys())
                rows = result.fetchall()
            except Exception as e:
                return f"❌ 查询失败: {e}"

        lines = [
            f"📋 表: {table_name}",
            f"📊 总行数: {total} | 显示: 第 {offset + 1}-{offset + len(rows)} 行",
            "",
        ]

        if not rows:
            lines.append("(无数据)")
            return "\n".join(lines)

        lines.append(format_rows_as_table(col_names, rows))

        if offset + len(rows) < total:
            lines.append("")
            lines.append(
                f"💡 下一页: inspect(table_name='{table_name}', "
                f"purpose='sample', offset={offset + limit})"
            )

        return "\n".join(lines)

    def _relationships(self, inspector, table_name: Optional[str]) -> str:
        """外键关系"""
        tables = [table_name] if table_name else inspector.get_table_names()
        lines = ["🔗 外键关系", ""]
        found = False

        for tbl in tables:
            resolved, _ = self._resolve_table(inspector, tbl)
            if not resolved:
                continue
            fks = inspector.get_foreign_keys(resolved)
            if fks:
                found = True
                lines.append(f"📋 {resolved}:")
                for fk in fks:
                    src = ", ".join(fk.get("constrained_columns", []))
                    ref = fk.get("referred_table", "?")
                    dst = ", ".join(fk.get("referred_columns", []))
                    name = fk.get("name", "")
                    name_str = f" ({name})" if name else ""
                    lines.append(f"  {src} → {ref}.{dst}{name_str}")
                lines.append("")

        if not found:
            lines.append("(未发现外键关系)")

        return "\n".join(lines)

    def _ddl(self, engine, db_type, inspector, table_name: str) -> str:
        """建表 SQL"""
        from sqlalchemy import text

        resolved, error = self._resolve_table(inspector, table_name)
        if error:
            return error
        table_name = resolved

        # SQLite 直接获取原始 DDL
        if db_type == DBType.SQLITE:
            with engine.connect() as conn:
                try:
                    row = conn.execute(
                        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"),
                        {"n": table_name}
                    ).fetchone()
                    if row:
                        return f"📋 {table_name} 建表语句:\n\n{row[0]}"
                except Exception as e:
                    return f"❌ 获取失败: {e}"

        # MySQL 直接获取 SHOW CREATE TABLE
        if db_type == DBType.MYSQL:
            with engine.connect() as conn:
                try:
                    row = conn.execute(text(f"SHOW CREATE TABLE `{table_name}`")).fetchone()
                    if row:
                        return f"📋 {table_name} 建表语句:\n\n{row[1]}"
                except Exception:
                    pass  # 降级到推断模式

        # 通用：从 inspector 推断 DDL
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        pk_cols = pk.get("constrained_columns", []) if pk else []
        fks = inspector.get_foreign_keys(table_name)

        parts = []
        for col in columns:
            col_def = f'  "{col["name"]}" {col.get("type", "TEXT")}'
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("default") is not None:
                col_def += f" DEFAULT {col['default']}"
            parts.append(col_def)

        if pk_cols:
            parts.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")
        for fk in fks:
            src = ", ".join(fk.get("constrained_columns", []))
            ref = fk.get("referred_table", "?")
            dst = ", ".join(fk.get("referred_columns", []))
            parts.append(f"  FOREIGN KEY ({src}) REFERENCES {ref}({dst})")

        sql = f'CREATE TABLE "{table_name}" (\n' + ",\n".join(parts) + "\n);"
        return f"📋 {table_name} 结构（推断 DDL）:\n\n{sql}"

    def _search(self, inspector, keyword: str) -> str:
        """搜索表名和列名"""
        kw = keyword.lower()
        all_tables = inspector.get_table_names()

        matched_tables = []
        matched_columns = []

        for tbl in all_tables:
            if kw in tbl.lower():
                matched_tables.append(tbl)
            for col in inspector.get_columns(tbl):
                if kw in col["name"].lower():
                    matched_columns.append(f"{tbl}.{col['name']} ({col.get('type', '?')})")

        lines = [
            f"🔍 搜索: '{keyword}'",
            f"📊 匹配: {len(matched_tables)} 个表, {len(matched_columns)} 个列",
            "",
        ]

        if matched_tables:
            lines.append("【匹配的表】")
            for t in matched_tables:
                lines.append(f"  • {t}")
            lines.append("")

        if matched_columns:
            lines.append("【匹配的列】")
            for c in matched_columns[:50]:
                lines.append(f"  • {c}")
            if len(matched_columns) > 50:
                lines.append(f"  ... 还有 {len(matched_columns) - 50} 个")

        if not matched_tables and not matched_columns:
            lines.append(f"未找到与 '{keyword}' 相关的表或列")

        return "\n".join(lines)

    def _stats(self, engine, inspector, table_name: str) -> str:
        """表统计信息（行数、空值比例、唯一值数等）"""
        from sqlalchemy import text

        resolved, error = self._resolve_table(inspector, table_name)
        if error:
            return error
        table_name = resolved

        columns = inspector.get_columns(table_name)

        with engine.connect() as conn:
            try:
                total = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            except Exception as e:
                return f"❌ 获取行数失败: {e}"

        lines = [
            f"📊 表统计: {table_name}",
            f"📊 总行数: {total}",
            "",
            "【列统计】",
            f"  {'列名':<25} {'类型':<15} {'空值数':<10} {'空值比例':<10} {'唯一值数':<10}",
            f"  {'-' * 25} {'-' * 15} {'-' * 10} {'-' * 10} {'-' * 10}",
        ]

        if total == 0:
            lines.append("  (表无数据)")
            return "\n".join(lines)

        with engine.connect() as conn:
            for col in columns:
                col_name = col["name"]
                col_type = str(col.get("type", "?"))[:15]
                try:
                    null_count = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col_name}" IS NULL')
                    ).scalar()
                    distinct_count = conn.execute(
                        text(f'SELECT COUNT(DISTINCT "{col_name}") FROM "{table_name}"')
                    ).scalar()
                    null_pct = f"{null_count / total * 100:.1f}%" if total > 0 else "0%"
                    lines.append(
                        f"  {col_name:<25} {col_type:<15} {null_count:<10} {null_pct:<10} {distinct_count:<10}"
                    )
                except Exception:
                    lines.append(f"  {col_name:<25} {col_type:<15} {'?':<10} {'?':<10} {'?':<10}")

        return "\n".join(lines)

    def close(self):
        """关闭所有缓存的数据库连接"""
        self._conn_mgr.close_all()
