#!/usr/bin/env python3
import argparse
import json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect sources from JSONL.")
    parser.add_argument("--input", required=True, help="JSONL file with sources")
    parser.add_argument("--output", required=True, help="Output JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = []
    with open(args.input, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            sources.append(json.loads(line))
    payload = {"sources": sources, "count": len(sources)}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
