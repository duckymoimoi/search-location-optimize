#!/usr/bin/env python3
"""Replayable Stage-1 baseline for the validated 500-POI v6 checkpoint.

Profiles:
- lexical_raw: current production lexical DSL, Elasticsearch top branch_depth
- dense_exact_raw: mE5 query encoder against frozen exact corpus vectors
- hybrid_rrf_raw: current two-branch RRF before candidate policy
- lexical_policy / dense_policy / hybrid_policy: candidate dedup + current
  query-only text priorities, capped at the configured candidate budget

This is a diagnostic over authored training data, not an untouched test set.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from datetime import UTC, datetime
import gc
import hashlib
import json
import math
from pathlib import Path
import re
import time
from types import SimpleNamespace
from typing import Any
import unicodedata
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as functional
from transformers import AutoModel, AutoTokenizer


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QUERIES = (
    ROOT
    / "data/vietnam/train_stage1_queries_v6/staging/003_hard_noise_500"
    / "query_variants_v6_hard_noise_500_final.parquet"
)
DEFAULT_EMBEDDINGS = ROOT / "artifacts/embeddings/me5_small/corpus_embeddings.npy"
DEFAULT_IDS = ROOT / "artifacts/embeddings/me5_small/poi_ids.parquet"
DEFAULT_POIS = ROOT / "data/vietnam/poi_corpus_v1/pois_core.parquet"
API_DIR = ROOT / "apps/poi-search/api"
APP_PATH = API_DIR / "app.py"
ALGO_FILES = (
    "textnorm.py",
    "lexical.py",
    "ranking.py",
    "geo.py",
    "es_query.py",
    "pipeline.py",
    "app.py",
)
POLICY_PATH = API_DIR / "search_policy.json"
DEFAULT_OUT = ROOT / "artifacts/results/stage1_v6_hard_noise_500_baseline"
METRIC_KS = (1, 5, 10, 20, 50)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def parse_acceptable(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple, np.ndarray)):
        return [str(item) for item in raw]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        value = ast.literal_eval(text)
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
    except (SyntaxError, ValueError):
        pass
    return [item for item in text.split("|") if item]


def load_policy_functions(policy: dict[str, Any]) -> dict[str, Any]:
    """Load real app functions without importing Runtime or loading the model."""
    functions: list[ast.FunctionDef] = []
    for name in ALGO_FILES:
        source = ast.parse((API_DIR / name).read_text(encoding="utf-8"))
        for node in source.body:
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
                functions.append(node)
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            *functions,
        ],
        type_ignores=[],
    )

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            self.status_code = status_code
            self.detail = detail

    namespace: dict[str, Any] = {
        "__name__": "stage1_policy_functions",
        "Any": Any,
        "Path": Path,
        "np": np,
        "torch": torch,
        "functional": functional,
        "re": re,
        "math": math,
        "unicodedata": unicodedata,
        "json": json,
        "time": time,
        "datetime": datetime,
        "UTC": UTC,
        "defaultdict": defaultdict,
        "SimpleNamespace": SimpleNamespace,
        "HTTPException": HTTPException,
        "POLICY": policy,
        "LEXICAL_CONFIG": policy["lexical"],
        "RANKING_POLICY": policy["ranking"],
        "BRANCH_DEPTH": int(policy["retrieval"]["branch_depth"]),
        "RRF_CONSTANT": int(policy["retrieval"]["rrf_constant"]),
        "CORPUS_VERSION": "vn-poi-core-v1",
        "RETRIEVAL_PROFILE": "hybrid",
        "INDEX_NAME": "vn-poi-core-v1-me5-small",
        "RELEASE_ID": "baseline",
        "MODEL_ID": "intfloat/multilingual-e5-small",
        "EMBEDDING_SPACE_ID": "me5-small-passage-384",
        "PASSAGE_BUILDER_VERSION": "passage_context-v1",
    }
    exec(
        compile(ast.fix_missing_locations(module), str(APP_PATH), "exec"),
        namespace,
    )
    return namespace


def post_msearch(es_url: str, index: str, bodies: list[dict[str, Any]]) -> list[list[str]]:
    lines: list[str] = []
    for body in bodies:
        lines.append(json.dumps({"index": index}, ensure_ascii=False))
        lines.append(json.dumps(body, ensure_ascii=False))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    request = Request(
        f"{es_url.rstrip('/')}/_msearch",
        data=payload,
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    output: list[list[str]] = []
    for item in result.get("responses", []):
        if item.get("error"):
            raise RuntimeError(f"Elasticsearch msearch error: {item['error']}")
        output.append([str(hit["_id"]) for hit in item["hits"]["hits"]])
    if len(output) != len(bodies):
        raise RuntimeError(f"Expected {len(bodies)} msearch responses, got {len(output)}")
    return output


def lexical_runs(
    queries: list[str],
    *,
    fn: dict[str, Any],
    es_url: str,
    index: str,
    depth: int,
    batch_size: int,
) -> list[list[str]]:
    runs: list[list[str]] = []
    began = time.perf_counter()
    for start in range(0, len(queries), batch_size):
        batch = queries[start : start + batch_size]
        bodies = [fn["lexical_body"](query, depth) for query in batch]
        runs.extend(post_msearch(es_url, index, bodies))
        print(
            f"lexical {min(start + len(batch), len(queries))}/{len(queries)} "
            f"elapsed={time.perf_counter() - began:.1f}s",
            flush=True,
        )
    return runs


def encode_queries(
    queries: list[str],
    *,
    model_id: str,
    cache_only: bool,
    batch_size: int,
    threads: int,
    glue_code_spans: Any,
) -> np.ndarray:
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=cache_only)
    model = AutoModel.from_pretrained(model_id, local_files_only=cache_only).cpu().eval()
    torch.set_num_threads(max(1, threads))
    vectors: list[np.ndarray] = []
    began = time.perf_counter()
    for start in range(0, len(queries), batch_size):
        batch = ["query: " + glue_code_spans(query) for query in queries[start : start + batch_size]]
        tokens = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=64,
            return_tensors="pt",
        )
        with torch.no_grad():
            hidden = model(**tokens).last_hidden_state
            mask = tokens["attention_mask"].unsqueeze(-1).expand(hidden.size()).float()
            pooled = torch.sum(hidden * mask, dim=1) / torch.clamp(mask.sum(dim=1), min=1e-9)
            encoded = functional.normalize(pooled, p=2, dim=1)
        vectors.append(encoded.numpy().astype(np.float32, copy=False))
        print(
            f"encode {min(start + len(batch), len(queries))}/{len(queries)} "
            f"elapsed={time.perf_counter() - began:.1f}s",
            flush=True,
        )
    result = np.vstack(vectors)
    del model, tokenizer, vectors
    gc.collect()
    return result


def dense_exact_runs(
    query_vectors: np.ndarray,
    *,
    corpus_embeddings_path: Path,
    corpus_ids_path: Path,
    depth: int,
    score_batch_size: int,
) -> list[list[str]]:
    corpus = np.load(corpus_embeddings_path, mmap_mode="r")
    ids_frame = pd.read_parquet(corpus_ids_path).sort_values("row_index")
    corpus_ids = ids_frame["poi_id"].astype(str).to_numpy()
    if corpus.shape[0] != len(corpus_ids) or corpus.shape[1] != query_vectors.shape[1]:
        raise ValueError(
            f"Embedding mismatch: corpus={corpus.shape}, ids={len(corpus_ids)}, "
            f"queries={query_vectors.shape}"
        )
    runs: list[list[str]] = []
    began = time.perf_counter()
    for start in range(0, len(query_vectors), score_batch_size):
        query_batch = query_vectors[start : start + score_batch_size]
        scores = query_batch @ corpus.T
        part = np.argpartition(scores, -depth, axis=1)[:, -depth:]
        for row_index, candidates in enumerate(part):
            candidate_scores = scores[row_index, candidates]
            candidate_ids = corpus_ids[candidates]
            order = np.lexsort((candidate_ids, -candidate_scores))
            runs.append([str(item) for item in candidate_ids[order]])
        print(
            f"dense-score {min(start + len(query_batch), len(query_vectors))}/"
            f"{len(query_vectors)} elapsed={time.perf_counter() - began:.1f}s",
            flush=True,
        )
    return runs


def aliases_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, np.ndarray):
        return [str(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)] if str(value).strip() else []


def load_candidate_docs(path: Path, needed_ids: set[str]) -> dict[str, dict[str, Any]]:
    columns = [
        "poi_id",
        "name",
        "aliases",
        "category",
        "address_text",
        "ranking_point",
        "entity_group_id",
        "branch_id",
        "preserve_individual_access_point",
    ]
    frame = pd.read_parquet(path, columns=columns)
    frame = frame[frame["poi_id"].astype(str).isin(needed_ids)]
    output: dict[str, dict[str, Any]] = {}
    for row in frame.itertuples(index=False):
        poi_id = str(row.poi_id)
        output[poi_id] = {
            "canonical_id": poi_id,
            "search_label": str(row.name or ""),
            "search_aliases": aliases_list(row.aliases),
            "category": str(row.category or ""),
            "address": str(row.address_text or ""),
            "ranking_point": row.ranking_point,
            "entity_group_id": row.entity_group_id,
            "branch_id": row.branch_id,
            "preserve_individual_access_point": bool(row.preserve_individual_access_point),
        }
    missing = needed_ids - set(output)
    if missing:
        raise ValueError(f"Missing {len(missing)} candidate docs; examples={sorted(missing)[:5]}")
    return output


def evidence_for(
    lexical_ids: list[str], dense_ids: list[str], *, rrf_constant: int
) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for branch in (lexical_ids, dense_ids):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1.0 / (rrf_constant + rank)
    return dict(scores)


def policy_order(
    query: str,
    ordered_ids: list[str],
    *,
    lexical_ids: list[str],
    dense_ids: list[str],
    doc_by_id: dict[str, dict[str, Any]],
    fn: dict[str, Any],
    rrf_constant: int,
) -> list[str]:
    scores = evidence_for(lexical_ids, dense_ids, rrf_constant=rrf_constant)
    docs = fn["candidate_documents"](
        ordered_ids,
        [doc_by_id[item] for item in ordered_ids if item in doc_by_id],
    )
    best = max((scores.get(doc["canonical_id"], 0.0) for doc in docs), default=1.0) or 1.0
    ranked = [
        (scores.get(doc["canonical_id"], 0.0) / best, rank, None, doc)
        for rank, doc in enumerate(docs, 1)
    ]
    ranked = fn["prioritize_name_address"](query, ranked)
    ranked = fn["prioritize_name_match_quality"](query, ranked)
    return [str(row[3]["canonical_id"]) for row in ranked]


def best_rank(ids: list[str], acceptable: set[str], miss_rank: int) -> int:
    for rank, poi_id in enumerate(ids, 1):
        if poi_id in acceptable:
            return rank
    return miss_rank


def summarize(frame: pd.DataFrame, rank_column: str) -> dict[str, Any]:
    ranks = frame[rank_column].astype(int).to_numpy()
    result: dict[str, Any] = {"n": int(len(ranks))}
    for k in METRIC_KS:
        result[f"Hit@{k}"] = float(np.mean(ranks <= k)) if len(ranks) else 0.0
    result["MRR@10"] = float(
        np.mean(np.where(ranks <= 10, 1.0 / ranks, 0.0))
    ) if len(ranks) else 0.0
    result["miss@50"] = int(np.sum(ranks > 50))
    return result


def grouped_metrics(frame: pd.DataFrame, rank_column: str, key: str) -> dict[str, Any]:
    return {
        str(value): summarize(group, rank_column)
        for value, group in frame.groupby(key, dropna=False, sort=True)
    }


def slot_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", str(value))
    return (int(match.group(1)) if match else 10_000, str(value))


def case_difficulty(frame: pd.DataFrame, rank_column: str) -> dict[str, Any]:
    pivot = frame.pivot(index="case_id", columns="slot", values=rank_column)
    ordered_slots = sorted(frame["slot"].dropna().astype(str).unique(), key=slot_sort_key)
    noisy_slots = ordered_slots[2:]
    noisy = frame[frame["slot"].isin(noisy_slots)]
    return {
        "case_count": int(len(pivot)),
        "all_6_hit_at_1": float((pivot.max(axis=1) <= 1).mean()),
        "all_6_hit_at_5": float((pivot.max(axis=1) <= 5).mean()),
        "any_variant_miss_at_50": float((pivot.max(axis=1) > 50).mean()),
        "noisy_slots": noisy_slots,
        "noisy_metrics": summarize(noisy, rank_column),
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Stage-1 baseline — {report['dataset']['label']}",
        "",
        f"Generated: {report['created_at_utc']}",
        "",
        f"> {report['warning']}",
        "",
        "## Overall",
        "",
        "| Profile | Hit@1 | Hit@5 | Hit@10 | Hit@20 | Hit@50 | MRR@10 | miss@50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile, metrics in report["profiles"].items():
        overall = metrics["overall"]
        lines.append(
            f"| {profile} | {overall['Hit@1']:.4f} | {overall['Hit@5']:.4f} | "
            f"{overall['Hit@10']:.4f} | {overall['Hit@20']:.4f} | "
            f"{overall['Hit@50']:.4f} | {overall['MRR@10']:.4f} | "
            f"{overall['miss@50']} |"
        )
    lines.extend(["", "## Hybrid policy by slot", ""])
    lines.extend([
        "| Slot | Hit@1 | Hit@5 | Hit@10 | Hit@20 | Hit@50 | MRR@10 | miss@50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for slot, metrics in report["profiles"]["hybrid_policy"]["by_slot"].items():
        lines.append(
            f"| {slot} | {metrics['Hit@1']:.4f} | {metrics['Hit@5']:.4f} | "
            f"{metrics['Hit@10']:.4f} | {metrics['Hit@20']:.4f} | "
            f"{metrics['Hit@50']:.4f} | {metrics['MRR@10']:.4f} | "
            f"{metrics['miss@50']} |"
        )
    difficulty = report["profiles"]["hybrid_policy"]["case_difficulty"]
    lines.extend(
        [
            "",
            "## Difficulty diagnostics",
            "",
            f"- Cases with all six variants at rank 1: {difficulty['all_6_hit_at_1']:.2%}",
            f"- Cases with all six variants in top 5: {difficulty['all_6_hit_at_5']:.2%}",
            f"- Cases with at least one miss@50: {difficulty['any_variant_miss_at_50']:.2%}",
            f"- Noisy slots: {', '.join(difficulty['noisy_slots'])}",
            f"- Noisy-slot Hit@1: {difficulty['noisy_metrics']['Hit@1']:.4f}",
            f"- Noisy-slot Hit@50: {difficulty['noisy_metrics']['Hit@50']:.4f}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--corpus-embeddings", type=Path, default=DEFAULT_EMBEDDINGS)
    parser.add_argument("--corpus-ids", type=Path, default=DEFAULT_IDS)
    parser.add_argument("--pois", type=Path, default=DEFAULT_POIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    parser.add_argument("--index", default="vn-poi-core-v1-me5-small")
    parser.add_argument("--model-id", default="intfloat/multilingual-e5-small")
    parser.add_argument("--dataset-label")
    parser.add_argument(
        "--dataset-role",
        choices=("authored_training", "frozen_evaluation"),
        default="authored_training",
    )
    parser.add_argument("--lexical-batch-size", type=int, default=100)
    parser.add_argument("--encode-batch-size", type=int, default=64)
    parser.add_argument("--score-batch-size", type=int, default=64)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    began = time.perf_counter()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    fn = load_policy_functions(policy)
    frame = pd.read_parquet(args.queries)
    if args.limit:
        frame = frame.head(args.limit).copy()
    frame["slot"] = frame["variant_id"].astype(str).str.extract(r"-(v\d+)$")[0]
    frame["acceptable"] = frame.apply(
        lambda row: parse_acceptable(row["acceptable_poi_ids"])
        or [str(row["intended_poi_id"])],
        axis=1,
    )
    queries = frame["query_text"].astype(str).tolist()
    depth = int(policy["retrieval"]["branch_depth"])
    budget = int(policy["retrieval"]["candidate_budget"])
    rrf_constant = int(policy["retrieval"]["rrf_constant"])
    miss_rank = budget + 1

    print(f"dataset rows={len(frame)} cases={frame['case_id'].nunique()} depth={depth}", flush=True)
    lexical = lexical_runs(
        queries,
        fn=fn,
        es_url=args.es_url,
        index=args.index,
        depth=depth,
        batch_size=args.lexical_batch_size,
    )
    query_vectors = encode_queries(
        queries,
        model_id=args.model_id,
        cache_only=not args.allow_download,
        batch_size=args.encode_batch_size,
        threads=args.threads,
        glue_code_spans=fn["glue_code_spans"],
    )
    dense = dense_exact_runs(
        query_vectors,
        corpus_embeddings_path=args.corpus_embeddings,
        corpus_ids_path=args.corpus_ids,
        depth=depth,
        score_batch_size=args.score_batch_size,
    )
    del query_vectors
    gc.collect()

    hybrid: list[list[str]] = []
    dense_min = int(policy["retrieval"]["dense_min_compact_chars"])
    for query, lexical_ids, dense_ids in zip(queries, lexical, dense, strict=True):
        if fn["compact_length"](query) < dense_min:
            hybrid.append(list(lexical_ids))
        else:
            hybrid.append(fn["rrf"](lexical_ids, dense_ids))

    needed_ids = {
        poi_id
        for runs in (lexical, dense, hybrid)
        for ids in runs
        for poi_id in ids
    }
    doc_by_id = load_candidate_docs(args.pois, needed_ids)
    lexical_policy: list[list[str]] = []
    dense_policy: list[list[str]] = []
    hybrid_policy: list[list[str]] = []
    for index, (query, lexical_ids, dense_ids, hybrid_ids) in enumerate(
        zip(queries, lexical, dense, hybrid, strict=True),
        1,
    ):
        lexical_policy.append(
            policy_order(
                query,
                lexical_ids,
                lexical_ids=lexical_ids,
                dense_ids=[],
                doc_by_id=doc_by_id,
                fn=fn,
                rrf_constant=rrf_constant,
            )
        )
        dense_policy.append(
            policy_order(
                query,
                dense_ids,
                lexical_ids=[],
                dense_ids=dense_ids,
                doc_by_id=doc_by_id,
                fn=fn,
                rrf_constant=rrf_constant,
            )
        )
        hybrid_dense = [] if fn["compact_length"](query) < dense_min else dense_ids
        hybrid_policy.append(
            policy_order(
                query,
                hybrid_ids,
                lexical_ids=lexical_ids,
                dense_ids=hybrid_dense,
                doc_by_id=doc_by_id,
                fn=fn,
                rrf_constant=rrf_constant,
            )
        )
        if index % 500 == 0:
            print(f"policy-rank {index}/{len(queries)}", flush=True)

    runs_by_profile = {
        "lexical_raw": lexical,
        "dense_exact_raw": dense,
        "hybrid_rrf_raw": hybrid,
        "lexical_policy": lexical_policy,
        "dense_policy": dense_policy,
        "hybrid_policy": hybrid_policy,
    }
    for profile, runs in runs_by_profile.items():
        frame[f"rank_{profile}"] = [
            best_rank(ids[:budget], set(acceptable), miss_rank)
            for ids, acceptable in zip(runs, frame["acceptable"], strict=True)
        ]
        frame[f"top5_{profile}"] = [json.dumps(ids[:5], ensure_ascii=False) for ids in runs]

    dataset_label = args.dataset_label or args.queries.stem
    warning = (
        "Authored training checkpoint; not an untouched model-selection test."
        if args.dataset_role == "authored_training"
        else "Frozen evaluation replay; results are no longer blind after this run."
    )
    report: dict[str, Any] = {
        "protocol": "stage1_current_policy_baseline_v1",
        "warning": warning,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "elapsed_seconds": time.perf_counter() - began,
        "dataset": {
            "label": dataset_label,
            "role": args.dataset_role,
            "path": display_path(args.queries),
            "sha256": sha256(args.queries),
            "rows": int(len(frame)),
            "cases": int(frame["case_id"].nunique()),
        },
        "runtime": {
            "policy_path": str(POLICY_PATH.relative_to(ROOT)),
            "policy_sha256": sha256(POLICY_PATH),
            "policy_version": policy["policy_version"],
            "app_sha256": hashlib.sha256(
                b"".join((API_DIR / name).read_bytes() for name in ALGO_FILES)
            ).hexdigest(),
            "model_id": args.model_id,
            "corpus_embeddings_sha256": sha256(args.corpus_embeddings),
            "corpus_ids_sha256": sha256(args.corpus_ids),
            "branch_depth": depth,
            "candidate_budget": budget,
            "rrf_constant": rrf_constant,
        },
        "profiles": {},
    }
    for profile in runs_by_profile:
        rank_column = f"rank_{profile}"
        report["profiles"][profile] = {
            "overall": summarize(frame, rank_column),
            "by_slot": grouped_metrics(frame, rank_column, "slot"),
            "by_family": grouped_metrics(frame, rank_column, "query_variant_family"),
            "by_severity": grouped_metrics(frame, rank_column, "severity"),
            "by_stratum": grouped_metrics(frame, rank_column, "primary_sampling_stratum"),
            "case_difficulty": case_difficulty(frame, rank_column),
        }

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "baseline_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    frame.drop(columns=["acceptable"]).to_parquet(
        args.output / "per_query_results.parquet", index=False
    )
    frame.drop(columns=["acceptable"]).to_csv(
        args.output / "per_query_results.csv", index=False, encoding="utf-8-sig"
    )
    failures = frame[frame["rank_hybrid_policy"] > budget]
    with (args.output / "hybrid_policy_failures.jsonl").open("w", encoding="utf-8") as handle:
        for row in failures.to_dict("records"):
            row.pop("acceptable", None)
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    (args.output / "baseline_report.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    print(markdown_report(report), flush=True)
    print(f"wrote {report_path}", flush=True)


if __name__ == "__main__":
    main()
