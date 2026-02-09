#!/usr/bin/env python3
import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


SUPPORTED_TYPES = {"string", "int", "float", "date"}


@dataclass
class ColumnRule:
    name: str
    col_type: str
    required: bool
    unique: bool
    date_format: Optional[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate CSV against schema JSON.")
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--schema", required=True, help="Schema JSON path")
    parser.add_argument("--output", required=True, help="Output JSON file")
    parser.add_argument("--limit", type=int, default=20000, help="Max rows to validate")
    return parser.parse_args()


def load_schema(path: str) -> List[ColumnRule]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    columns = []
    for col in data.get("columns", []):
        col_type = col.get("type", "string")
        if col_type not in SUPPORTED_TYPES:
            raise SystemExit(f"Unsupported type: {col_type}")
        columns.append(
            ColumnRule(
                name=col["name"],
                col_type=col_type,
                required=bool(col.get("required", False)),
                unique=bool(col.get("unique", False)),
                date_format=col.get("format"),
            )
        )
    return columns


def validate_value(rule: ColumnRule, raw: str) -> Optional[str]:
    if raw == "":
        return "missing"
    if rule.col_type == "string":
        return None
    if rule.col_type == "int":
        try:
            int(raw)
            return None
        except ValueError:
            return "type_error"
    if rule.col_type == "float":
        try:
            float(raw)
            return None
        except ValueError:
            return "type_error"
    if rule.col_type == "date":
        fmt = rule.date_format or "%Y-%m-%d"
        try:
            datetime.strptime(raw, fmt)
            return None
        except ValueError:
            return "type_error"
    return "type_error"


def main() -> None:
    args = parse_args()
    rules = load_schema(args.schema)
    required_columns = {r.name for r in rules if r.required}
    unique_columns = {r.name for r in rules if r.unique}
    errors: Dict[str, Dict[str, int]] = {r.name: {"missing": 0, "type_error": 0} for r in rules}
    uniques: Dict[str, set] = {name: set() for name in unique_columns}
    duplicates: Dict[str, int] = {name: 0 for name in unique_columns}
    row_count = 0
    missing_required = 0

    with open(args.input, "r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("CSV has no header.")
        header = set(reader.fieldnames)
        missing_cols = sorted(required_columns - header)

        for row in reader:
            row_count += 1
            if row_count > args.limit:
                break
            for rule in rules:
                raw = (row.get(rule.name) or "").strip()
                issue = validate_value(rule, raw)
                if issue:
                    errors[rule.name][issue] += 1
                if issue == "missing" and rule.required:
                    missing_required += 1
                if rule.name in unique_columns and raw != "":
                    if raw in uniques[rule.name]:
                        duplicates[rule.name] += 1
                    else:
                        uniques[rule.name].add(raw)

    payload = {
        "rows_checked": row_count,
        "missing_required_columns": missing_cols,
        "missing_required_values": missing_required,
        "column_errors": errors,
        "duplicate_counts": duplicates,
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
