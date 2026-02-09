#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a research outline.")
    parser.add_argument("--input", required=True, help="Input JSON file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    sources = data.get("sources", [])
    grouped = defaultdict(list)
    for src in sources:
        topic = src.get("topic") or "未分类"
        grouped[topic].append(src)

    outline = []
    for topic, items in grouped.items():
        outline.append(
            {
                "topic": topic,
                "count": len(items),
                "sources": [{"title": s.get("title"), "url": s.get("url")} for s in items],
            }
        )

    payload = {"outline": outline, "total_topics": len(outline)}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
