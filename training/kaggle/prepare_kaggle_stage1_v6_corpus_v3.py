#!/usr/bin/env python3
"""Pack Stage-1 v6 train + corpus v3 + gold v2 for a Kaggle fine-tune.

Does not copy embeddings. The kernel encodes passages/queries on GPU.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TRAIN = ROOT / "data" / "vietnam" / "train_stage1_queries_v6"
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1_corpus_v2"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v3"
DATA_DIR = HERE / "dataset_stage1_v6_corpus_v3"
KERNEL_DIR = HERE / "kernel_stage1_v6_e5_finetune"

EXCLUDED_CASES = {
    "train20k-02003": (
        "intended osm:node/5608881031 was merge_duplicate into "
        "osm:node/5608880680 (PNJ Phường Bình Thới); query identity is "
        "PNJ Hòa Bình. Do not train the wrong branch."
    )
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ids(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def remap_id(poi_id: str, corpus_ids: set[str], migration: dict[str, tuple[str, str]]) -> tuple[str | None, str]:
    if poi_id in corpus_ids:
        return poi_id, "keep"
    mapped = migration.get(poi_id)
    if mapped and mapped[0] in corpus_ids:
        return mapped[0], mapped[1]
    return None, "unresolved"


def main() -> None:
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]

    required = [
        TRAIN / "query_variants.csv",
        TRAIN / "manifest.json",
        GOLD / "query_variants.csv",
        GOLD / "target_pois.csv",
        GOLD / "qrels_policy.json",
        GOLD / "manifest.json",
        CORPUS / "search_documents.parquet",
        CORPUS / "pois_core.parquet",
        CORPUS / "poi_id_migration.parquet",
        CORPUS / "manifest.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(CORPUS / "search_documents.parquet", columns=["poi_id", "passage_context"])
    core = pd.read_parquet(
        CORPUS / "pois_core.parquet",
        columns=["poi_id", "entity_group_id", "name"],
    )
    migration_table = pd.read_parquet(
        CORPUS / "poi_id_migration.parquet",
        columns=["old_poi_id", "canonical_poi_id", "action"],
    )
    corpus_ids = set(docs["poi_id"].astype(str))
    migration = {
        str(row.old_poi_id): (str(row.canonical_poi_id), str(row.action))
        for row in migration_table.itertuples(index=False)
    }
    entity_by_id = dict(zip(core["poi_id"].astype(str), core["entity_group_id"].astype(str)))

    train = pd.read_csv(TRAIN / "query_variants.csv")
    remap_events: list[dict[str, str]] = []
    kept_rows: list[dict[str, object]] = []
    excluded_rows = 0

    for row in train.to_dict("records"):
        case_id = str(row["case_id"])
        if case_id in EXCLUDED_CASES:
            excluded_rows += 1
            continue
        source_intended = str(row["intended_poi_id"])
        intended, intended_action = remap_id(source_intended, corpus_ids, migration)
        if intended is None:
            raise SystemExit(f"Unresolved intended {source_intended} on {row['variant_id']}")
        if intended != source_intended:
            remap_events.append(
                {
                    "variant_id": str(row["variant_id"]),
                    "field": "intended_poi_id",
                    "source": source_intended,
                    "canonical": intended,
                    "action": intended_action,
                }
            )
        acceptable: list[str] = []
        for poi_id in parse_ids(row["acceptable_poi_ids"]):
            mapped, action = remap_id(poi_id, corpus_ids, migration)
            if mapped is None:
                remap_events.append(
                    {
                        "variant_id": str(row["variant_id"]),
                        "field": "acceptable_poi_ids",
                        "source": poi_id,
                        "canonical": "",
                        "action": action,
                    }
                )
                continue
            if mapped not in acceptable:
                acceptable.append(mapped)
            if mapped != poi_id:
                remap_events.append(
                    {
                        "variant_id": str(row["variant_id"]),
                        "field": "acceptable_poi_ids",
                        "source": poi_id,
                        "canonical": mapped,
                        "action": action,
                    }
                )
        if intended not in acceptable:
            acceptable.insert(0, intended)
        entity_id = entity_by_id.get(intended)
        if not entity_id:
            raise SystemExit(f"Missing entity_group_id for {intended}")
        kept_rows.append(
            {
                "case_id": case_id,
                "variant_id": str(row["variant_id"]),
                "query_text": str(row["query_text"]),
                "canonical_query": str(row["canonical_query"]),
                "query_variant_family": str(row["query_variant_family"]),
                "variant_operator": str(row["variant_operator"]),
                "primary_sampling_stratum": str(row["primary_sampling_stratum"]),
                "intended_poi_id": intended,
                "intended_poi_id_source": source_intended,
                "acceptable_poi_ids": json.dumps(acceptable, ensure_ascii=False),
                "n_acceptable": len(acceptable),
                "entity_group_id": entity_id,
                "review_status": str(row["review_status"]),
            }
        )

    train_out = pd.DataFrame(kept_rows)
    gold = pd.read_csv(GOLD / "query_variants.csv")
    gold_ids: set[str] = set()
    for raw in gold["acceptable_poi_ids"]:
        gold_ids.update(parse_ids(raw))
    gold_ids.update(gold["intended_poi_id"].astype(str))
    missing_gold = sorted(gold_ids - corpus_ids)
    if missing_gold:
        raise SystemExit(f"Gold v2 IDs missing from corpus v3: {missing_gold[:10]}")

    train_ids = set(train_out["intended_poi_id"].astype(str))
    for raw in train_out["acceptable_poi_ids"]:
        train_ids.update(parse_ids(raw))
    overlap = sorted(train_ids & gold_ids)
    if overlap:
        raise SystemExit(f"Train/gold ID overlap after remap: {overlap[:10]}")

    slim_docs = docs.loc[:, ["poi_id", "passage_context"]].copy()
    slim_docs["poi_id"] = slim_docs["poi_id"].astype(str)
    pq.write_table(
        pa.Table.from_pandas(slim_docs, preserve_index=False),
        DATA_DIR / "search_documents.parquet",
        compression="zstd",
    )
    train_out.to_csv(DATA_DIR / "query_variants_train.csv", index=False, encoding="utf-8")
    shutil.copy2(GOLD / "query_variants.csv", DATA_DIR / "gold_query_variants.csv")
    shutil.copy2(GOLD / "target_pois.csv", DATA_DIR / "gold_target_pois.csv")
    shutil.copy2(GOLD / "qrels_policy.json", DATA_DIR / "gold_qrels_policy.json")
    shutil.copy2(GOLD / "manifest.json", DATA_DIR / "gold_manifest.json")
    shutil.copy2(CORPUS / "manifest.json", DATA_DIR / "corpus_manifest.json")
    shutil.copy2(TRAIN / "manifest.json", DATA_DIR / "train_source_manifest.json")

    config = {
        "experiment": "stage1_v6_partial_e5_inbatch_pilot",
        "dataset_version": "train_stage1_queries_v6_partial_2499_corpus_v3",
        "corpus_version": "vn-poi-core-v3-semantic-address-dedup50",
        "gold_dataset": "gold_stage1_v1_corpus_v2",
        "model_id": "intfloat/multilingual-e5-small",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "max_query_tokens": 64,
        "max_passage_tokens": 128,
        "train_batch_size": 32,
        "epochs": 3,
        "learning_rate": 2e-5,
        "weight_decay": 0.01,
        "warmup_ratio": 0.06,
        "max_grad_norm": 1.0,
        "temperature_scale": 20.0,
        "seed": 42,
        "dev_case_fraction": 0.1,
        "eval_depth": 1000,
        "encode_batch_size": 48,
        "note": (
            "Pilot in-batch unique-target contrastive on authored v6 rows. "
            "No mined hard negatives, no prefix expansion, no brand-only track. "
            "Gold v2 is frozen comparison, not a tuning split."
        ),
    }
    (DATA_DIR / "train_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    pack_files = [
        "search_documents.parquet",
        "query_variants_train.csv",
        "gold_query_variants.csv",
        "gold_target_pois.csv",
        "gold_qrels_policy.json",
        "gold_manifest.json",
        "corpus_manifest.json",
        "train_source_manifest.json",
        "train_config.json",
    ]
    manifest = {
        "dataset": "vn-poi-stage1-v6-corpus-v3",
        "status": "pilot_pack",
        "uploads_embeddings": False,
        "corpus_version": config["corpus_version"],
        "gold_dataset": config["gold_dataset"],
        "train_cases": int(train_out["case_id"].nunique()),
        "train_rows": int(len(train_out)),
        "excluded_cases": EXCLUDED_CASES,
        "excluded_rows": excluded_rows,
        "gold_rows": int(len(gold)),
        "corpus_rows": int(len(slim_docs)),
        "remap_events": len(remap_events),
        "files": {
            name: {"bytes": (DATA_DIR / name).stat().st_size, "sha256": sha256(DATA_DIR / name)}
            for name in pack_files
        },
    }
    (DATA_DIR / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DATA_DIR / "id_remap_report.json").write_text(
        json.dumps(
            {
                "excluded_cases": EXCLUDED_CASES,
                "events": remap_events,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    data_ref = f"{username}/vn-poi-stage1-v6-corpus-v3"
    kernel_ref = f"{username}/vn-poi-stage1-v6-e5-finetune"
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Stage1 v6 corpus v3",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "v6 train + corpus v3 passages + gold v2, no embeddings",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "vn-poi-stage1-v6-e5-finetune",
                "code_file": "run_train_stage1_v6.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [data_ref],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "data_dir": str(DATA_DIR),
                "kernel_dir": str(KERNEL_DIR),
                "data_ref": data_ref,
                "kernel_ref": kernel_ref,
                "train_cases": manifest["train_cases"],
                "train_rows": manifest["train_rows"],
                "excluded_rows": excluded_rows,
                "remap_events": len(remap_events),
                "corpus_rows": manifest["corpus_rows"],
                "next": [
                    f"python -m kaggle datasets create -p {DATA_DIR} --dir-mode zip",
                    f"python -m kaggle kernels push -p {KERNEL_DIR}",
                    f"python -m kaggle kernels status {kernel_ref}",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
