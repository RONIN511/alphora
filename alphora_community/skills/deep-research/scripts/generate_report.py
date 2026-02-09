#!/usr/bin/env python3
import argparse
import json
from datetime import datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate research report.")
    parser.add_argument("--outline", required=True, help="Outline JSON path")
    parser.add_argument("--sources", required=True, help="Sources JSON path")
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


def format_sources(sources: list) -> str:
    lines = []
    for src in sources:
        title = src.get("title") or "未命名"
        url = src.get("url") or ""
        lines.append(f"- {title} {url}".strip())
    return "\n".join(lines) if lines else "- 无"


def format_outline(outline: list) -> str:
    lines = []
    for item in outline:
        lines.append(f"- {item['topic']}（{item['count']}）")
    return "\n".join(lines) if lines else "- 无"


def main() -> None:
    args = parse_args()
    outline = load_json(args.outline)
    sources = load_json(args.sources)
    with open(args.template, "r", encoding="utf-8") as handle:
        template = handle.read()

    context = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "outline_summary": format_outline(outline.get("outline", [])),
        "sources_list": format_sources(sources.get("sources", [])),
        "source_count": sources.get("count", 0),
    }
    report = render(template, context)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(report)


if __name__ == "__main__":
    main()
