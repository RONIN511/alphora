# Alphora Community - Tools

为 AI Agent 系统提供的工具集合。每个工具均设计为**异步接口 + 字符串输出**，方便 Agent 直接理解和使用返回结果。

---

## 模块总览

```
tools/
├── database/               # 数据库工具
│   ├── __init__.py             # 模块导出
│   ├── connection.py           # 连接管理与缓存
│   ├── safety.py               # SQL 安全校验
│   ├── formatter.py            # 结果格式化
│   ├── inspector.py            # DatabaseInspector — 结构探查
│   └── query.py                # DatabaseQuery — 查询执行
├── files/                  # 文件处理工具
│   ├── file_viewer.py          # 通用文件查看器
│   ├── image_reader.py         # 图片分析（多模态 LLM）
│   └── viewers/                # 各格式查看器实现
│       ├── tabular.py              # Excel / CSV / TSV
│       ├── document.py             # Word (.docx)
│       ├── presentation.py         # PowerPoint (.pptx)
│       ├── pdf.py                  # PDF
│       └── text.py                 # 文本 / 代码 / JSON / Markdown
└── web/                    # 网络工具
    ├── arxiv.py                # arXiv 论文搜索
    ├── bocha.py                # 博查互联网搜索
    └── browser.py              # 网页抓取与解析
```

---

## 🗄️ Database — 数据库工具

面向 AI Agent 的数据库交互工具，支持 SQLite、MySQL、PostgreSQL。

**核心设计：** `connection_string` 作为方法入参（而非构造参数），适配对话过程中动态获取连接信息的场景。内部通过 ConnectionManager 缓存引擎，同一连接字符串不会重复创建。

### 安装依赖

```bash
pip install sqlalchemy          # 必需
pip install pymysql             # MySQL
pip install psycopg2-binary     # PostgreSQL
```

### DatabaseInspector — 结构探查

用于了解数据库"长什么样"：有哪些表、每张表什么结构、表之间什么关系。
通过 `purpose` 参数选择探查模式，一个方法覆盖所有探查需求。

```python
from alphora_community.tools.database import DatabaseInspector

inspector = DatabaseInspector()

# 数据库概览（表列表 + 行数 + 外键关系）
print(await inspector.inspect(
    connection_string="sqlite:///data.db"
))

# MySQL / PostgreSQL
print(await inspector.inspect(
    connection_string="mysql+pymysql://user:pass@localhost/mydb"
))

# 查看单张表的详细结构（列、类型、主键、索引、数据采样）
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders"
))

# 数据预览（支持分页）
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders",
    purpose="sample",
    limit=20,
    offset=100
))

# 外键关系图
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    purpose="relationships"
))

# 建表 SQL
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders",
    purpose="ddl"
))

# 搜索表名/列名
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    keyword="user"
))

# 表统计信息（空值比例、唯一值数等）
print(await inspector.inspect(
    connection_string="sqlite:///data.db",
    table_name="orders",
    purpose="stats"
))
```

**探查模式一览：**

| purpose | 说明 | 需要 table_name |
|---------|------|:---:|
| `auto` | 自动推断（默认） | — |
| `overview` | 全局概览 | ❌ |
| `describe` | 表详细结构 | ✅ |
| `sample` | 数据分页预览 | ✅ |
| `relationships` | 外键关系 | 可选 |
| `ddl` | 建表 SQL | ✅ |
| `search` | 搜索表名/列名 | ❌ |
| `stats` | 列统计信息 | ✅ |

**智能推断：**
- 无 table_name → `overview`
- 有 table_name → `describe`
- 有 keyword → `search`

**典型 Agent 工作流：**
1. `inspect()` → 了解全局
2. `inspect(table_name="target")` → 看目标表结构
3. 拼 SQL → 用 `DatabaseQuery` 执行

### DatabaseQuery — 查询执行

安全地执行 SQL 查询，带参数化防注入、结果格式化、只读保护。
支持直接写 SQL 和快捷模式两种用法。

```python
from alphora_community.tools.database import DatabaseQuery

query = DatabaseQuery()

# 简单查询
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="SELECT * FROM users LIMIT 10"
))

# 参数化查询（防注入）
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="SELECT * FROM orders WHERE status = :status AND total > :min",
    params={"status": "shipped", "min": 100}
))

# 不同输出格式
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="SELECT * FROM config",
    output_format="json"
))

# 快捷：计数
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="count",
    table_name="orders",
    where="status = 'active'"
))

# 快捷：唯一值列表
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="distinct",
    table_name="orders",
    column="status"
))

# 快捷：聚合统计（自动对数值列计算 MIN/MAX/AVG/SUM）
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="aggregate",
    table_name="orders"
))

# 快捷：查看前/后 N 行
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="head",
    table_name="orders",
    max_rows=20
))

# 写操作（需显式开启）
print(await query.execute(
    connection_string="sqlite:///data.db",
    sql="UPDATE users SET status = 'inactive' WHERE last_login < '2023-01-01'",
    allow_write=True
))
```

**快捷模式：**

| sql 值 | 说明 | 需要参数 |
|---------|------|----------|
| `"count"` | 统计行数 | table_name, where(可选) |
| `"distinct"` | 唯一值列表 | table_name, column |
| `"aggregate"` | 数值列聚合 | table_name, where(可选) |
| `"head"` | 前 N 行 | table_name |
| `"tail"` | 后 N 行 | table_name |

**安全机制：**

| 机制 | 说明 |
|------|------|
| 只读模式 | 默认拦截 INSERT/UPDATE/DELETE/DROP 等 |
| 危险拦截 | DROP DATABASE、TRUNCATE 等始终拦截 |
| 多语句拦截 | 不允许一次提交多条 SQL |
| 参数化查询 | 使用 `:param` 语法防注入 |
| 行数限制 | 默认最多返回 500 行 |

---

## 📁 Files — 文件处理工具

### FileViewer — 通用文件查看器

一个接口处理所有格式，自动根据扩展名分发到对应的查看器。

```python
from alphora_community.tools import FileViewer

viewer = FileViewer()

# 预览 Excel（多 sheet 时自动显示概要）
print(await viewer.view_file("sales.xlsx"))

# 搜索关键词（自动切换 search 模式，无需指定 purpose）
print(await viewer.view_file("sales.xlsx", keyword="北京"))

# 查看指定 Sheet
print(await viewer.view_file("sales.xlsx", sheet_name="月度汇总"))

# 查看表结构
print(await viewer.view_file("sales.xlsx", purpose="structure"))

# 查看指定行范围
print(await viewer.view_file("sales.xlsx", start_row=10, end_row=20))

# 查看 PDF 指定页
print(await viewer.view_file("report.pdf", page_number=5))

# 在 Word 文档中搜索
print(await viewer.view_file("contract.docx", keyword="甲方"))

# 查看 Python 代码结构
print(await viewer.view_file("main.py", purpose="structure"))
```

**支持的格式：**

| 类型 | 扩展名 | 特殊功能 |
|------|--------|----------|
| 表格 | .xlsx .xls .csv .tsv | 多 Sheet、合并单元格处理、全局搜索 |
| 文档 | .docx .doc | 段落/表格提取、标题结构 |
| 演示 | .pptx .ppt | 逐页浏览、内容搜索 |
| PDF  | .pdf | PyMuPDF/pdfplumber 双引擎、目录提取 |
| 文本 | .txt .md .json .yaml .py .js 等 | 代码结构分析、JSON 结构解析 |

**智能参数推断：**
- 有 `keyword` → 自动 `search` 模式
- 有 `start_row`/`end_row` → 自动 `range` 模式
- 无额外参数 → `preview` 模式

### ImageReader — 图片分析

通过多模态 LLM 分析图片内容，支持描述、OCR、问答、结构化提取等。

```python
from alphora_community.tools import ImageReader

reader = ImageReader(llm=your_multimodal_llm)

# 图片描述
print(await reader.describe("photo.jpg"))

# OCR 文字识别
print(await reader.extract_text("document.png"))

# 问答
print(await reader.ask("scene.jpg", question="图中有几辆车？"))

# 表格提取
print(await reader.extract_table("receipt.jpg"))

# 结构化信息提取
data = await reader.extract_structured(
    "id_card.jpg",
    fields=["姓名", "身份证号", "地址"]
)

# 多图对比
result = await reader.analyze_batch(
    ["before.jpg", "after.jpg"],
    compare=True,
    prompt="对比两张图的变化"
)
```

**支持的模式：**

| 模式 | 用途 |
|------|------|
| `describe` | 详细描述图片内容 |
| `ocr` | 识别文字 |
| `qa` | 图片问答 |
| `extract` | 结构化信息提取 (JSON) |
| `summary` | 一句话概括 |
| `table` | 表格识别 (Markdown) |
| `code` | 代码识别 |
| `chart` | 图表分析 |

---

## 🌐 Web — 网络工具

### WebBrowser — 网页抓取与解析

智能网页浏览器，自动处理 HTML、PDF、JSON 等内容类型。

```python
from alphora_community.tools import WebBrowser

browser = WebBrowser()

# 抓取网页（自动提取正文、过滤噪音）
result = await browser.fetch("https://example.com")

# 抓取 PDF
result = await browser.fetch("https://example.com/paper.pdf", max_pdf_pages=20)

# 提取链接和图片
result = await browser.fetch(
    "https://example.com",
    extract_links=True,
    extract_images=True
)

# JavaScript 动态渲染页面
result = await browser.fetch(
    "https://spa-app.com",
    render_js=True,
    wait_for_selector=".content"
)
```

**特性：**
- HTML → Markdown 智能转换，过滤导航/广告/侧边栏
- PDF 智能换行合并（连字符断词、段落识别）
- 自动重定向跟踪
- 失败自动重试
- 可选 Playwright 渲染 SPA 页面

### WebSearchTool — 互联网搜索（博查 API）

```python
from alphora_community.tools import WebSearchTool

search = WebSearchTool(api_key="your_bocha_api_key")

# 基础搜索
result = await search.search("特斯拉 2024 销量")

# 限定时间范围
result = await search.search("AI 最新进展", freshness="oneWeek")
```

### ArxivSearchTool — 学术论文搜索

```python
from alphora_community.tools import ArxivSearchTool

arxiv = ArxivSearchTool()  # 无需 API Key

# 搜索论文
result = await arxiv.search("large language model agents", max_results=10)

# 按日期排序
result = await arxiv.search("reinforcement learning", sort_by="submittedDate")
```

---

## 🏗️ 设计原则

1. **字符串输出** — 所有工具返回格式化字符串，Agent 可直接理解
2. **异步优先** — 核心方法均为 `async`，适配异步 Agent 框架
3. **智能推断** — 参数冲突时自动推断意图并提示
4. **安全可控** — 数据库只读默认、查询校验、结果截断
5. **优雅降级** — 依赖缺失时给出清晰的安装提示，而非直接崩溃
6. **沙箱兼容** — 文件路径支持沙箱环境自动转换
7. **对话友好** — 连接信息作为方法入参，适配对话中动态传入的场景

---

## 📥 快速导入

```python
# 全部导入
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

# 按模块导入
from alphora_community.tools.database import DatabaseInspector, DatabaseQuery, DBType
from alphora_community.tools.files import FileViewer, ImageReader
from alphora_community.tools.web import WebBrowser, WebSearchTool, ArxivSearchTool
```

---

## 📋 依赖清单

| 工具 | 必需依赖 | 可选依赖 |
|------|----------|----------|
| DatabaseInspector | `sqlalchemy` | `pymysql`, `psycopg2` |
| DatabaseQuery | `sqlalchemy` | `pymysql`, `psycopg2` |
| FileViewer (Excel) | `openpyxl`, `pandas` | — |
| FileViewer (CSV) | `pandas` | — |
| FileViewer (Word) | `python-docx` | — |
| FileViewer (PPT) | `python-pptx` | — |
| FileViewer (PDF) | — | `pymupdf`, `pdfplumber` |
| ImageReader | — | `Pillow` (尺寸信息) |
| WebBrowser | `httpx`, `beautifulsoup4` | `html2text`, `pymupdf`, `playwright` |
| WebSearchTool | `httpx` | — |
| ArxivSearchTool | `httpx` | — |

一键安装核心依赖：

```bash
pip install sqlalchemy openpyxl pandas python-docx python-pptx pymupdf httpx beautifulsoup4 html2text
```
