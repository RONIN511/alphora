#!/usr/bin/env python3
import argparse
import csv
import json
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None

    def update(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2
        if self.min_value is None or value < self.min_value:
            self.min_value = value
        if self.max_value is None or value > self.max_value:
            self.max_value = value

    @property
    def variance(self) -> float:
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

    @property
    def stdev(self) -> float:
        return self.variance ** 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile CSV columns and basic stats.")
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--limit", type=int, default=100000, help="Max rows to read")
    parser.add_argument("--sample", type=int, default=5, help="Sample values per column")
    return parser.parse_args()


def try_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def main() -> None:
    args = parse_args()
    missing_counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    numeric_stats: Dict[str, RunningStats] = {}
    non_numeric_counts: Dict[str, int] = {}
    row_count = 0

    with open(args.input, "r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("CSV has no header.")
        for name in reader.fieldnames:
            missing_counts[name] = 0
            samples[name] = []
            numeric_stats[name] = RunningStats()
            non_numeric_counts[name] = 0

        for row in reader:
            row_count += 1
            if row_count > args.limit:
                break
            for name in reader.fieldnames:
                raw = (row.get(name) or "").strip()
                if raw == "":
                    missing_counts[name] += 1
                    continue
                if len(samples[name]) < args.sample:
                    samples[name].append(raw)
                value = try_float(raw)
                if value is None:
                    non_numeric_counts[name] += 1
                else:
                    numeric_stats[name].update(value)

    columns = []
    for name in missing_counts.keys():
        stats = numeric_stats[name]
        numeric_only = stats.count > 0 and non_numeric_counts[name] == 0
        columns.append(
            {
                "name": name,
                "missing": missing_counts[name],
                "missing_rate": (missing_counts[name] / row_count) if row_count else 0.0,
                "sample_values": samples[name],
                "numeric": numeric_only,
                "numeric_stats": {
                    "count": stats.count,
                    "min": stats.min_value,
                    "max": stats.max_value,
                    "mean": stats.mean if stats.count else None,
                    "stdev": stats.stdev if stats.count else None,
                },
            }
        )

    payload = {
        "rows_read": row_count,
        "columns": columns,
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
