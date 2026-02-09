---
name: deep-research
description: 深度研究任务的检索、去重、框架生成与报告输出。适用于政策、行业、竞品、技术趋势调研。
license: Apache-2.0
compatibility: "Python 3.9+ (standard library only)"
allowed_tools:
  - WebSearchTool
  - ArxivSearchTool
  - WebBrowser
  - FileViewer
metadata:
  author: alphora-community
  version: "1.0.0"
  tags: ["deep-research", "literature", "analysis", "reporting"]
---

# 深度研究（Deep Research）

该 Skill 用于将研究任务拆解为可执行流程：问题框架 → 资料收集 → 去重归档 → 证据聚合 → 报告生成。

## 适用场景

- 行业研究与趋势分析
- 竞品对比与策略建议
- 政策/法规解读与影响评估
- 技术路线评估与可行性分析

## 输入要求

- 研究问题或目标
- 可选：初始资料清单（JSONL，见 `assets/sample_sources.jsonl`）

## 工作流（推荐）

1. **问题拆解**
   - 参考 `references/QUESTION_FRAMEWORK.md`
   - 产出研究问题清单与假设

2. **网络检索与资料抓取（社区工具）**
   - 使用 `WebSearchTool.search` 做互联网检索（新闻/政策/行业数据）
   - 使用 `ArxivSearchTool.search` 做学术检索（论文与摘要）
   - 使用 `WebBrowser.fetch` 抓取网页/PDF 正文
   - 使用 `FileViewer.view_file` 阅读本地报告/Excel/PDF

3. **资料收集**
   - 运行 `scripts/collect_sources.py`
   - 输入：JSONL 资料清单
   - 输出：`sources.json`

4. **去重与分组**
   - 运行 `scripts/dedupe_sources.py`
   - 输出：`sources_deduped.json`

5. **结构化大纲**
   - 运行 `scripts/synthesize_outline.py`
   - 输出：`outline.json`

6. **生成报告**
   - 运行 `scripts/generate_report.py` + `assets/report_template.md`
   - 输出：Markdown 报告

## 示例命令

```bash
python scripts/collect_sources.py --input assets/sample_sources.jsonl --output sources.json
python scripts/dedupe_sources.py --input sources.json --output sources_deduped.json
python scripts/synthesize_outline.py --input sources_deduped.json --output outline.json
python scripts/generate_report.py \
  --outline outline.json \
  --sources sources_deduped.json \
  --template assets/report_template.md \
  --output research_report.md
```

## 工具调用示例

```python
from alphora_community.tools import WebSearchTool, ArxivSearchTool, WebBrowser, FileViewer

search = WebSearchTool()
arxiv = ArxivSearchTool()
browser = WebBrowser()
viewer = FileViewer()

# 互联网检索
result = await search.search("AI 产业 2024 市场规模", freshness="oneYear")

# 学术检索
papers = await arxiv.search("large language model agents", max_results=8)

# 抓取网页/PDF
page = await browser.fetch("https://example.com/report.pdf", max_pdf_pages=10)

# 读取本地文件
local = await viewer.view_file("reports/industry_report.pdf")
```

## 参考资料

- `references/QUESTION_FRAMEWORK.md`：问题拆解框架
- `references/RUBRIC.md`：证据质量与结论可信度标准
- `assets/report_template.md`：报告模板

## 输出要求

报告必须包含：

1. 研究问题与范围
2. 证据摘要（按来源分组）
3. 关键发现与结论
4. 风险与不确定性
5. 后续建议与开放问题
