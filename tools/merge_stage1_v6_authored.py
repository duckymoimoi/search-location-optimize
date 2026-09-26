#!/usr/bin/env python3
"""Merge manually authored Stage-1 v6 JSONL batches by stable variant ID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_rows(paths: list[Path], key: str) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            merged[str(row[key])] = row
    return merged


def write_rows(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(rows[key], ensure_ascii=False, sort_keys=True) + "\n"
            for key in sorted(rows)
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-rows", type=Path, required=True)
    parser.add_argument("--base-trace", type=Path, required=True)
    parser.add_argument("--batch-rows", type=Path, action="append", default=[])
    parser.add_argument("--batch-trace", type=Path, action="append", default=[])
    parser.add_argument("--rows-output", type=Path, required=True)
    parser.add_argument("--trace-output", type=Path, required=True)
    args = parser.parse_args()
    rows = read_rows([args.base_rows, *args.batch_rows], "variant_id")
    traces = read_rows([args.base_trace, *args.batch_trace], "variant_id")
    write_rows(args.rows_output, rows)
    write_rows(args.trace_output, traces)
    print(json.dumps({"query_rows": len(rows), "trace_rows": len(traces)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
