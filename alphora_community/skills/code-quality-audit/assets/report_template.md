#!/usr/bin/env markdown
# Data Quality Audit Report

生成时间: {{generated_at}}

## 概览

- 读取行数: {{rows_read}}
- 缺失率 TOP5:
{{missing_summary}}

## Schema 校验

- 缺失必填列: {{missing_required_columns}}
- 必填值缺失计数: {{missing_required_values}}
- 重复值统计: {{duplicate_summary}}

## 异常值摘要

{{outlier_summary}}

## 结论与建议

- 按严重度评估并制定修复计划
- 对关键字段优先补齐或修正
