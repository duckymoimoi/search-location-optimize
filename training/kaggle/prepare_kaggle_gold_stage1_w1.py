#!/usr/bin/env python3
"""Prepare Kaggle dataset+kernel for gold_stage1_v1 Round-1 screening.

Does NOT run BM25/dense locally (weak network / avoid heavy machine load).
BM25 + 6 dense exact run inside the Kaggle GPU kernel.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GOLD = ROOT / "data" / "vietnam" / "gold_stage1_v1"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v1"
DATA_DIR = HERE / "dataset_gold_stage1_w1"
KERNEL_DIR = HERE / "kernel_gold_stage1_w1"


def main() -> None:
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        raise SystemExit(f"Missing {cred_path}")
    username = json.loads(cred_path.read_text(encoding="utf-8"))["username"]

    qcsv = GOLD / "query_variants_v1.csv"
    if not qcsv.exists():
        raise SystemExit(f"Run lock_query_variants_v1.py first — missing {qcsv}")

    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(CORPUS / "search_documents.parquet", DATA_DIR / "search_documents.parquet")
    shutil.copy2(qcsv, DATA_DIR / "query_variants_v1.csv")
    if (GOLD / "query_variants_v1.parquet").exists():
        shutil.copy2(GOLD / "query_variants_v1.parquet", DATA_DIR / "query_variants_v1.parquet")
    shutil.copy2(GOLD / "manifest.json", DATA_DIR / "gold_manifest.json")
    if (GOLD / "qrels_policy_v1.json").exists():
        shutil.copy2(GOLD / "qrels_policy_v1.json", DATA_DIR / "qrels_policy_v1.json")
    shutil.copy2(GOLD / "target_pois_v1.csv", DATA_DIR / "target_pois_v1.csv")

    data_ref = f"{username}/vn-poi-gold-stage1-w1"
    kernel_ref = f"{username}/vn-poi-gold-stage1-w1-exact-dense-bm25"

    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "VN POI Gold Stage1 W1",
                "id": data_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "vn-poi-core-v1 passages + locked gold_stage1_v1 1080 queries",
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
                "title": "vn-poi-gold-stage1-w1-exact-dense-bm25",
                "code_file": "run_gold_stage1_exact.py",
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

    (DATA_DIR / "README.md").write_text(
        "# VN POI Gold Stage1 W1\n\n"
        "- `search_documents.parquet` — vn-poi-core-v1 passages\n"
        "- `query_variants_v1.csv` — 1080 locked queries\n"
        "- BM25 is built **inside the Kaggle kernel** (not precomputed locally)\n",
        encoding="utf-8",
    )
    (KERNEL_DIR / "README.md").write_text(
        "# Gold Stage1 Round-1 — BM25 + 6 dense exact (Kaggle GPU)\n\n"
        "Profiles: BM25Okapi default · mE5-small · Bekko A8M · Bekko A25M · "
        "Halong · GTE-multilingual-base · BGE-M3.\n\n"
        "Exact top-1000 only (no ANN). Internet ON for HF downloads.\n\n"
        "```bash\n"
        "python data/vietnam/gold_stage1_v1/lock_query_variants_v1.py\n"
        "python training/kaggle/prepare_kaggle_gold_stage1_w1.py\n"
        f"kaggle datasets create -p {DATA_DIR.as_posix()} --dir-mode zip\n"
        f"# or: kaggle datasets version -p {DATA_DIR.as_posix()} -m 'gold w1' --dir-mode zip\n"
        f"kaggle kernels push -p {KERNEL_DIR.as_posix()}\n"
        f"kaggle kernels status {kernel_ref}\n"
        "```\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "data_dir": str(DATA_DIR),
                "kernel_dir": str(KERNEL_DIR),
                "data_ref": data_ref,
                "kernel_ref": kernel_ref,
                "next": [
                    f"kaggle datasets create -p {DATA_DIR} --dir-mode zip",
                    f"kaggle kernels push -p {KERNEL_DIR}",
                    f"kaggle kernels status {kernel_ref}",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
