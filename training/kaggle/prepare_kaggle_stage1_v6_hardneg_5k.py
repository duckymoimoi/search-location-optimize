#!/usr/bin/env python3
"""Pack the isolated v6 5k hard-negative experiment for a new Kaggle kernel.

Does not modify 4k/2.5k hardneg, in-batch kernel, or published v6 CSV.
Does not upload embeddings.
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
PILOT = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_5k"
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1_corpus_v2"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v3"
DATA_DIR = HERE / "dataset_stage1_v6_hardneg_5k"
KERNEL_DIR = HERE / "kernel_stage1_v6_hardneg_5k"
SRC_KERNEL = HERE / "kernel_stage1_v6_hardneg_pilot" / "run_train_stage1_v6_hardneg.py"


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


def main() -> None:
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]

    required = [
        PILOT / "query_train_view.parquet",
        PILOT / "query_relation_view.parquet",
        PILOT / "training_pairs.parquet",
        PILOT / "manifest.json",
        PILOT / "mining_manifest.json",
        GOLD / "query_variants.csv",
        GOLD / "target_pois.csv",
        GOLD / "qrels_policy.json",
        GOLD / "manifest.json",
        CORPUS / "search_documents.parquet",
        CORPUS / "manifest.json",
        SRC_KERNEL,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(CORPUS / "search_documents.parquet", columns=["poi_id", "passage_context"])
    view = pd.read_parquet(PILOT / "query_train_view.parquet")
    pairs = pd.read_parquet(PILOT / "training_pairs.parquet")
    gold = pd.read_csv(GOLD / "query_variants.csv")

    corpus_ids = set(docs["poi_id"].astype(str))
    pair_ids = set(pairs["poi_id"].astype(str))
    missing_pair_ids = sorted(pair_ids - corpus_ids)
    if missing_pair_ids:
        raise SystemExit(f"Pair POI ids missing from corpus v3: {missing_pair_ids[:10]}")

    gold_ids: set[str] = set(gold["intended_poi_id"].astype(str))
    for raw in gold["acceptable_poi_ids"]:
        gold_ids.update(parse_ids(raw))
    missing_gold = sorted(gold_ids - corpus_ids)
    if missing_gold:
        raise SystemExit(f"Gold v2 IDs missing from corpus v3: {missing_gold[:10]}")

    train_ids = set(view["intended_poi_id"].astype(str))
    for raw in view["acceptable_poi_ids"]:
        train_ids.update(parse_ids(raw))
    overlap = sorted(train_ids & gold_ids)
    if overlap:
        raise SystemExit(f"Train/gold ID overlap: {overlap[:10]}")
    if int((pairs["query_id"].isin(view.loc[view["split"] != "train", "query_id"])).sum()):
        raise SystemExit("training_pairs contains non-train queries")

    slim_docs = docs.loc[:, ["poi_id", "passage_context"]].copy()
    slim_docs["poi_id"] = slim_docs["poi_id"].astype(str)
    pq.write_table(
        pa.Table.from_pandas(slim_docs, preserve_index=False),
        DATA_DIR / "search_documents.parquet",
        compression="zstd",
    )
    shutil.copy2(PILOT / "query_train_view.parquet", DATA_DIR / "query_train_view.parquet")
    shutil.copy2(PILOT / "training_pairs.parquet", DATA_DIR / "training_pairs.parquet")
    shutil.copy2(PILOT / "manifest.json", DATA_DIR / "compile_manifest.json")
    shutil.copy2(PILOT / "mining_manifest.json", DATA_DIR / "mining_manifest.json")
    shutil.copy2(GOLD / "query_variants.csv", DATA_DIR / "gold_query_variants.csv")
    shutil.copy2(GOLD / "target_pois.csv", DATA_DIR / "gold_target_pois.csv")
    shutil.copy2(GOLD / "qrels_policy.json", DATA_DIR / "gold_qrels_policy.json")
    shutil.copy2(GOLD / "manifest.json", DATA_DIR / "gold_manifest.json")
    shutil.copy2(CORPUS / "manifest.json", DATA_DIR / "corpus_manifest.json")

    config = {
        "experiment": "stage1_v6_hardneg_5k",
        "dataset_version": "train_stage1_v6_hardneg_5k",
        "corpus_version": "vn-poi-core-v3-semantic-address-dedup50",
        "gold_dataset": "gold_stage1_v1_corpus_v2",
        "model_id": "intfloat/multilingual-e5-small",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "max_query_tokens": 64,
        "max_passage_tokens": 128,
        "train_batch_size": 16,
        "epochs": 2,
        "learning_rate": 2e-5,
        "weight_decay": 0.01,
        "warmup_ratio": 0.06,
        "max_grad_norm": 1.0,
        "temperature_scale": 20.0,
        "seed": 42,
        "dev_case_fraction": 0.1,
        "eval_depth": 1000,
        "encode_batch_size": 48,
        "gold_hit1_drop_tolerance": 0.01,
        "prefix_k_list": [1, 5, 10],
        "prefix_shc_window": 3,
        "note": (
            "Published v6 5000 POI / 30000 query including 010 SINGLE v03/v05. "
            "Slot weights v01/v02=1.0, SINGLE v03/v05=0.5, COMPOUND v04/v06=0.25. "
            "Hardneg 2+3+3, no forced siblings. Gold Hit@1 lock; FHC/SHC reported."
        ),
    }
    (DATA_DIR / "train_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    pack_files = [
        "search_documents.parquet",
        "query_train_view.parquet",
        "training_pairs.parquet",
        "compile_manifest.json",
        "mining_manifest.json",
        "gold_query_variants.csv",
        "gold_target_pois.csv",
        "gold_qrels_policy.json",
        "gold_manifest.json",
        "corpus_manifest.json",
        "train_config.json",
    ]
    manifest = {
        "dataset": "vn-poi-stage1-v6-hardneg-5k",
        "status": "EXPERIMENTAL",
        "uploads_embeddings": False,
        "corpus_version": config["corpus_version"],
        "gold_dataset": config["gold_dataset"],
        "train_rows": int((view["split"] == "train").sum()),
        "dev_rows": int((view["split"] == "dev").sum()),
        "pair_rows": int(len(pairs)),
        "gold_rows": int(len(gold)),
        "corpus_rows": int(len(slim_docs)),
        "files": {
            name: {"bytes": (DATA_DIR / name).stat().st_size, "sha256": sha256(DATA_DIR / name)}
            for name in pack_files
        },
    }
    (DATA_DIR / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    data_ref = f"{username}/vn-poi-stage1-v6-hardneg-5k"
    kernel_ref = f"{username}/vn-poi-stage1-v6-hardneg-5k-train"
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Stage1 v6 hardneg 5k",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "v6 5k views + mined pairs + corpus v3 + gold v2",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    dest_kernel = KERNEL_DIR / "run_train_stage1_v6_hardneg.py"
    text = SRC_KERNEL.read_text(encoding="utf-8")
    text = text.replace(
        'default=Path("/kaggle/input/vn-poi-stage1-v6-hardneg-pilot")',
        'default=Path("/kaggle/input/vn-poi-stage1-v6-hardneg-5k")',
    )
    dest_kernel.write_text(text, encoding="utf-8")
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "vn-poi-stage1-v6-hardneg-5k-train",
                "code_file": "run_train_stage1_v6_hardneg.py",
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
    (KERNEL_DIR / "README.md").write_text(
        "# vn-poi-stage1-v6-hardneg-5k-train\n\n"
        "New Kaggle script kernel. It does **not** overwrite "
        "`vn-poi-stage1-v6-e5-finetune`, `vn-poi-stage1-v6-hardneg-train`, "
        "or `vn-poi-stage1-v6-hardneg-4k-train`.\n\n"
        "- Published v6 5000 POI / 30000 query; compiled views only.\n"
        "- Slot weights: v01/v02=1.0, SINGLE v03/v05=0.5, COMPOUND v04/v06=0.25.\n"
        "- Hardneg 2 random + 3 lexical + 3 dense. No forced same-brand siblings.\n"
        "- At most 2 epochs. Gold Hit@1 lock; FHC/SHC reported, not used to keep.\n"
        "- Do not upload `*.npy` embeddings with this pack.\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "data_dir": str(DATA_DIR),
                "kernel_dir": str(KERNEL_DIR),
                "data_ref": data_ref,
                "kernel_ref": kernel_ref,
                "train_rows": manifest["train_rows"],
                "pair_rows": manifest["pair_rows"],
                "gold_rows": manifest["gold_rows"],
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
