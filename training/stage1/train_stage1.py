"""Train and evaluate E5 and Vietnamese encoders for Hanoi POI Stage 1.

The script is designed for a Kaggle script kernel but has a local
``--validate-only`` mode that never downloads a model or trains.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_REQUIRED_INPUTS = (
    "queries_10k.parquet",
    "corpus_search_view.parquet",
    "entity_resolution.parquet",
    "dataset_manifest.json",
    "generation_policy.json",
    "entity_policy.json",
    "validation_report.json",
)


def required_inputs(config: dict[str, Any]) -> tuple[str, ...]:
    configured = config.get("data", {}).get("required_files")
    if configured:
        return tuple(configured)
    return DEFAULT_REQUIRED_INPUTS


def local_model_input_names(config: dict[str, Any]) -> set[str]:
    return {
        item["source"]
        for model in config["models"]
        for item in model.get("local_model_files", [])
    }


def resolve_input_file(input_dir: Path, name: str) -> Path:
    direct = input_dir / name
    if direct.exists():
        return direct
    search_roots = [input_dir.parent]
    kaggle_root = Path("/kaggle/input")
    if kaggle_root.exists() and kaggle_root not in search_roots:
        search_roots.append(kaggle_root)
    for root in search_roots:
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return direct


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_input_dir(explicit: str | None, config: dict[str, Any]) -> Path:
    required = required_inputs(config)
    colocated = tuple(
        name for name in required if name not in local_model_input_names(config)
    )
    if explicit:
        candidate = Path(explicit)
        if all((candidate / name).exists() for name in colocated):
            return candidate
        raise FileNotFoundError(f"Input directory is incomplete: {candidate}")

    roots = [Path("/kaggle/input"), Path.cwd()]
    anchor = config.get("data", {}).get("anchor_file", required[0])
    for root in roots:
        if not root.exists():
            continue
        for anchor_file in root.rglob(anchor):
            candidate = anchor_file.parent
            if all((candidate / name).exists() for name in colocated):
                return candidate
    raise FileNotFoundError("Could not find a complete Stage 1 input directory")


def find_config(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit)
        if candidate.exists():
            return candidate
        raise FileNotFoundError(candidate)
    local = Path(__file__).with_name("config.json")
    if local.exists():
        return local
    for root in (Path("/kaggle/input"), Path.cwd()):
        if root.exists():
            matches = list(root.rglob("train_config.json"))
            if matches:
                return matches[0]
    raise FileNotFoundError("Could not find config.json or train_config.json")


def verify_inputs(input_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    manifest = read_json(input_dir / "dataset_manifest.json")
    manifest_files = manifest.get("files", {})
    if isinstance(manifest_files, list):
        manifest_files = {item["path"]: item for item in manifest_files}
    external_files = {
        item["source"]: item
        for model in config["models"]
        for item in model.get("local_model_files", [])
    }
    checks: dict[str, Any] = {
        "dataset_version": manifest.get("dataset_version")
        == config["dataset_version"],
        "corpus_version": manifest.get("corpus_version")
        == config["corpus_version"],
        "search_view_version": manifest.get("search_view_version")
        == config["search_view_version"],
        "files": {},
    }
    for name in required_inputs(config):
        path = resolve_input_file(input_dir, name)
        expected = manifest_files.get(name) or external_files.get(name)
        if name == "dataset_manifest.json":
            ok = path.exists()
        else:
            ok = bool(
                path.exists()
                and expected
                and path.stat().st_size == expected["bytes"]
                and sha256(path) == expected["sha256"]
            )
        checks["files"][name] = ok
    checks["passed"] = all(
        [
            checks["dataset_version"],
            checks["corpus_version"],
            checks["search_view_version"],
            *checks["files"].values(),
        ]
    )
    if not checks["passed"]:
        raise ValueError(f"Input verification failed: {checks}")
    return checks


def load_data(input_dir: Path, config: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    query_columns = [
        "query_id",
        "query",
        "case_type",
        "track",
        "query_surface",
        "intended_poi_id",
        "query_family_id",
        "known_compatible_poi_ids",
        "leakage_group_id",
        "category",
        "split",
        "supervised_training_eligible",
        "main_metric_candidate",
        "structured_metric_candidate",
        "dataset_version",
        "corpus_version",
        "search_view_version",
    ]
    corpus_columns = [
        "canonical_id",
        "search_label",
        "search_aliases",
        "address_fields_json",
        "category",
        "destination_searchable",
        "corpus_version",
        "search_view_version",
        "entity_group_id",
    ]
    data_config = config.get("data", {})

    def read_queries(name: str) -> list[dict[str, Any]]:
        schema_names = set(pq.read_schema(input_dir / name).names)
        missing = set(query_columns) - schema_names
        if missing:
            raise ValueError(f"Missing query columns in {name}: {sorted(missing)}")
        return pq.read_table(
            input_dir / name, columns=query_columns
        ).to_pylist()

    if data_config.get("mode") == "split_files":
        queries = []
        for name in (
            data_config["train_file"],
            data_config["dev_file"],
            data_config["test_file"],
        ):
            queries.extend(read_queries(name))
        overlay = {
            row["query_id"]: row
            for row in pq.read_table(
                input_dir / data_config["eligibility_file"]
            ).to_pylist()
        }
        overlay_fields = (
            "supervised_training_eligible",
            "main_metric_candidate",
            "structured_metric_candidate",
        )
        for row in queries:
            if row["query_id"] not in overlay:
                raise ValueError(f"Missing eligibility overlay for {row['query_id']}")
            for field in overlay_fields:
                row[field] = overlay[row["query_id"]][field]
    else:
        queries = read_queries(data_config.get("query_file", "queries_10k.parquet"))
    corpus = pq.read_table(
        input_dir / "corpus_search_view.parquet", columns=corpus_columns
    ).to_pylist()

    expected_loaded = data_config.get("expected_loaded_query_rows", 10_000)
    expected_corpus = data_config.get("expected_corpus_rows", 46_792)
    if len(queries) != expected_loaded:
        raise ValueError(f"Expected {expected_loaded} loaded queries, got {len(queries)}")
    if len(corpus) != expected_corpus:
        raise ValueError(f"Expected {expected_corpus} corpus rows, got {len(corpus)}")
    allowed_versions = set(
        config.get("record_source_versions", [config["dataset_version"]])
    )
    if any(row["dataset_version"] not in allowed_versions for row in queries):
        raise ValueError("Unexpected source dataset version in query rows")
    if any(row["corpus_version"] != config["corpus_version"] for row in queries):
        raise ValueError("Corpus version mismatch in query rows")
    if any(
        row["search_view_version"] != config["search_view_version"]
        for row in queries
    ):
        raise ValueError("Search-view version mismatch in query rows")

    destination_corpus = [row for row in corpus if row["destination_searchable"]]
    expected_destinations = data_config.get("expected_destination_rows", 45_693)
    if len(destination_corpus) != expected_destinations:
        raise ValueError(
            f"Expected {expected_destinations} searchable destinations, got {len(destination_corpus)}"
        )
    ids = {row["canonical_id"] for row in destination_corpus}
    if any(row["intended_poi_id"] not in ids for row in queries):
        raise ValueError("At least one query target is missing from the search corpus")
    return queries, destination_corpus


def normalized_key(text: str) -> str:
    return " ".join((text or "").casefold().split())


def build_passage(row: dict[str, Any], prefix: str) -> str:
    address = json.loads(row["address_fields_json"] or "{}")
    address_text = " ".join(
        str(address.get(key, "")).strip()
        for key in ("housenumber", "street", "subdistrict", "district")
        if str(address.get(key, "")).strip()
    )
    category = (row.get("category") or "").replace("=", " ").replace("_", " ")
    aliases = [str(value).strip() for value in row.get("search_aliases") or [] if str(value).strip()]

    parts: list[str] = []
    seen: set[str] = set()
    for value in [row["search_label"], address_text, category, *aliases]:
        value = " ".join(str(value).split()).strip(" ;")
        key = normalized_key(value)
        if value and key not in seen:
            parts.append(value)
            seen.add(key)
    return prefix + "; ".join(parts)


def prepare_training_views(
    queries: list[dict], corpus: list[dict], config: dict[str, Any]
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    corpus_by_id = {row["canonical_id"]: row for row in corpus}
    for row in queries:
        poi = corpus_by_id[row["intended_poi_id"]]
        row["entity_group_id"] = poi["entity_group_id"]

    train = [
        row
        for row in queries
        if row["split"] == "train"
        and row["supervised_training_eligible"]
        and row["query_surface"] == "committed_text"
        and row["track"] == "retrieval_core"
    ]
    dev = [
        row
        for row in queries
        if row["split"] == "dev_synthetic" and row["main_metric_candidate"]
    ]
    test = [
        row
        for row in queries
        if row["split"] == "test_synthetic" and row["main_metric_candidate"]
    ]
    diagnostics = [
        row
        for row in queries
        if row["track"] in {"autocomplete", "ambiguity_stress", "ime_keystream", "structured_code"}
    ]
    expected_counts = config.get("data", {}).get(
        "expected_training_views", {"train": 3_927, "dev": 438, "test": 391}
    )
    expected = tuple(expected_counts[name] for name in ("train", "dev", "test"))
    actual = (len(train), len(dev), len(test))
    if actual != expected:
        raise ValueError(f"Unexpected train/dev/test sizes: {actual}, expected {expected}")
    return train, dev, test, diagnostics


def make_unique_batches(
    rows: list[dict], batch_size: int, seed: int
) -> list[list[dict]]:
    pending = list(rows)
    random.Random(seed).shuffle(pending)
    batches: list[list[dict]] = []
    while pending:
        batch: list[dict] = []
        deferred: list[dict] = []
        target_ids: set[str] = set()
        entity_ids: set[str] = set()
        compatible_ids: set[str] = set()
        queries: set[str] = set()
        for row in pending:
            target = row["intended_poi_id"]
            entity = row["entity_group_id"]
            row_compatible = set(row.get("known_compatible_poi_ids") or [target])
            query_key = normalized_key(row["query"])
            conflict = (
                target in target_ids
                or entity in entity_ids
                or query_key in queries
                or bool(row_compatible & compatible_ids)
            )
            if len(batch) < batch_size and not conflict:
                batch.append(row)
                target_ids.add(target)
                entity_ids.add(entity)
                compatible_ids.update(row_compatible)
                queries.add(query_key)
            else:
                deferred.append(row)
        if not batch:
            raise RuntimeError("Unique batch sampler made no progress")
        batches.append(batch)
        pending = deferred
    if sum(map(len, batches)) != len(rows):
        raise RuntimeError("Unique batch sampler lost rows")
    return batches


def compatible_sets_are_disjoint(batch: list[dict]) -> bool:
    seen: set[str] = set()
    for row in batch:
        compatible = set(
            row.get("known_compatible_poi_ids") or [row["intended_poi_id"]]
        )
        if compatible & seen:
            return False
        seen.update(compatible)
    return True


def metric_summary(ranks: Iterable[int]) -> dict[str, float | int]:
    ranks = list(ranks)
    count = len(ranks)
    if not count:
        return {"count": 0}
    return {
        "count": count,
        "hit_1": sum(rank <= 1 for rank in ranks) / count,
        "hit_5": sum(rank <= 5 for rank in ranks) / count,
        "mrr_10": sum((1.0 / rank) if rank <= 10 else 0.0 for rank in ranks) / count,
        "candidate_hit_20": sum(rank <= 20 for rank in ranks) / count,
        "candidate_hit_50": sum(rank <= 50 for rank in ranks) / count,
        "mean_rank": float(np.mean(ranks)),
        "median_rank": float(np.median(ranks)),
    }


def exact_ranks(
    query_embeddings: np.ndarray,
    corpus_embeddings: np.ndarray,
    eval_rows: list[dict],
    corpus_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    corpus_index = {canonical_id: index for index, canonical_id in enumerate(corpus_ids)}
    scores = query_embeddings @ corpus_embeddings.T
    ranks: list[int] = []
    records: list[dict[str, Any]] = []
    for index, row in enumerate(eval_rows):
        target_index = corpus_index[row["intended_poi_id"]]
        target_score = scores[index, target_index]
        better = int(np.count_nonzero(scores[index] > target_score))
        ties_before = int(
            np.count_nonzero(scores[index, :target_index] == target_score)
        )
        rank = 1 + better + ties_before
        ranks.append(rank)
        records.append(
            {
                "query_id": row["query_id"],
                "query_family_id": row["query_family_id"],
                "case_type": row["case_type"],
                "category": row["category"],
                "target_id": row["intended_poi_id"],
                "rank": rank,
                "target_score": float(target_score),
            }
        )

    by_case: dict[str, Any] = {}
    for case_type in sorted({row["case_type"] for row in eval_rows}):
        case_ranks = [
            record["rank"]
            for row, record in zip(eval_rows, records)
            if row["case_type"] == case_type
        ]
        by_case[case_type] = metric_summary(case_ranks)
    return {"overall": metric_summary(ranks), "by_case": by_case}, records


def quantiles(values: list[int]) -> dict[str, int]:
    array = np.asarray(values)
    return {
        name: int(np.quantile(array, value, method="nearest"))
        for name, value in (("min", 0.0), ("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1.0))
    }


def ensure_training_dependencies() -> None:
    required_transformers = "4.57.6"
    try:
        installed = importlib.metadata.version("transformers")
    except importlib.metadata.PackageNotFoundError:
        installed = None
    if installed != required_transformers:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                f"transformers=={required_transformers}",
                "sentencepiece==0.2.1",
                "safetensors>=0.6,<0.7",
            ]
        )

    probe = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-c",
                (
                    "import json,torch; "
                    "cap=torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None; "
                    "print(json.dumps({'cuda':torch.version.cuda,'capability':cap,"
                    "'arch_list':torch.cuda.get_arch_list() if torch.cuda.is_available() else []}))"
                ),
            ],
            text=True,
        )
    )
    if probe["capability"]:
        wanted_arch = f"sm_{probe['capability'][0]}{probe['capability'][1]}"
        if wanted_arch not in probe["arch_list"]:
            print(
                "Installing the official PyTorch CUDA 12.6 wheel because the "
                f"current build does not contain {wanted_arch}: {probe}"
            )
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--force-reinstall",
                    "torch==2.11.0+cu126",
                    "--index-url",
                    "https://download.pytorch.org/whl/cu126",
                ]
            )
            verified = json.loads(
                subprocess.check_output(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import json,torch; cap=torch.cuda.get_device_capability(0); "
                            "print(json.dumps({'cuda':torch.version.cuda,'capability':cap,"
                            "'arch_list':torch.cuda.get_arch_list()}))"
                        ),
                    ],
                    text=True,
                )
            )
            if wanted_arch not in verified["arch_list"]:
                raise RuntimeError(
                    f"Installed PyTorch still lacks {wanted_arch}: {verified}"
                )


def token_lengths(tokenizer: Any, texts: list[str], batch_size: int = 1024) -> list[int]:
    lengths: list[int] = []
    for start in range(0, len(texts), batch_size):
        encoded = tokenizer(
            texts[start : start + batch_size],
            add_special_tokens=True,
            padding=False,
            truncation=False,
        )
        lengths.extend(len(input_ids) for input_ids in encoded["input_ids"])
    return lengths


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def model_embeddings(model: Any, encoded: dict[str, Any]) -> Any:
    import torch.nn.functional as functional

    outputs = model(**encoded)
    return functional.normalize(
        mean_pool(outputs.last_hidden_state, encoded["attention_mask"]), p=2, dim=1
    )


def encode_texts(
    model: Any,
    tokenizer: Any,
    texts: list[str],
    max_length: int,
    batch_size: int,
    device: Any,
) -> np.ndarray:
    import torch

    model.eval()
    output: list[np.ndarray] = []
    use_amp = device.type == "cuda"
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            encoded = tokenizer(
                texts[start : start + batch_size],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=use_amp,
            ):
                embeddings = model_embeddings(model, encoded)
            output.append(embeddings.float().cpu().numpy())
    return np.concatenate(output, axis=0).astype(np.float32, copy=False)


def evaluate_model(
    model: Any,
    tokenizer: Any,
    corpus_texts: list[str],
    corpus_ids: list[str],
    eval_rows: list[dict],
    config: dict[str, Any],
    device: Any,
) -> tuple[dict[str, Any], list[dict], np.ndarray]:
    corpus_embeddings = encode_texts(
        model,
        tokenizer,
        corpus_texts,
        config["max_passage_tokens"],
        config["encode_batch_size"],
        device,
    )
    queries = [config["query_prefix"] + row["query"] for row in eval_rows]
    query_embeddings = encode_texts(
        model,
        tokenizer,
        queries,
        config["max_query_tokens"],
        config["encode_batch_size"],
        device,
    )
    metrics, records = exact_ranks(
        query_embeddings, corpus_embeddings, eval_rows, corpus_ids
    )
    return metrics, records, corpus_embeddings


def guardrail_passes(
    baseline: dict[str, Any], candidate: dict[str, Any], config: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {}
    passed = True
    for case_type in config["guardrail_cases"]:
        base = baseline["by_case"].get(case_type, {"count": 0})
        cand = candidate["by_case"].get(case_type, {"count": 0})
        if not base.get("count") or not cand.get("count"):
            details[case_type] = {"status": "not_applicable"}
            continue
        drop = float(base["hit_1"] - cand["hit_1"])
        case_pass = drop <= config["guardrail_hit1_max_drop"]
        details[case_type] = {"hit1_drop": drop, "passed": case_pass}
        passed &= case_pass
    return passed, details


def selection_key(metrics: dict[str, Any], config: dict[str, Any]) -> tuple[float, ...]:
    overall = metrics["overall"]
    return tuple(float(overall[name]) for name in config["selection_metrics"])


def save_rank_records(path: Path, records: list[dict], run_name: str, split: str) -> None:
    enriched = [{**row, "run_name": run_name, "split": split} for row in records]
    pq.write_table(pa.Table.from_pylist(enriched), path, compression="zstd")


def flatten_metrics(
    metrics: dict[str, Any], run_name: str, split: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slice_name, values in [("overall", metrics["overall"]), *metrics["by_case"].items()]:
        rows.append({"run_name": run_name, "split": split, "slice": slice_name, **values})
    return rows


def model_card_text(
    config: dict[str, Any], selected: dict[str, Any], selection: dict[str, Any]
) -> str:
    dev = selection["dev_metrics"]["overall"]
    test = selection["test_metrics"]["overall"]
    model = selected["model"]
    return f"""# Hanoi POI Stage 1 dense retriever

Selected run: `{selected['name']}`  
Base model: `{model['model_id']}` at revision `{model['model_revision']}`  
Dataset: `{config['dataset_version']}`; corpus: `{config['corpus_version']}`; search view: `{config['search_view_version']}`

## Evaluation

Selection used only `dev_synthetic`; `test_synthetic` was evaluated after selection. Exact ranking covers all 45,693 destination-searchable POIs.

| Split | Hit@1 | Hit@5 | MRR@10 | CandidateHit@20 | CandidateHit@50 |
|---|---:|---:|---:|---:|---:|
| dev | {dev['hit_1']:.4f} | {dev['hit_5']:.4f} | {dev['mrr_10']:.4f} | {dev['candidate_hit_20']:.4f} | {dev['candidate_hit_50']:.4f} |
| test | {test['hit_1']:.4f} | {test['hit_5']:.4f} | {test['mrr_10']:.4f} | {test['candidate_hit_20']:.4f} | {test['candidate_hit_50']:.4f} |

## Intended use and limitations

This is a demo candidate generator for Hanoi POI search, not a production geocoder. Training and held-out labels are synthetic weak labels derived from OSM POIs. The test split is synthetic, `structured_code` has only 10 metric cases, IME strings were not verified against a real mobile keyboard engine, and pickup routing points are not included. Stage 2 spatial/contextual reranking and a manually reviewed benchmark are still required before deployment. Review the selected base model license before commercial use.
"""


def resolve_model_source(
    model_config: dict[str, Any], input_dir: Path, output_dir: Path
) -> tuple[str, str | None]:
    local_files = model_config.get("local_model_files", [])
    if not local_files:
        return model_config["model_id"], model_config.get("model_revision")
    materialization_root = (
        Path("/tmp/stage1_input_models")
        if Path("/kaggle").exists()
        else output_dir / "resolved_input_models"
    )
    target_dir = materialization_root / model_config["key"]
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in local_files:
        source = resolve_input_file(input_dir, item["source"])
        target = target_dir / item["target"]
        if not target.exists() or sha256(target) != item["sha256"]:
            shutil.copy2(source, target)
    return str(target_dir), None


def run_training(
    input_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
    train_rows: list[dict],
    dev_rows: list[dict],
    test_rows: list[dict],
    corpus: list[dict],
) -> None:
    ensure_training_dependencies()
    import torch
    import torch.nn.functional as functional
    import transformers
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

    seed_everything(config["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Training mode requires a CUDA GPU")

    output_dir.mkdir(parents=True, exist_ok=True)
    ranks_dir = output_dir / "per_query_runs"
    ranks_dir.mkdir(parents=True, exist_ok=True)
    corpus_ids = [row["canonical_id"] for row in corpus]
    print(f"device={device} corpus={len(corpus)} train={len(train_rows)} dev={len(dev_rows)}")
    candidates: list[dict[str, Any]] = []
    training_runs: list[dict[str, Any]] = []
    baselines: dict[str, dict[str, Any]] = {}
    metric_rows: list[dict[str, Any]] = []
    global_run_index = 0

    for model_config in config["models"]:
        model_key = model_config["key"]
        model_eval_config = {**config, **model_config}
        resolved_model_id, resolved_revision = resolve_model_source(
            model_config, input_dir, output_dir
        )
        corpus_texts = [
            build_passage(row, model_config["passage_prefix"]) for row in corpus
        ]
        corpus_text_by_id = dict(zip(corpus_ids, corpus_texts))
        tokenizer = AutoTokenizer.from_pretrained(
            resolved_model_id, revision=resolved_revision
        )
        query_texts = [
            model_config["query_prefix"] + row["query"]
            for row in train_rows + dev_rows + test_rows
        ]
        query_lengths = token_lengths(tokenizer, query_texts)
        passage_lengths = token_lengths(tokenizer, corpus_texts)
        write_json(
            output_dir / f"token_length_audit_{model_key}.json",
            {
                "model": model_config,
                "query_tokens": quantiles(query_lengths),
                "passage_tokens": quantiles(passage_lengths),
                "query_truncated": sum(
                    length > config["max_query_tokens"] for length in query_lengths
                ),
                "passage_truncated": sum(
                    length > config["max_passage_tokens"] for length in passage_lengths
                ),
            },
        )

        baseline_name = model_config.get(
            "baseline_name", f"D0_{model_key}_zero_shot"
        )
        base_model = AutoModel.from_pretrained(
            resolved_model_id, revision=resolved_revision
        ).to(device)
        baseline_metrics, baseline_records, _ = evaluate_model(
            base_model,
            tokenizer,
            corpus_texts,
            corpus_ids,
            dev_rows,
            model_eval_config,
            device,
        )
        write_json(
            output_dir / f"zero_shot_dev_metrics_{model_key}.json", baseline_metrics
        )
        save_rank_records(
            ranks_dir / f"{baseline_name}_dev.parquet",
            baseline_records,
            baseline_name,
            "dev",
        )
        metric_rows.extend(flatten_metrics(baseline_metrics, baseline_name, "dev"))
        baselines[model_key] = baseline_metrics
        candidates.append(
            {
                "name": baseline_name,
                "metrics": baseline_metrics,
                "model_path": None,
                "model": model_config,
                "resolved_model_id": resolved_model_id,
                "resolved_revision": resolved_revision,
                "guardrail_passed": True,
                "guardrail_details": {},
            }
        )
        print(baseline_name, baseline_metrics["overall"])
        del base_model
        torch.cuda.empty_cache()

        for run in model_config["runs"]:
            global_run_index += 1
            run_seed = config["seed"] + global_run_index
            seed_everything(run_seed)
            model = AutoModel.from_pretrained(
                resolved_model_id, revision=resolved_revision
            ).to(device)
            optimizer = torch.optim.AdamW(
                model.parameters(),
                lr=run["learning_rate"],
                weight_decay=config["weight_decay"],
            )
            run_epochs = run.get("epochs", config["epochs"])
            epoch_batches = [
                make_unique_batches(
                    train_rows, config["train_batch_size"], run_seed + epoch
                )
                for epoch in range(run_epochs)
            ]
            total_steps = sum(len(batches) for batches in epoch_batches)
            warmup_steps = int(math.ceil(total_steps * config["warmup_ratio"]))
            scheduler = get_linear_schedule_with_warmup(
                optimizer,
                num_warmup_steps=warmup_steps,
                num_training_steps=total_steps,
            )
            scaler = torch.amp.GradScaler("cuda", enabled=True)
            best: dict[str, Any] | None = None
            run_history: list[dict[str, Any]] = []
            run_dir = output_dir / "checkpoints" / run["name"]

            for epoch, batches in enumerate(epoch_batches, start=1):
                model.train()
                losses: list[float] = []
                started = time.time()
                for batch in batches:
                    query_inputs = tokenizer(
                        [model_config["query_prefix"] + row["query"] for row in batch],
                        padding=True,
                        truncation=True,
                        max_length=config["max_query_tokens"],
                        return_tensors="pt",
                    )
                    passage_inputs = tokenizer(
                        [corpus_text_by_id[row["intended_poi_id"]] for row in batch],
                        padding=True,
                        truncation=True,
                        max_length=config["max_passage_tokens"],
                        return_tensors="pt",
                    )
                    query_inputs = {
                        key: value.to(device) for key, value in query_inputs.items()
                    }
                    passage_inputs = {
                        key: value.to(device) for key, value in passage_inputs.items()
                    }
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast(device_type="cuda", dtype=torch.float16):
                        query_embeddings = model_embeddings(model, query_inputs)
                        passage_embeddings = model_embeddings(model, passage_inputs)
                        logits = (
                            query_embeddings @ passage_embeddings.T
                        ) * config["temperature_scale"]
                        labels = torch.arange(len(batch), device=device)
                        loss = functional.cross_entropy(logits, labels)
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), config["max_grad_norm"]
                    )
                    scale_before_step = scaler.get_scale()
                    scaler.step(optimizer)
                    scaler.update()
                    if scaler.get_scale() >= scale_before_step:
                        scheduler.step()
                    losses.append(float(loss.detach().cpu()))

                dev_metrics, dev_records, _ = evaluate_model(
                    model,
                    tokenizer,
                    corpus_texts,
                    corpus_ids,
                    dev_rows,
                    model_eval_config,
                    device,
                )
                guardrail, guardrail_details = guardrail_passes(
                    baseline_metrics, dev_metrics, config
                )
                epoch_name = f"{run['name']}_epoch{epoch}"
                save_rank_records(
                    ranks_dir / f"{epoch_name}_dev.parquet",
                    dev_records,
                    epoch_name,
                    "dev",
                )
                metric_rows.extend(flatten_metrics(dev_metrics, epoch_name, "dev"))
                record = {
                    "epoch": epoch,
                    "mean_train_loss": float(np.mean(losses)),
                    "steps": len(batches),
                    "elapsed_seconds": time.time() - started,
                    "metrics": dev_metrics,
                    "guardrail_passed": guardrail,
                    "guardrail_details": guardrail_details,
                }
                run_history.append(record)
                print(
                    epoch_name,
                    record["mean_train_loss"],
                    dev_metrics["overall"],
                    guardrail,
                )

                if guardrail and (
                    best is None
                    or selection_key(dev_metrics, config)
                    > selection_key(best["metrics"], config)
                ):
                    if run_dir.exists():
                        shutil.rmtree(run_dir)
                    model.save_pretrained(run_dir, safe_serialization=True)
                    tokenizer.save_pretrained(run_dir)
                    best = {
                        "name": epoch_name,
                        "metrics": dev_metrics,
                        "model_path": str(run_dir),
                        "model": model_config,
                        "resolved_model_id": str(run_dir),
                        "resolved_revision": None,
                        "guardrail_passed": True,
                        "guardrail_details": guardrail_details,
                    }

            training_runs.append(
                {
                    "model": model_config,
                    "run": run,
                    "seed": run_seed,
                    "history": run_history,
                    "best": best,
                }
            )
            if best is not None:
                candidates.append(best)
            del model
            torch.cuda.empty_cache()

    reference_key = config.get("global_guardrail_baseline_key")
    if reference_key:
        if reference_key not in baselines:
            raise ValueError(f"Unknown global guardrail baseline: {reference_key}")
        for candidate in candidates:
            passed, details = guardrail_passes(
                baselines[reference_key], candidate["metrics"], config
            )
            candidate["guardrail_passed"] = passed
            candidate["guardrail_details"] = details

    selected = max(
        [candidate for candidate in candidates if candidate["guardrail_passed"]],
        key=lambda candidate: selection_key(candidate["metrics"], config),
    )
    selected_model_config = selected["model"]
    selected_eval_config = {**config, **selected_model_config}
    final_dir = output_dir / "final_model"
    if final_dir.exists():
        shutil.rmtree(final_dir)
    if selected["model_path"]:
        shutil.copytree(selected["model_path"], final_dir)
    else:
        base_model = AutoModel.from_pretrained(
            selected["resolved_model_id"],
            revision=selected["resolved_revision"],
        )
        base_tokenizer = AutoTokenizer.from_pretrained(
            selected["resolved_model_id"],
            revision=selected["resolved_revision"],
        )
        base_model.save_pretrained(final_dir, safe_serialization=True)
        base_tokenizer.save_pretrained(final_dir)
        del base_model

    selected_corpus_texts = [
        build_passage(row, selected_model_config["passage_prefix"]) for row in corpus
    ]
    final_tokenizer = AutoTokenizer.from_pretrained(final_dir)
    final_model = AutoModel.from_pretrained(final_dir).to(device)
    final_dev_metrics, final_dev_records, final_corpus_embeddings = evaluate_model(
        final_model,
        final_tokenizer,
        selected_corpus_texts,
        corpus_ids,
        dev_rows,
        selected_eval_config,
        device,
    )
    final_test_metrics, final_test_records, _ = evaluate_model(
        final_model,
        final_tokenizer,
        selected_corpus_texts,
        corpus_ids,
        test_rows,
        selected_eval_config,
        device,
    )
    save_rank_records(
        ranks_dir / "selected_dev.parquet", final_dev_records, selected["name"], "dev"
    )
    save_rank_records(
        ranks_dir / "selected_test.parquet", final_test_records, selected["name"], "test"
    )
    metric_rows.extend(flatten_metrics(final_dev_metrics, selected["name"], "selected_dev"))
    metric_rows.extend(flatten_metrics(final_test_metrics, selected["name"], "test"))
    np.save(output_dir / "corpus_embeddings.npy", final_corpus_embeddings)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"row_index": index, "canonical_id": canonical_id}
                for index, canonical_id in enumerate(corpus_ids)
            ]
        ),
        output_dir / "corpus_id_map.parquet",
        compression="zstd",
    )

    zero_shot_test_metrics: dict[str, Any] = {}
    for model_config in config["models"]:
        model_key = model_config["key"]
        baseline_name = model_config.get(
            "baseline_name", f"D0_{model_key}_zero_shot"
        )
        baseline_eval_config = {**config, **model_config}
        resolved_model_id, resolved_revision = resolve_model_source(
            model_config, input_dir, output_dir
        )
        baseline_corpus_texts = [
            build_passage(row, model_config["passage_prefix"]) for row in corpus
        ]
        baseline_tokenizer = AutoTokenizer.from_pretrained(
            resolved_model_id, revision=resolved_revision
        )
        base_model = AutoModel.from_pretrained(
            resolved_model_id, revision=resolved_revision
        ).to(device)
        baseline_test_metrics, baseline_test_records, _ = evaluate_model(
            base_model,
            baseline_tokenizer,
            baseline_corpus_texts,
            corpus_ids,
            test_rows,
            baseline_eval_config,
            device,
        )
        zero_shot_test_metrics[model_key] = baseline_test_metrics
        metric_rows.extend(
            flatten_metrics(baseline_test_metrics, baseline_name, "test")
        )
        save_rank_records(
            ranks_dir / f"{baseline_name}_test.parquet",
            baseline_test_records,
            baseline_name,
            "test",
        )
        del base_model
        torch.cuda.empty_cache()

    selection = {
        "selected": selected["name"],
        "selected_model": selected_model_config,
        "selection_metrics": config["selection_metrics"],
        "dev_metrics": final_dev_metrics,
        "test_metrics": final_test_metrics,
        "zero_shot_dev_metrics": baselines,
        "zero_shot_test_metrics": zero_shot_test_metrics,
        "candidates": [
            {
                "name": candidate["name"],
                "model_key": candidate["model"]["key"],
                "metrics": candidate["metrics"],
                "guardrail_passed": candidate["guardrail_passed"],
                "guardrail_details": candidate["guardrail_details"],
            }
            for candidate in candidates
        ],
    }
    write_json(output_dir / "training_runs.json", training_runs)
    write_json(output_dir / "model_selection.json", selection)
    pq.write_table(
        pa.Table.from_pylist(metric_rows),
        output_dir / "metrics_by_slice.parquet",
        compression="zstd",
    )
    write_json(
        output_dir / "inference_config.json",
        {
            "query_prefix": selected_model_config["query_prefix"],
            "passage_prefix": selected_model_config["passage_prefix"],
            "max_query_tokens": config["max_query_tokens"],
            "max_passage_tokens": config["max_passage_tokens"],
            "pooling": "attention_mask_mean",
            "normalize": True,
            "similarity": "dot_product_of_l2_normalized_vectors",
        },
    )
    write_json(
        output_dir / "final_model_manifest.json",
        {
            "selected_run": selected["name"],
            "base_model_id": selected_model_config["model_id"],
            "base_model_revision": selected_model_config["model_revision"],
            "dataset_version": config["dataset_version"],
            "corpus_version": config["corpus_version"],
            "search_view_version": config["search_view_version"],
            "embedding_dimension": int(final_corpus_embeddings.shape[1]),
            "corpus_rows": int(final_corpus_embeddings.shape[0]),
            "model_files": {
                str(path.relative_to(final_dir)): sha256(path)
                for path in sorted(final_dir.rglob("*"))
                if path.is_file()
            },
        },
    )
    (output_dir / "environment.txt").write_text(
        "\n".join(
            [
                f"python={platform.python_version()}",
                f"platform={platform.platform()}",
                f"torch={torch.__version__}",
                f"transformers={transformers.__version__}",
                f"numpy={np.__version__}",
                f"pyarrow={pa.__version__}",
                f"cuda={torch.version.cuda}",
                f"gpu={torch.cuda.get_device_name(0)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        output_dir / "passage_manifest.json",
        {
            "builder_version": "passage-v1",
            "fields": ["search_label", "address", "category", "search_aliases"],
            "prefix": selected_model_config["passage_prefix"],
            "rows": len(selected_corpus_texts),
            "sha256": hashlib.sha256(
                "\n".join(selected_corpus_texts).encode("utf-8")
            ).hexdigest(),
        },
    )
    (output_dir / "MODEL_CARD.md").write_text(
        model_card_text(config, selected, selection), encoding="utf-8"
    )
    print("SELECTED", selected["name"], selection["test_metrics"]["overall"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir")
    parser.add_argument("--config")
    parser.add_argument("--output-dir", default="/kaggle/working/stage1_outputs")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    config_path = find_config(args.config)
    config = read_json(config_path)
    model_keys = [model["key"] for model in config["models"]]
    if len(model_keys) != len(set(model_keys)) or not model_keys:
        raise ValueError("Config must contain models with unique non-empty keys")
    input_dir = find_input_dir(args.input_dir, config)
    output_dir = Path(args.output_dir)
    verification = verify_inputs(input_dir, config)
    queries, corpus = load_data(input_dir, config)
    train_rows, dev_rows, test_rows, diagnostics = prepare_training_views(
        queries, corpus, config
    )
    batches = make_unique_batches(
        train_rows, config["train_batch_size"], config["seed"]
    )
    preflight = {
        "passed": True,
        "input_dir": str(input_dir),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "training_script_sha256": sha256(Path(__file__)),
        "verification": verification,
        "queries": len(queries),
        "corpus": len(corpus),
        "train": len(train_rows),
        "dev": len(dev_rows),
        "test": len(test_rows),
        "diagnostics": len(diagnostics),
        "batches": len(batches),
        "batch_size_min": min(map(len, batches)),
        "batch_size_max": max(map(len, batches)),
        "unique_target_batches": all(
            len({row["intended_poi_id"] for row in batch}) == len(batch)
            for batch in batches
        ),
        "unique_entity_batches": all(
            len({row["entity_group_id"] for row in batch}) == len(batch)
            for batch in batches
        ),
        "disjoint_known_compatible_batches": all(
            compatible_sets_are_disjoint(batch) for batch in batches
        ),
    }
    if args.validate_only:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "input_manifest_verified.json", preflight)
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return

    write_json(output_dir / "config_resolved.json", config)
    write_json(output_dir / "input_manifest_verified.json", preflight)
    run_training(
        input_dir,
        output_dir,
        config,
        train_rows,
        dev_rows,
        test_rows,
        corpus,
    )


if __name__ == "__main__":
    main()
