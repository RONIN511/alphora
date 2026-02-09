---
name: data-quality-audit
description: Audit CSV data quality with profiling, schema checks, anomaly detection, and a Markdown report. Use when validating datasets before analysis or ingestion.
license: Apache-2.0
compatibility: "Python 3.9+ (standard library only)"
metadata:
  author: alphora-community
  version: "1.0.0"
  tags: ["data-quality", "csv", "profiling", "validation", "reporting"]
---

# Data Quality Audit

这个 Skill 用于对 CSV 数据进行质量审计：快速画像、规则校验、异常检测，并生成结构化报告。

## 何时使用

- 数据进入分析或入库前需要质量把关
- 需要发现缺失、类型错误、异常值
- 需要给出清晰可复现的审计报告

## 输入要求

- CSV 文件路径
- 可选：schema JSON（参考 `references/EXAMPLE_SCHEMA.json`）

## 工作流（推荐）

1. **读取数据画像**
   - 运行 `scripts/profile_csv.py` 生成 `profile.json`
   - 目标：了解列、缺失率、基础统计

2. **校验 schema**
   - 运行 `scripts/validate_schema.py` 生成 `validation.json`
   - 目标：检查必填列、类型、唯一性约束

3. **异常检测**
   - 运行 `scripts/outlier_check.py` 生成 `outliers.json`
   - 目标：找出数值型字段异常

4. **生成报告**
   - 运行 `scripts/generate_report.py` + `assets/report_template.md`
   - 输出 Markdown 报告，便于分享/审阅

## 脚本说明

- `scripts/profile_csv.py`
  - 输入：CSV
  - 输出：`profile.json`
- `scripts/validate_schema.py`
  - 输入：CSV + schema JSON
  - 输出：`validation.json`
- `scripts/outlier_check.py`
  - 输入：CSV
  - 输出：`outliers.json`
- `scripts/generate_report.py`
  - 输入：profile/validation/outliers JSON + 模板
  - 输出：Markdown 报告

## 示例命令

```bash
python scripts/profile_csv.py --input data.csv --output profile.json
python scripts/validate_schema.py --input data.csv --schema references/EXAMPLE_SCHEMA.json --output validation.json
python scripts/outlier_check.py --input data.csv --output outliers.json --zscore 3.0
python scripts/generate_report.py \
  --profile profile.json \
  --validation validation.json \
  --outliers outliers.json \
  --template assets/report_template.md \
  --output report.md
```

## 参考资料

- `references/CHECKLIST.md`：审计清单
- `references/SEVERITY_RUBRIC.md`：问题严重度分级
- `references/EXAMPLE_SCHEMA.json`：schema 模板

## 输出格式约定

报告需要包含：

1. 概览（行数、列数、缺失率摘要）
2. 关键问题（按严重度）
3. 异常值示例
4. 结论与建议

## 注意事项

- 仅标准库实现，适合在 Sandbox 中运行
- 大文件建议先抽样或限制行数（`--limit`）
- 报告使用模板可保证结构一致
