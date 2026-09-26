#!/usr/bin/env python3
"""Serialize manually authored Stage-1 v6 JSONL rows to canonical CSV/Parquet."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from stage1_v6_common import (
    SCHEMA_COLUMNS,
    canonical_csv_list,
    canonical_row,
    read_jsonl,
)


ARROW_SCHEMA = pa.schema(
    [
        *[(column, pa.string()) for column in SCHEMA_COLUMNS[:10]],
        ("acceptable_poi_ids", pa.list_(pa.string())),
        *[(column, pa.string()) for column in SCHEMA_COLUMNS[11:14]],
        ("n_acceptable", pa.int64()),
        ("is_multipositive", pa.bool_()),
    ]
)


def serialize(input_path: Path, csv_path: Path, parquet_path: Path) -> int:
    raw_rows = read_jsonl(input_path)
    rows = [canonical_row(row) for row in raw_rows]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    csv_descriptor, csv_temp_name = tempfile.mkstemp(
        prefix=f".{csv_path.name}.", suffix=".tmp", dir=str(csv_path.parent)
    )
    parquet_descriptor, parquet_temp_name = tempfile.mkstemp(
        prefix=f".{parquet_path.name}.", suffix=".tmp", dir=str(parquet_path.parent)
    )
    os.close(parquet_descriptor)
    csv_temp = Path(csv_temp_name)
    parquet_temp = Path(parquet_temp_name)
    try:
        with os.fdopen(csv_descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCHEMA_COLUMNS)
            writer.writeheader()
            for row in rows:
                serialized = dict(row)
                serialized["acceptable_poi_ids"] = canonical_csv_list(
                    row["acceptable_poi_ids"]
                )
                serialized["is_multipositive"] = (
                    "true" if row["is_multipositive"] else "false"
                )
                writer.writerow(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        table = pa.Table.from_pylist(rows, schema=ARROW_SCHEMA)
        pq.write_table(table, parquet_temp)
        # Read back before either output is committed.
        if pq.read_table(parquet_temp).num_rows != len(rows):
            raise RuntimeError("Parquet read-back row count mismatch")
        os.replace(csv_temp, csv_path)
        os.replace(parquet_temp, parquet_path)
        return len(rows)
    finally:
        if csv_temp.exists():
            csv_temp.unlink()
        if parquet_temp.exists():
            parquet_temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--parquet", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = serialize(args.input, args.csv, args.parquet)
        print(f"serialized {count} rows")
        return 0
    except Exception as error:
        print(f"serialization failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
