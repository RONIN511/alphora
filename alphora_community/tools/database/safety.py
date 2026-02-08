"""
SQL 安全校验模块

提供 SQL 语句的安全性校验，包括：
- 危险操作拦截（DROP DATABASE / TRUNCATE 等始终拦截）
- 只读模式下拦截写操作
- 多语句拦截（防止注入）
- SQL 类型识别
"""

import re
from typing import Tuple


# 危险操作关键词 —— 无论只读还是读写模式，始终拦截
DANGEROUS_KEYWORDS = {
    "DROP DATABASE", "DROP SCHEMA",
    "TRUNCATE", "ALTER SYSTEM",
    "SHUTDOWN", "GRANT", "REVOKE",
    "CREATE USER", "DROP USER",
}

# 写操作关键词 —— 只读模式下拦截
WRITE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP",
    "ALTER", "CREATE", "REPLACE", "MERGE",
}


def validate_sql(sql: str, allow_write: bool = False) -> Tuple[bool, str]:
    """
    校验 SQL 语句的安全性

    Args:
        sql: SQL 语句
        allow_write: 是否允许写操作

    Returns:
        (is_valid, error_message) — 通过则 error_message 为空字符串
    """
    sql_stripped = sql.strip()
    if not sql_stripped:
        return False, "❌ SQL 语句不能为空"

    sql_upper = sql_stripped.upper()

    # 1. 危险操作检测
    for kw in DANGEROUS_KEYWORDS:
        if kw in sql_upper:
            return False, f"❌ 检测到危险操作: {kw}，已拦截"

    # 2. 只读模式下拦截写操作
    if not allow_write:
        first_word = sql_upper.split()[0] if sql_upper.split() else ""
        if first_word in WRITE_KEYWORDS:
            return False, (
                f"❌ 当前为只读模式，不允许 {first_word} 操作。\n"
                f"如需写操作，请设置 allow_write=True。"
            )

    # 3. 多语句拦截
    parts = sql_stripped.rstrip(";").split(";")
    non_empty = [p for p in parts if p.strip()]
    if len(non_empty) > 1:
        return False, "❌ 不支持一次执行多条 SQL 语句，请逐条提交"

    return True, ""


def is_select_query(sql: str) -> bool:
    """判断 SQL 是否为 SELECT 类查询（SELECT / WITH / EXPLAIN / SHOW / DESCRIBE）"""
    first_word = sql.strip().upper().split()[0] if sql.strip() else ""
    return first_word in {"SELECT", "WITH", "EXPLAIN", "SHOW", "DESCRIBE", "DESC", "PRAGMA"}
