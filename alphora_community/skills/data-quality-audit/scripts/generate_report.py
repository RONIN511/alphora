#!/usr/bin/env python3
import argparse
import json
from datetime import datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Markdown report.")
    parser.add_argument("--profile", required=True, help="Profile JSON path")
    parser.add_argument("--validation", required=True, help="Validation JSON path")
    parser.add_argument("--outliers", required=True, help="Outliers JSON path")
    parser.add_argument("--template", required=True, help="Report template path")
    parser.add_argument("--output", required=True, help="Output Markdown path")
    return parser.parse_args()


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def render(template: str, context: dict) -> str:
    for key, value in context.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    return template


def summarize_missing(profile: dict) -> str:
    columns = profile.get("columns", [])
    top = sorted(columns, key=lambda c: c.get("missing_rate", 0), reverse=True)[:5]
    lines = []
    for col in top:
        lines.append(f"- {col['name']}: {col['missing_rate']:.2%}")
    return "\n".join(lines) if lines else "- 无"


def summarize_outliers(outliers: dict) -> str:
    entries = outliers.get("outliers", {})
    lines = []
    for col, items in entries.items():
        if not items:
            continue
        lines.append(f"- {col}: {len(items)} 个（示例值 {items[0]['value']})")
    return "\n".join(lines) if lines else "- 无"


def main() -> None:
    args = parse_args()
    profile = load_json(args.profile)
    validation = load_json(args.validation)
    outliers = load_json(args.outliers)

    with open(args.template, "r", encoding="utf-8") as handle:
        template = handle.read()

    context = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "rows_read": profile.get("rows_read", 0),
        "missing_summary": summarize_missing(profile),
        "missing_required_columns": ", ".join(validation.get("missing_required_columns", [])) or "无",
        "missing_required_values": validation.get("missing_required_values", 0),
        "duplicate_summary": json.dumps(validation.get("duplicate_counts", {}), ensure_ascii=False),
        "outlier_summary": summarize_outliers(outliers),
    }

    report = render(template, context)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(report)


if __name__ == "__main__":
    main()
