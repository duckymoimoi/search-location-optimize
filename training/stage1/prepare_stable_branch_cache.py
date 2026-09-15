"""Adapt stable-v1 normalized tables to the frozen branch benchmark contract."""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dense", type=Path, required=True)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--cache-output", type=Path, required=True)
    parser.add_argument("--passage", default="context")
    parser.add_argument("--split", default="dev_synthetic")
    args = parser.parse_args()
    args.bundle_output.mkdir(parents=True, exist_ok=True)
    args.cache_output.mkdir(parents=True, exist_ok=True)

    rows = [
        row for row in pq.read_table(args.dataset / "queries_20k.parquet").to_pylist()
        if row["split"] == args.split
    ]
    qids = {row["query_id"] for row in rows}
    compatible: dict[str, set[str]] = defaultdict(set)
    parquet = pq.ParquetFile(args.dataset / "qrels.parquet")
    for batch in parquet.iter_batches(batch_size=200_000):
        for qrel in batch.to_pylist():
            if qrel["query_id"] in qids:
                compatible[qrel["query_id"]].add(qrel["poi_id"])
    for row in rows:
        ids = sorted(compatible[row["query_id"]])
        row["known_compatible_poi_ids"] = ids
        row["compatible_count"] = len(ids)
    pq.write_table(pa.Table.from_pylist(rows), args.bundle_output / "dev_synthetic.parquet", compression="zstd")
    shutil.copy2(args.dataset / "eligibility.parquet", args.bundle_output / "eligibility_v4.parquet")
    shutil.copy2(
        args.dense / f"{args.split}_{args.passage}_dense_exact_top100.parquet",
        args.cache_output / "dev_dense_exact_top100.parquet",
    )
    shutil.copy2(
        args.dense / f"{args.split}_query_embeddings.npy",
        args.cache_output / "dev_query_embeddings.npy",
    )
    typing_rows = pq.read_table(args.dense / f"typing_{args.passage}_dense_exact_top100.parquet").to_pylist()
    typing_vectors = np.load(args.dense / "typing_query_embeddings.npy")
    keep = [index for index, row in enumerate(typing_rows) if row["split"] == args.split]
    pq.write_table(
        pa.Table.from_pylist([typing_rows[index] for index in keep]),
        args.cache_output / "dev_sessions_dense_exact_top100.parquet",
        compression="zstd",
    )
    np.save(args.cache_output / "dev_session_embeddings.npy", typing_vectors[keep])
    print({"dev_queries": len(rows), "qrels_loaded": sum(map(len, compatible.values()))})


if __name__ == "__main__":
    main()
