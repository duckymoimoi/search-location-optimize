#!/usr/bin/env python3
"""Pack the dev-lock checkpoint plus brand Gold for a rescore dataset.

Does not upload corpus embeddings. Corpus passages stay on the 6k-devlock dataset.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHECKPOINT = HERE / "output_stage1_v6_hardneg_6k_devlock" / "stage1_v6_hardneg" / "checkpoint_e5_hardneg"
BRAND = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_brand_v1"
MEMBERSHIP = ROOT / "data" / "vietnam" / "train_stage1_brand_membership_v3" / "brand_group_members_v3.parquet"
DATA_DIR = HERE / "dataset_stage1_v6_hardneg_6k_devlock_rescore"


def main() -> None:
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]
    required = [
        CHECKPOINT / "model.safetensors",
        CHECKPOINT / "config.json",
        CHECKPOINT / "tokenizer.json",
        CHECKPOINT / "tokenizer_config.json",
        BRAND / "brand_queries_v1.parquet",
        MEMBERSHIP,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    for name in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
        shutil.copy2(CHECKPOINT / name, DATA_DIR / name)
    shutil.copy2(BRAND / "brand_queries_v1.parquet", DATA_DIR / "brand_queries_v1.parquet")
    shutil.copy2(MEMBERSHIP, DATA_DIR / "brand_group_members_v3.parquet")
    data_ref = f"{username}/vn-poi-stage1-v6-hardneg-6k-devlock-rescore"
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Stage1 v6 hardneg 6k devlock rescore",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "Dev-lock checkpoint plus brand Gold queries. No corpus embeddings.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"data_ref": data_ref, "bytes": sum(path.stat().st_size for path in DATA_DIR.iterdir())}))


if __name__ == "__main__":
    main()
