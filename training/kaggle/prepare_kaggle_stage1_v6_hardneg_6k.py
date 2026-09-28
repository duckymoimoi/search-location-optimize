#!/usr/bin/env python3
"""Pack the isolated v6 6k hardneg experiment + Gold v2.1.

Does not overwrite 4k/5k/in-batch kernels or published v6 CSV.
Does not upload embeddings. Does not mix brand Gold into 1-target loss.
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
PILOT = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_6k"
GOLD = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_v2_1"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v3"
DATA_DIR = HERE / "dataset_stage1_v6_hardneg_6k"
KERNEL_DIR = HERE / "kernel_stage1_v6_hardneg_6k"
SRC_KERNEL = HERE / "kernel_stage1_v6_hardneg_5k" / "run_train_stage1_v6_hardneg.py"


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


def gold_to_kernel_csv(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for raw in sessions.to_dict("records"):
        accept = parse_ids(raw.get("acceptable_poi_ids"))
        intended = str(raw["intended_poi_id"])
        if intended not in accept:
            accept.insert(0, intended)
        rows.append(
            {
                "variant_id": str(raw["query_id"]),
                "case_id": str(raw["case_id"]),
                "query_text": str(raw["query_text"]),
                "query_variant_family": str(raw.get("difficulty") or "clean"),
                "primary_sampling_stratum": str(raw.get("primary_sampling_stratum") or ""),
                "intended_poi_id": intended,
                "acceptable_poi_ids": json.dumps(accept, ensure_ascii=False),
                "query_role": str(raw.get("query_role") or ""),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]

    sessions_path = GOLD / "query_sessions_v2_1.csv"
    required = [
        PILOT / "query_train_view.parquet",
        PILOT / "query_relation_view.parquet",
        PILOT / "training_pairs.parquet",
        PILOT / "manifest.json",
        PILOT / "mining_manifest.json",
        sessions_path,
        GOLD / "target_pois_v2_1.csv",
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
    sessions = pd.read_csv(sessions_path)
    gold = gold_to_kernel_csv(sessions)
    gold.to_csv(DATA_DIR / "gold_query_variants.csv", index=False)

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
        raise SystemExit(f"Gold v2.1 IDs missing from corpus v3: {missing_gold[:10]}")

    # Gold targets may appear as extra acceptables on other-branch train rows.
    # Strip them from this experimental view/pairs; do not rewrite published v6.
    def strip_gold_acceptables(raw) -> str:
        kept = [poi_id for poi_id in parse_ids(raw) if poi_id not in gold_ids]
        return json.dumps(kept, ensure_ascii=False)

    view = view.copy()
    view["acceptable_poi_ids"] = view["acceptable_poi_ids"].map(strip_gold_acceptables)
    train_intended = set(view["intended_poi_id"].astype(str))
    if train_intended & gold_ids:
        raise SystemExit(f"Train intended overlaps gold: {sorted(train_intended & gold_ids)[:10]}")
    drop_pos = (pairs["label"].astype(str) == "positive") & pairs["poi_id"].astype(str).isin(gold_ids)
    pairs = pairs.loc[~drop_pos].copy()
    print(f"stripped gold IDs from train acceptables; dropped {int(drop_pos.sum())} gold-positive pair rows")
    if int((pairs["query_id"].isin(view.loc[view["split"] != "train", "query_id"])).sum()):
        raise SystemExit("training_pairs contains non-train queries")
    if len(gold) != 800:
        raise SystemExit(f"Gold v2.1 expected 800 sessions, got {len(gold)}")

    slim_docs = docs.loc[:, ["poi_id", "passage_context"]].copy()
    slim_docs["poi_id"] = slim_docs["poi_id"].astype(str)
    pq.write_table(
        pa.Table.from_pandas(slim_docs, preserve_index=False),
        DATA_DIR / "search_documents.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pandas(view, preserve_index=False),
        DATA_DIR / "query_train_view.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pandas(pairs, preserve_index=False),
        DATA_DIR / "training_pairs.parquet",
        compression="zstd",
    )
    shutil.copy2(PILOT / "manifest.json", DATA_DIR / "compile_manifest.json")
    shutil.copy2(PILOT / "mining_manifest.json", DATA_DIR / "mining_manifest.json")
    shutil.copy2(GOLD / "target_pois_v2_1.csv", DATA_DIR / "gold_target_pois.csv")
    shutil.copy2(GOLD / "manifest.json", DATA_DIR / "gold_manifest.json")
    shutil.copy2(CORPUS / "manifest.json", DATA_DIR / "corpus_manifest.json")

    config = {
        "experiment": "stage1_v6_hardneg_6k_v21",
        "dataset_version": "train_stage1_v6_hardneg_6k",
        "corpus_version": "vn-poi-core-v3-semantic-address-dedup50",
        "gold_dataset": "gold_stage1_v2_1",
        "expected_gold_rows": 800,
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
        "prefix_roles": ["q01"],
        "note": (
            "Published v6 6000 POI / 36000 query. Gold v2.1 800 sessions. "
            "Hardneg lexical=1 dense=3 random=2; no forced siblings. "
            "Slot weights v01/v02=1.0, noisy=0.25. Prefix FHC/SHC on q01 only. "
            "Checkpoint lock stays gold Hit@1 / dev Hit@1."
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
        "gold_manifest.json",
        "corpus_manifest.json",
        "train_config.json",
    ]
    manifest = {
        "dataset": "vn-poi-stage1-v6-hardneg-6k",
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

    data_ref = f"{username}/vn-poi-stage1-v6-hardneg-6k"
    kernel_ref = f"{username}/vn-poi-stage1-v6-hardneg-6k-train"
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Stage1 v6 hardneg 6k",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "v6 6k views + gold v2.1 + corpus v3",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    dest_kernel = KERNEL_DIR / "run_train_stage1_v6_hardneg.py"
    text = SRC_KERNEL.read_text(encoding="utf-8")
    text = text.replace(
        'default=Path("/kaggle/input/vn-poi-stage1-v6-hardneg-5k")',
        'default=Path("/kaggle/input/vn-poi-stage1-v6-hardneg-6k")',
    )
    text = text.replace(
        'and checks["gold_rows"] == 1080',
        'and checks["gold_rows"] == int(config.get("expected_gold_rows") or 800)',
    )
    old_expand = '''def expand_char_prefixes(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in sessions.itertuples(index=False):
        chars = grapheme_clusters(row.query_text)'''
    new_expand = '''def expand_char_prefixes(sessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in sessions.itertuples(index=False):
        role = str(getattr(row, "query_role", "") or "")
        if role and role != "q01":
            continue
        chars = grapheme_clusters(row.query_text)'''
    if old_expand not in text:
        raise SystemExit("kernel prefix hook not found")
    dest_kernel.write_text(text.replace(old_expand, new_expand), encoding="utf-8")
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "vn-poi-stage1-v6-hardneg-6k-train",
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
        "# vn-poi-stage1-v6-hardneg-6k-train\n\n"
        "New kernel. Does not overwrite 5k/4k/in-batch.\n\n"
        "- Published v6 6000 POI; Gold v2.1 800 sessions as lock gold.\n"
        "- Hardneg lexical=1, dense=3, random=2. No forced siblings.\n"
        "- Prefix FHC/SHC on q01 only. Checkpoint lock is gold Hit@1.\n"
        "- Do not upload embeddings.\n",
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
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
