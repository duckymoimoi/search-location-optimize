"""Create private Kaggle dataset/kernel staging without copying credentials."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HANOI_QUERIES_10K" / "hanoi_queries_10k"
TRAINING = ROOT / "training" / "stage1"
STAGING = Path(__file__).resolve().parent
DATASET_DIR = STAGING / "dataset"
KERNEL_DIR = STAGING / "kernel"
KAGGLE_CREDENTIAL = Path.home() / ".kaggle" / "kaggle.json"

DATA_FILES = [
    "queries_10k.parquet",
    "corpus_search_view.parquet",
    "entity_resolution.parquet",
    "dataset_manifest.json",
    "generation_policy.json",
    "entity_policy.json",
    "validation_report.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def main() -> None:
    credential = json.loads(KAGGLE_CREDENTIAL.read_text(encoding="utf-8"))
    username = credential.get("username")
    if not username or not credential.get("key"):
        raise RuntimeError("Kaggle credential is missing username or key")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    for path in DATASET_DIR.iterdir():
        if path.is_file():
            path.unlink()
    for path in KERNEL_DIR.iterdir():
        if path.is_file():
            path.unlink()

    copied = []
    for name in DATA_FILES:
        source = SOURCE / name
        if not source.exists():
            raise FileNotFoundError(source)
        target = DATASET_DIR / name
        shutil.copy2(source, target)
        copied.append(
            {"name": name, "bytes": target.stat().st_size, "sha256": sha256(target)}
        )
    config_target = DATASET_DIR / "train_config.json"
    shutil.copy2(TRAINING / "config.json", config_target)
    copied.append(
        {
            "name": config_target.name,
            "bytes": config_target.stat().st_size,
            "sha256": sha256(config_target),
        }
    )

    dataset_ref = f"{username}/hanoi-poi-stage1-v3"
    kernel_ref = f"{username}/hanoi-poi-e5-stage1-train"
    (DATASET_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Hanoi POI Stage 1 v3",
                "id": dataset_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "Private pilot data for Vietnamese POI retrieval training",
                "description": "Synthetic weak-label query data and OSM-derived search view for a private Stage 1 retrieval experiment.",
                "keywords": ["nlp", "search", "vietnam"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    shutil.copy2(TRAINING / "train_stage1.py", KERNEL_DIR / "train_stage1.py")
    shutil.copy2(TRAINING / "config.json", KERNEL_DIR / "config.json")
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "Hanoi POI E5 Stage1 Train",
                "code_file": "train_stage1.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [dataset_ref],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (STAGING / "staging_manifest.json").write_text(
        json.dumps(
            {
                "dataset_ref": dataset_ref,
                "kernel_ref": kernel_ref,
                "private": True,
                "files": copied,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "prepared": True,
                "dataset_files": len(copied),
                "dataset_bytes": sum(item["bytes"] for item in copied),
                "credential_copied": False,
            }
        )
    )


if __name__ == "__main__":
    main()
