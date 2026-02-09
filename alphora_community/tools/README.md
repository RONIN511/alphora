# Alphora Community Tools

**面向 AI Agent 的常用工具集合（Database / Files / Web）**

`alphora_community.tools` 提供一组“对话友好”的工具实现：**异步优先**、**字符串输出**、**可选沙箱适配**，适合直接挂载到 Agent 的工具列表中使用。

---

## 特性

- **字符串输出**：所有核心工具方法返回 `str`（必要时返回 JSON 字符串），便于 LLM 直接理解
- **异步优先**：核心方法均为 `async`，在 Agent 框架里可直接 `await`
- **沙箱兼容**：支持传入 `Sandbox`，把沙箱内路径自动映射到宿主机路径
- **安全可控**：数据库工具默认只读、危险 SQL 拦截、单语句限制、参数化查询
- **智能推断**：FileViewer / DatabaseInspector 支持根据参数自动推断查看/探查模式

---

## 工具一览

| 模块 | 工具 | 作用 |
|------|------|------|
| Database | `DatabaseInspector` | 探查库/表结构、关系、DDL、采样、统计 |
| Database | `DatabaseQuery` | 安全执行 SQL（只读默认），支持快捷指令 |
| Files | `FileViewer` | 统一预览/搜索 Excel、CSV、Word、PPT、PDF、文本/代码等 |
| Files | `ImageReader` | 多模态图片分析（描述/OCR/问答/结构化提取/表格识别等） |
| Web | `WebBrowser` | 抓取网页/PDF/JSON 并解析为对话友好文本（可选 JS 渲染） |
| Web | `WebSearchTool` | 互联网实时搜索（博查 API） |
| Web | `ArxivSearchTool` | arXiv 论文检索（无需 API Key） |

---

## 安装

### 基础安装

`alphora_community` 随 `alphora` 一起打包发布：

```bash
pip install alphora
```

### 可选依赖

按需安装对应工具的依赖（未安装时工具会给出清晰提示）：

```bash
# Database
pip install sqlalchemy
pip install pymysql              # MySQL
pip install psycopg2-binary      # PostgreSQL

# Files
pip install openpyxl pandas      # Excel / CSV
pip install python-docx          # Word
pip install python-pptx          # PowerPoint
pip install pymupdf pdfplumber   # PDF（任装其一也可）

# Web
pip install httpx beautifulsoup4 html2text lxml
pip install pymupdf              # 抓取 PDF（可选）
pip install playwright && playwright install chromium   # JS 渲染（可选）

# Image
pip install Pillow               # 仅用于尺寸等基础信息（可选）
```

---

## 快速开始

### 快速导入

```python
from alphora_community.tools import (
    # Database
    DatabaseInspector,
    DatabaseQuery,
    # Files
    FileViewer,
    ImageReader,
    # Web
    WebBrowser,
    WebSearchTool,
    ArxivSearchTool,
)
```

### 最小可运行示例

> 说明：这些工具是异步接口，建议在你的 Agent / FastAPI / asyncio 环境中直接使用。

```python
import asyncio

from alphora.models import OpenAILike
from alphora_community.tools import (
    DatabaseInspector, DatabaseQuery,
    FileViewer, ImageReader,
    WebBrowser, WebSearchTool, ArxivSearchTool,
)


async def main():
    # ---------------------------
    # Database
    # ---------------------------
    inspector = DatabaseInspector()
    query = DatabaseQuery()

    print(await inspector.inspect(connection_string="sqlite:///data.db"))
    print(await query.execute(
        connection_string="sqlite:///data.db",
        sql="SELECT * FROM users LIMIT 5",
    ))

    # ---------------------------
    # Files
    # ---------------------------
    viewer = FileViewer()
    print(await viewer.view_file("report.pdf", page_number=1, max_lines=50))

    # ImageReader 需要多模态 LLM（示例用 OpenAI-like 适配器）
    vision_llm = OpenAILike(model_name="qwen-vl-plus", is_multimodal=True)
    reader = ImageReader(llm=vision_llm)
    print(await reader.describe("photo.jpg"))

    # ---------------------------
    # Web
    # ---------------------------
    browser = WebBrowser()
    print(await browser.fetch("https://example.com", extract_links=True))

    arxiv = ArxivSearchTool()
    print(await arxiv.search("large language model agents", max_results=3))

    # WebSearchTool 需要 BOCHA_API_KEY（或构造时传 api_key=...）
    search = WebSearchTool()
    print(await search.search("特斯拉 2024 销量", freshness="oneYear"))


if __name__ == "__main__":
    asyncio.run(main())
```

---

##  Database（数据库工具）

### DatabaseInspector（结构探查）

`inspect()` 是唯一入口，通过参数自动切换模式：

- **不传 `table_name`**：全库概览（表、行数、外键摘要）
- **传 `table_name`**：表结构详情（列/主键/索引/采样）
- **`purpose="sample"`**：分页预览数据
- **传 `keyword`**：搜索表名/列名

```python
inspector = DatabaseInspector()

# 全库概览
print(await inspector.inspect(connection_string="sqlite:///data.db"))

# 表结构
print(await inspector.inspect(connection_string="sqlite:///data.db", table_name="orders"))

# 数据分页预览
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders",
    purpose="sample",
    limit=20,
    offset=100,
))

# 建表 DDL
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders",
    purpose="ddl",
))

# 搜索
print(await inspector.inspect(connection_string="sqlite:///data.db", keyword="user"))
```

### DatabaseQuery（SQL 执行）

默认只读，写操作需要显式 `allow_write=True`。支持参数化（`:param`）防注入。

```python
query = DatabaseQuery()

# 参数化查询（推荐）
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="SELECT * FROM orders WHERE status = :s AND total > :min",
    params={"s": "shipped", "min": 100},
))

# 不同输出格式：table / csv / json / markdown
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="SELECT * FROM config",
    output_format="json",
))

# 快捷指令：count / distinct / aggregate / head / tail
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="count",
    table_name="orders",
    where="status = 'active'",
))
```

---

## Files（文件工具）

### FileViewer（通用文件查看器）

一个接口覆盖常见文件格式，支持智能推断：

- 有 `keyword` → 自动进入 `search` 模式
- 有 `start_row` / `end_row` → 自动进入 `range` 模式
- 其他情况 → `preview`

```python
viewer = FileViewer()

# Excel / CSV
print(await viewer.view_file("sales.xlsx"))
print(await viewer.view_file("sales.xlsx", keyword="北京"))
print(await viewer.view_file("sales.xlsx", purpose="structure"))
print(await viewer.view_file("sales.xlsx", sheet_name="__all__"))

# PDF / Word / PPT
print(await viewer.view_file("report.pdf", page_number=5))
print(await viewer.view_file("contract.docx", keyword="甲方"))
print(await viewer.view_file("slides.pptx", page_number=1))

# 代码/文本结构
print(await viewer.view_file("main.py", purpose="structure"))
```

### ImageReader（图片分析，多模态）

ImageReader 基于多模态 LLM（例如 `OpenAILike(..., is_multimodal=True)`）进行图片理解：

```python
from alphora.models import OpenAILike
from alphora_community.tools import ImageReader

vision_llm = OpenAILike(model_name="qwen-vl-plus", is_multimodal=True)
reader = ImageReader(llm=vision_llm)

# 图片描述
print(await reader.describe("photo.jpg"))

# OCR
print(await reader.extract_text("document.png"))

# 问答
print(await reader.ask("scene.jpg", question="图中有几辆车？"))

# 表格提取（Markdown）
print(await reader.extract_table("receipt.jpg"))

# 结构化提取（尽量返回 dict；模型不稳定时会回退为原始字符串）
data = await reader.extract_structured(
    "id_card.jpg",
    fields=["姓名", "身份证号", "地址"],
)
print(data)

# 多图对比
result = await reader.analyze_batch(
    ["before.jpg", "after.jpg"],
    compare=True,
    prompt="对比两张图的变化",
)
print(result)
```

---

## Web（网络工具）

### WebBrowser（网页抓取与解析）

自动识别内容类型（HTML/PDF/JSON 等），并输出“可读的”文本（默认 Markdown）。可选使用 Playwright 渲染 JS 页面。

```python
browser = WebBrowser()

# 抓取网页（可选提取链接/图片）
print(await browser.fetch(
    "https://example.com",
    extract_links=True,
    extract_images=True,
))

# 抓取 PDF（限制最大页数）
print(await browser.fetch(
    "https://example.com/paper.pdf",
    max_pdf_pages=20,
))

# JS 渲染（需要 playwright）
print(await browser.fetch(
    "https://spa-app.com",
    render_js=True,
    wait_for_selector=".content",
))
```

### WebSearchTool（互联网搜索，博查 API）

需要配置 `BOCHA_API_KEY`（环境变量）或构造时传 `api_key=...`：

```python
from alphora_community.tools import WebSearchTool

search = WebSearchTool()
print(await search.search("AI 最新进展", freshness="oneWeek"))
```

### ArxivSearchTool（论文检索）

```python
from alphora_community.tools import ArxivSearchTool

arxiv = ArxivSearchTool()
print(await arxiv.search("reinforcement learning", max_results=5, sort_by="submittedDate"))
```

---

## 设计原则

1. **对话友好**：输出偏“读得懂”，而不是仅返回原始对象
2. **少状态**：连接信息/关键参数尽量作为方法入参，适配对话过程动态传入
3. **安全默认**：危险操作默认禁止，必须显式开启
4. **优雅降级**：缺依赖/不支持时返回明确提示，而非直接崩溃

---

## 依赖清单（速查）

| 工具 | 必需依赖 | 可选依赖 |
|------|----------|----------|
| `DatabaseInspector` | `sqlalchemy` | `pymysql`, `psycopg2-binary` |
| `DatabaseQuery` | `sqlalchemy` | `pymysql`, `psycopg2-binary` |
| `FileViewer`（Excel/CSV） | `openpyxl`, `pandas` | — |
| `FileViewer`（Word） | `python-docx` | — |
| `FileViewer`（PPT） | `python-pptx` | — |
| `FileViewer`（PDF） | — | `pymupdf` / `pdfplumber` |
| `ImageReader` | 多模态 LLM 适配器 | `Pillow` |
| `WebBrowser` | `httpx`, `beautifulsoup4` | `html2text`, `lxml`, `pymupdf`, `playwright` |
| `WebSearchTool` | `httpx` | — |
| `ArxivSearchTool` | `httpx` | — |

