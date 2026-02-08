"""
格式化工具模块

提供查询结果的多种输出格式：
- table:    对齐的文本表格（默认，Agent 最易阅读）
- csv:      CSV 格式（适合后续处理）
- json:     JSON 格式（结构化输出）
- markdown: Markdown 表格（适合展示）
"""

import json
from typing import List, Any, Optional


# 列值最大显示宽度
MAX_CELL_WIDTH = 50
# 列值截断阈值
TRUNCATE_THRESHOLD = 60


def truncate_value(value: Any, max_len: int = TRUNCATE_THRESHOLD) -> str:
    """将值转为字符串并在过长时截断"""
    if value is None:
        return "NULL"
    s = str(value)
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def format_rows_as_table(col_names: List[str], rows: List) -> str:
    """
    将列名和行数据格式化为对齐的文本表格

    Args:
        col_names: 列名列表
        rows: 行数据列表（每行为元组或列表）

    Returns:
        格式化后的文本表格字符串
    """
    str_rows = []
    widths = [len(c) for c in col_names]

    for row in rows:
        sr = []
        for i, v in enumerate(row):
            s = truncate_value(v)
            if i < len(widths):
                widths[i] = max(widths[i], len(s))
            sr.append(s)
        str_rows.append(sr)

    widths = [min(w, MAX_CELL_WIDTH) for w in widths]

    lines = [
        " | ".join(c.ljust(widths[i])[: widths[i]] for i, c in enumerate(col_names)),
        "-+-".join("-" * w for w in widths),
    ]
    for sr in str_rows:
        lines.append(
            " | ".join(
                v.ljust(widths[i])[: widths[i]] if i < len(widths) else v
                for i, v in enumerate(sr)
            )
        )
    return "\n".join(lines)


def format_as_csv(col_names: List[str], rows: List) -> str:
    """格式化为 CSV"""
    def esc(v):
        s = truncate_value(v)
        return f'"{s.replace(chr(34), chr(34) * 2)}"' if "," in s or '"' in s or "\n" in s else s

    lines = [",".join(col_names)]
    for row in rows:
        lines.append(",".join(esc(v) for v in row))
    return "\n".join(lines)


def format_as_json(col_names: List[str], rows: List) -> str:
    """格式化为 JSON"""
    data = []
    for row in rows:
        record = {}
        for i, v in enumerate(row):
            col = col_names[i] if i < len(col_names) else f"col_{i}"
            record[col] = None if v is None else v
        data.append(record)
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def format_as_markdown(col_names: List[str], rows: List) -> str:
    """格式化为 Markdown 表格"""
    lines = [
        "| " + " | ".join(col_names) + " |",
        "| " + " | ".join("---" for _ in col_names) + " |",
    ]
    for row in rows:
        cells = [truncate_value(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_query_result(
        sql: str,
        col_names: List[str],
        rows: List,
        elapsed: float,
        truncated: bool,
        max_rows: int,
        output_format: str = "table",
) -> str:
    """
    格式化 SELECT 查询的完整结果（含元信息头）

    Args:
        sql: 执行的 SQL 语句
        col_names: 列名列表
        rows: 行数据列表
        elapsed: 执行耗时（秒）
        truncated: 结果是否被截断
        max_rows: 最大行数限制
        output_format: 输出格式 (table / csv / json / markdown)

    Returns:
        格式化的完整结果字符串
    """
    header_lines = [
        f"📋 查询: {sql[:150]}{'...' if len(sql) > 150 else ''}",
        f"📊 结果: {len(rows)} 行 × {len(col_names)} 列"
        + (f"（截断，上限 {max_rows}）" if truncated else ""),
        f"⏱️ 耗时: {elapsed:.3f}s",
        "",
    ]

    if not rows:
        header_lines.append("(空结果集)")
        return "\n".join(header_lines)

    formatters = {
        "csv": format_as_csv,
        "json": format_as_json,
        "markdown": format_as_markdown,
        "table": format_rows_as_table,
    }
    fmt_func = formatters.get(output_format, format_rows_as_table)
    body = fmt_func(col_names, rows)

    return "\n".join(header_lines) + body


def format_write_result(sql: str, row_count: int, elapsed: float) -> str:
    """格式化写操作的执行结果"""
    return (
        f"✅ 执行成功\n"
        f"📋 语句: {sql[:200]}\n"
        f"📊 影响行数: {row_count}\n"
        f"⏱️ 耗时: {elapsed:.3f}s"
    )


def format_error(sql: str, error: Exception, elapsed: float) -> str:
    """格式化执行错误"""
    return (
        f"❌ 执行失败\n"
        f"📋 语句: {sql[:200]}\n"
        f"❗ 错误: {str(error)}\n"
        f"⏱️ 耗时: {elapsed:.3f}s"
    )
