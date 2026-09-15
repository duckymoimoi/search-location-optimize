"""Encode stable-v1 corpus/query passages and produce exact dense top-K runs."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return torch.sum(last_hidden_state * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)


def encode(model: Any, tokenizer: Any, texts: list[str], prefix: str, max_length: int, batch_size: int) -> np.ndarray:
    import torch
    import torch.nn.functional as functional

    parts = []
    model.eval()
    device = next(model.parameters()).device
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            tokens = tokenizer(
                [prefix + text for text in texts[start : start + batch_size]],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            tokens = {key: value.to(device) for key, value in tokens.items()}
            vector = functional.normalize(mean_pool(model(**tokens).last_hidden_state, tokens["attention_mask"]), p=2, dim=1)
            parts.append(vector.cpu().numpy().astype(np.float32, copy=False))
            if start and start % (batch_size * 50) == 0:
                print(f"encoded={start}/{len(texts)}", flush=True)
    return np.concatenate(parts)


def exact_topk(queries: np.ndarray, corpus: np.ndarray, ids: list[str], targets: list[str], top_k: int, chunk: int):
    id_index = {poi_id: index for index, poi_id in enumerate(ids)}
    outputs = []
    latency = []
    for start in range(0, len(queries), chunk):
        began = time.perf_counter()
        scores = queries[start : start + chunk] @ corpus.T
        elapsed = (time.perf_counter() - began) * 1000 / len(scores)
        latency.extend([elapsed] * len(scores))
        for offset, row_scores in enumerate(scores):
            target_index = id_index[targets[start + offset]]
            target_score = row_scores[target_index]
            target_rank = 1 + int(np.count_nonzero(row_scores > target_score))
            target_rank += int(np.count_nonzero(row_scores[:target_index] == target_score))
            candidate_indices = np.argpartition(-row_scores, top_k - 1)[:top_k]
            order = np.lexsort((candidate_indices, -row_scores[candidate_indices]))
            candidate_indices = candidate_indices[order]
            outputs.append((
                [ids[index] for index in candidate_indices],
                [float(row_scores[index]) for index in candidate_indices],
                target_rank,
            ))
    return outputs, latency


def summary(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values)
    return {
        "count": len(values), "mean_ms": float(array.mean()),
        "p50_ms": float(np.quantile(array, .5)), "p95_ms": float(np.quantile(array, .95)),
        "p99_ms": float(np.quantile(array, .99)), "max_ms": float(array.max()),
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_input_root(preferred: Path, anchor: str) -> Path:
    if (preferred / anchor).exists():
        return preferred
    kaggle_input = Path("/kaggle/input")
    matches = sorted(kaggle_input.rglob(anchor)) if kaggle_input.exists() else []
    if len(matches) == 1:
        return matches[0].parent
    raise FileNotFoundError(
        f"Cannot resolve {anchor}; preferred={preferred}; matches={[str(path) for path in matches]}"
    )


def ensure_kaggle_gpu_compatibility() -> None:
    """Kaggle's newest image may ship a wheel that dropped P100/sm_60."""
    if not Path("/kaggle").exists():
        return
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True, text=True, check=False,
    )
    if probe.stdout.strip().startswith("6.0"):
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--force-reinstall",
             "torch==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu126"],
            check=True,
        )
        # The base image's cu128 torchvision/torchaudio wheels are incompatible
        # with the pinned torch wheel; text-only BERT inference does not need them.
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("/kaggle/input/hanoi-poi-stage1-stable-v1"))
    parser.add_argument("--corpus", type=Path, default=Path("/kaggle/input/hanoi-poi-stage1-stable-v1"))
    parser.add_argument("--model", type=Path, default=Path("/kaggle/input/hanoi-poi-stage1-v4-model"))
    parser.add_argument("--output", type=Path, default=Path("/kaggle/working/stage1_stable_eval"))
    parser.add_argument("--passages", nargs="+", choices=["address", "context"], default=["address", "context"])
    parser.add_argument("--splits", nargs="+", default=["dev_synthetic", "test_synthetic", "architecture_holdout"])
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--query-max-length", type=int, default=64)
    parser.add_argument("--passage-max-length", type=int, default=192)
    parser.add_argument("--exact-chunk", type=int, default=64)
    parser.add_argument("--latency-samples", type=int, default=10)
    args = parser.parse_args()
    args.dataset = resolve_input_root(args.dataset, "queries_20k.parquet")
    args.corpus = resolve_input_root(args.corpus, "search_documents.parquet")
    args.model = resolve_input_root(args.model, "model.safetensors")
    args.output.mkdir(parents=True, exist_ok=True)

    docs = pq.read_table(args.corpus / "search_documents.parquet").to_pylist()
    searchable = {
        row["poi_id"]
        for row in pq.read_table(args.corpus / "pois.parquet", columns=["poi_id", "destination_searchable"]).to_pylist()
        if row["destination_searchable"]
    }
    docs = [row for row in docs if row["poi_id"] in searchable]
    ids = [row["poi_id"] for row in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate searchable POI IDs")

    eligibility = {row["query_id"]: row for row in pq.read_table(args.dataset / "eligibility.parquet").to_pylist()}
    queries = [row for row in pq.read_table(args.dataset / "queries_20k.parquet").to_pylist() if row["split"] in args.splits]
    sessions = [row for row in pq.read_table(args.dataset / "typing_sessions.parquet").to_pylist() if row["split"] in args.splits]
    texts = list(dict.fromkeys([row["query"] for row in queries] + [row["query"] for row in sessions]))

    ensure_kaggle_gpu_compatibility()
    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModel.from_pretrained(args.model).to(device).eval()
    encode(model, tokenizer, texts[:1], "query: ", args.query_max_length, 1)
    latency = []
    for text in texts[: args.latency_samples]:
        began = time.perf_counter()
        encode(model, tokenizer, [text], "query: ", args.query_max_length, 1)
        latency.append((time.perf_counter() - began) * 1000)
    began = time.perf_counter()
    vectors = encode(model, tokenizer, texts, "query: ", args.query_max_length, args.batch_size)
    query_encode_seconds = time.perf_counter() - began
    vector_by_text = dict(zip(texts, vectors))
    for split in args.splits:
        split_rows = [row for row in queries if row["split"] == split]
        np.save(args.output / f"{split}_query_embeddings.npy", np.stack([vector_by_text[row["query"]] for row in split_rows]))
    if sessions:
        np.save(args.output / "typing_query_embeddings.npy", np.stack([vector_by_text[row["query"]] for row in sessions]))

    runtime: dict[str, Any] = {
        "model_path": str(args.model.resolve()), "python": platform.python_version(),
        "torch": torch.__version__, "transformers": transformers.__version__,
        "device": str(device), "cpu_threads": torch.get_num_threads(), "query_batch1_latency": summary(latency),
        "query_bulk": {"unique": len(texts), "seconds": query_encode_seconds, "queries_per_second": len(texts) / query_encode_seconds},
        "passages": {},
    }
    for passage in args.passages:
        print(f"Encoding passage_{passage}: {len(docs)}", flush=True)
        began = time.perf_counter()
        corpus_vectors = encode(model, tokenizer, [row[f"passage_{passage}"] for row in docs], "passage: ", args.passage_max_length, args.batch_size)
        encode_seconds = time.perf_counter() - began
        np.save(args.output / f"corpus_{passage}_embeddings.npy", corpus_vectors)
        pq.write_table(pa.table({"row_index": range(len(ids)), "poi_id": ids}), args.output / f"corpus_{passage}_ids.parquet", compression="zstd")
        runtime["passages"][passage] = {"rows": len(ids), "encode_seconds": encode_seconds, "passages_per_second": len(ids) / encode_seconds, "splits": {}}
        for split in args.splits:
            split_rows = [row for row in queries if row["split"] == split]
            split_vectors = np.stack([vector_by_text[row["query"]] for row in split_rows])
            results, search_ms = exact_topk(split_vectors, corpus_vectors, ids, [row["intended_poi_id"] for row in split_rows], args.top_k, args.exact_chunk)
            output_rows = []
            for row, (top_ids, top_scores, target_rank) in zip(split_rows, results):
                flags = eligibility[row["query_id"]]
                output_rows.append({
                    **row,
                    "main_metric_candidate": flags["main_metric_candidate"],
                    "structured_metric_candidate": flags["structured_metric_candidate"],
                    "supervised_training_eligible": flags["supervised_training_eligible"],
                    "top_ids": top_ids, "top_scores": top_scores, "target_rank": target_rank,
                })
            pq.write_table(pa.Table.from_pylist(output_rows), args.output / f"{split}_{passage}_dense_exact_top{args.top_k}.parquet", compression="zstd")
            runtime["passages"][passage]["splits"][split] = {"queries": len(split_rows), "exact_search_latency": summary(search_ms)}
        session_rows = sessions
        if session_rows:
            session_vectors = np.stack([vector_by_text[row["query"]] for row in session_rows])
            results, search_ms = exact_topk(session_vectors, corpus_vectors, ids, [row["intended_poi_id"] for row in session_rows], args.top_k, args.exact_chunk)
            output_rows = [{**row, "top_ids": result[0], "top_scores": result[1], "target_rank": result[2]} for row, result in zip(session_rows, results)]
            pq.write_table(pa.Table.from_pylist(output_rows), args.output / f"typing_{passage}_dense_exact_top{args.top_k}.parquet", compression="zstd")
            runtime["passages"][passage]["typing_exact_search_latency"] = summary(search_ms)
    write_json(args.output / "dense_runtime.json", runtime)
    print(json.dumps(runtime, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
