#!/usr/bin/env python3
import argparse
import csv
import json
from typing import Dict, List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect numeric outliers in CSV.")
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--columns", default="", help="Comma-separated columns to check")
    parser.add_argument("--zscore", type=float, default=3.0, help="Z-score threshold")
    parser.add_argument("--limit", type=int, default=50000, help="Max rows to read")
    parser.add_argument("--max-outliers", type=int, default=20, help="Max outliers per column")
    return parser.parse_args()


def try_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def main() -> None:
    args = parse_args()
    selected = [c.strip() for c in args.columns.split(",") if c.strip()]
    rows: List[Dict[str, str]] = []
    values: Dict[str, List[float]] = {}
    row_count = 0

    with open(args.input, "r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("CSV has no header.")
        columns = selected or list(reader.fieldnames)
        values = {c: [] for c in columns}

        for row in reader:
            row_count += 1
            if row_count > args.limit:
                break
            rows.append(row)
            for col in columns:
                raw = (row.get(col) or "").strip()
                val = try_float(raw)
                if val is not None:
                    values[col].append(val)

    stats = {}
    for col, col_values in values.items():
        m = mean(col_values)
        s = stdev(col_values)
        stats[col] = {"mean": m, "stdev": s, "count": len(col_values)}

    outliers = {}
    for col in values.keys():
        m = stats[col]["mean"]
        s = stats[col]["stdev"]
        if s == 0:
            outliers[col] = []
            continue
        col_outliers = []
        for row in rows:
            raw = (row.get(col) or "").strip()
            val = try_float(raw)
            if val is None:
                continue
            z = abs((val - m) / s)
            if z >= args.zscore:
                col_outliers.append({"value": val, "zscore": z, "row": row})
                if len(col_outliers) >= args.max_outliers:
                    break
        outliers[col] = col_outliers

    payload = {
        "rows_checked": row_count,
        "zscore_threshold": args.zscore,
        "stats": stats,
        "outliers": outliers,
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
