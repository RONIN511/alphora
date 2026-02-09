#!/usr/bin/env python3
import argparse
import json
from typing import Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dedupe sources by title or url.")
    parser.add_argument("--input", required=True, help="Input JSON file")
    parser.add_argument("--output", required=True, help="Output JSON file")
    return parser.parse_args()


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def main() -> None:
    args = parse_args()
    with open(args.input, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    sources = data.get("sources", [])
    seen: Dict[str, dict] = {}
    for src in sources:
        key = normalize(src.get("url") or src.get("title", ""))
        if not key:
            continue
        if key not in seen:
            seen[key] = src
    payload = {"sources": list(seen.values()), "count": len(seen)}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
