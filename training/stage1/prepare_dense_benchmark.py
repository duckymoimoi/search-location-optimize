"""Encode frozen dev/session queries and compute exact dense top-K without holdout."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return torch.sum(last_hidden_state * mask, dim=1) / torch.clamp(
        mask.sum(dim=1), min=1e-9
    )


def encode(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    prefix: str,
    max_length: int,
    batch_size: int,
) -> np.ndarray:
    import torch
    import torch.nn.functional as functional

    output: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            encoded = tokenizer(
                [prefix + text for text in texts[start : start + batch_size]],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            hidden = model(**encoded).last_hidden_state
            embeddings = functional.normalize(
                mean_pool(hidden, encoded["attention_mask"]), p=2, dim=1
            )
            output.append(embeddings.cpu().numpy().astype(np.float32, copy=False))
    return np.concatenate(output, axis=0)


def exact_results(
    query_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    corpus_ids: list[str],
    target_ids: list[str],
    top_k: int,
    chunk_size: int,
) -> tuple[list[list[str]], list[list[float]], list[int], list[float]]:
    corpus_index = {canonical_id: index for index, canonical_id in enumerate(corpus_ids)}
    all_top_ids: list[list[str]] = []
    all_top_scores: list[list[float]] = []
    all_target_ranks: list[int] = []
    search_milliseconds: list[float] = []
    for start in range(0, len(query_embeddings), chunk_size):
        began = time.perf_counter()
        scores = query_embeddings[start : start + chunk_size] @ corpus_embeddings.T
        elapsed_ms = (time.perf_counter() - began) * 1000.0
        search_milliseconds.extend(
            [elapsed_ms / scores.shape[0]] * scores.shape[0]
        )
        for local_index, row_scores in enumerate(scores):
            target_index = corpus_index[target_ids[start + local_index]]
            target_score = row_scores[target_index]
            rank = 1 + int(np.count_nonzero(row_scores > target_score))
            rank += int(np.count_nonzero(row_scores[:target_index] == target_score))
            candidate_indices = np.argpartition(-row_scores, top_k - 1)[:top_k]
            order = np.lexsort((candidate_indices, -row_scores[candidate_indices]))
            candidate_indices = candidate_indices[order]
            all_top_ids.append([corpus_ids[index] for index in candidate_indices])
            all_top_scores.append(
                [float(row_scores[index]) for index in candidate_indices]
            )
            all_target_ranks.append(rank)
    return all_top_ids, all_top_scores, all_target_ranks, search_milliseconds


def latency_summary(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean_ms": float(np.mean(array)),
        "p50_ms": float(np.quantile(array, 0.50)),
        "p95_ms": float(np.quantile(array, 0.95)),
        "p99_ms": float(np.quantile(array, 0.99)),
        "max_ms": float(np.max(array)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--exact-chunk-size", type=int, default=64)
    parser.add_argument("--latency-samples", type=int, default=100)
    args = parser.parse_args()

    bundle = Path(args.bundle)
    artifacts = Path(args.artifacts)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = json.loads((artifacts / "inference_config.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (artifacts / "final_model_manifest.json").read_text(encoding="utf-8")
    )
    if manifest["dataset_version"] != "hnq20k-pilot-v4":
        raise ValueError("This benchmark requires the selected v4 checkpoint")

    dev_rows = pq.read_table(bundle / "dev_synthetic.parquet").to_pylist()
    overlay = {
        row["query_id"]: row
        for row in pq.read_table(bundle / "eligibility_v4.parquet").to_pylist()
    }
    for row in dev_rows:
        for field in (
            "main_metric_candidate",
            "structured_metric_candidate",
            "supervised_training_eligible",
        ):
            row[field] = overlay[row["query_id"]][field]

    session_rows = [
        row
        for row in pq.read_table(bundle / "typing_sessions.parquet").to_pylist()
        if row["split"] == "dev_synthetic"
    ]
    all_texts = [row["query"] for row in dev_rows] + [
        row["query"] for row in session_rows
    ]
    unique_texts = list(dict.fromkeys(all_texts))

    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(artifacts / "final_model")
    model = AutoModel.from_pretrained(artifacts / "final_model").cpu().eval()
    warmup_text = unique_texts[:1]
    encode(
        model,
        tokenizer,
        warmup_text,
        config["query_prefix"],
        config["max_query_tokens"],
        1,
    )
    sample_texts = unique_texts[: min(args.latency_samples, len(unique_texts))]
    latency_values: list[float] = []
    for text in sample_texts:
        began = time.perf_counter()
        encode(
            model,
            tokenizer,
            [text],
            config["query_prefix"],
            config["max_query_tokens"],
            1,
        )
        latency_values.append((time.perf_counter() - began) * 1000.0)

    began = time.perf_counter()
    unique_embeddings = encode(
        model,
        tokenizer,
        unique_texts,
        config["query_prefix"],
        config["max_query_tokens"],
        args.batch_size,
    )
    bulk_seconds = time.perf_counter() - began
    embedding_by_text = dict(zip(unique_texts, unique_embeddings))
    dev_embeddings = np.stack([embedding_by_text[row["query"]] for row in dev_rows])
    session_embeddings = np.stack(
        [embedding_by_text[row["query"]] for row in session_rows]
    )
    np.save(output / "dev_query_embeddings.npy", dev_embeddings)
    np.save(output / "dev_session_embeddings.npy", session_embeddings)

    corpus_embeddings = np.load(artifacts / "corpus_embeddings.npy", mmap_mode="r")
    corpus_ids = (
        pq.read_table(artifacts / "corpus_id_map.parquet", columns=["canonical_id"])
        .column(0)
        .to_pylist()
    )
    dev_top_ids, dev_top_scores, dev_ranks, dev_search_ms = exact_results(
        dev_embeddings,
        corpus_embeddings,
        corpus_ids,
        [row["intended_poi_id"] for row in dev_rows],
        args.top_k,
        args.exact_chunk_size,
    )
    dev_output = []
    for row, ids, scores, rank in zip(
        dev_rows, dev_top_ids, dev_top_scores, dev_ranks
    ):
        dev_output.append(
            {
                "query_id": row["query_id"],
                "query": row["query"],
                "track": row["track"],
                "case_type": row["case_type"],
                "query_family_id": row["query_family_id"],
                "intended_poi_id": row["intended_poi_id"],
                "known_compatible_poi_ids": row["known_compatible_poi_ids"],
                "compatible_count": row["compatible_count"],
                "main_metric_candidate": row["main_metric_candidate"],
                "structured_metric_candidate": row["structured_metric_candidate"],
                "top_ids": ids,
                "top_scores": scores,
                "target_rank": rank,
            }
        )
    pq.write_table(
        pa.Table.from_pylist(dev_output),
        output / "dev_dense_exact_top100.parquet",
        compression="zstd",
    )

    session_top_ids, session_top_scores, session_ranks, session_search_ms = exact_results(
        session_embeddings,
        corpus_embeddings,
        corpus_ids,
        [row["intended_poi_id"] for row in session_rows],
        args.top_k,
        args.exact_chunk_size,
    )
    session_output = []
    for row, ids, scores, rank in zip(
        session_rows, session_top_ids, session_top_scores, session_ranks
    ):
        session_output.append(
            {
                **row,
                "top_ids": ids,
                "top_scores": scores,
                "target_rank": rank,
            }
        )
    pq.write_table(
        pa.Table.from_pylist(session_output),
        output / "dev_sessions_dense_exact_top100.parquet",
        compression="zstd",
    )
    write_json(
        output / "dense_runtime.json",
        {
            "holdout_evaluated": False,
            "model_manifest": manifest,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "cpu_threads": torch.get_num_threads(),
            "dev_queries": len(dev_rows),
            "dev_session_events": len(session_rows),
            "unique_query_texts_encoded": len(unique_texts),
            "batch_size": args.batch_size,
            "bulk_encode_seconds": bulk_seconds,
            "bulk_queries_per_second": len(unique_texts) / bulk_seconds,
            "batch1_encode_latency": latency_summary(latency_values),
            "exact_dense_dev_latency": latency_summary(dev_search_ms),
            "exact_dense_session_latency": latency_summary(session_search_ms),
        },
    )
    print(
        json.dumps(
            {
                "dev_queries": len(dev_rows),
                "session_events": len(session_rows),
                "unique_texts": len(unique_texts),
                "bulk_seconds": bulk_seconds,
                "batch1_p95_ms": latency_summary(latency_values)["p95_ms"],
            }
        )
    )


if __name__ == "__main__":
    main()
