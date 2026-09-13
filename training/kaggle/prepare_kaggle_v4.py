"""Prepare private v4 Kaggle data/kernel staging without holdout or credentials."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HANOI_QUERIES_20K" / "hanoi_queries_20k"
TRAINING = ROOT / "training" / "stage1"
V3_MODEL = ROOT / "training" / "kaggle" / "outputs" / "stage1_outputs" / "final_model"
STAGING = Path(__file__).resolve().parent
DATASET_DIR = STAGING / "dataset_v4"
MODEL_DIR = STAGING / "model_v3_input"
KERNEL_DIR = STAGING / "kernel_v4"
KAGGLE_CREDENTIAL = Path.home() / ".kaggle" / "kaggle.json"

DATA_FILES = [
    "train_eligible_v4.parquet",
    "dev_synthetic.parquet",
    "test_synthetic.parquet",
    "eligibility_v4.parquet",
    "corpus_search_view.parquet",
    "entity_resolution.parquet",
    "dataset_manifest.json",
    "generation_policy.json",
    "entity_policy.json",
    "validation_report.json",
    "BENCHMARK_PROTOCOL.md",
]

MODEL_FILES = [
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clear_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file():
            path.unlink()


def main() -> None:
    credential = json.loads(KAGGLE_CREDENTIAL.read_text(encoding="utf-8"))
    username = credential.get("username")
    if not username or not credential.get("key"):
        raise RuntimeError("Kaggle credential is missing username or key")

    clear_files(DATASET_DIR)
    clear_files(MODEL_DIR)
    clear_files(KERNEL_DIR)
    copied_data: list[dict[str, object]] = []
    copied_model: list[dict[str, object]] = []

    for name in DATA_FILES:
        source = SOURCE / name
        target = DATASET_DIR / name
        shutil.copy2(source, target)
        copied_data.append(
            {"name": name, "bytes": target.stat().st_size, "sha256": sha256(target)}
        )

    for name in MODEL_FILES:
        source = V3_MODEL / name
        target = MODEL_DIR / f"v3_model_{name}"
        shutil.copy2(source, target)
        copied_model.append(
            {
                "name": target.name,
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )

    config_target = DATASET_DIR / "train_config.json"
    shutil.copy2(TRAINING / "config_v4.json", config_target)
    copied_data.append(
        {
            "name": config_target.name,
            "bytes": config_target.stat().st_size,
            "sha256": sha256(config_target),
        }
    )

    dataset_ref = f"{username}/hanoi-poi-stage1-v4"
    model_dataset_ref = f"{username}/hanoi-poi-stage1-v3-model"
    kernel_ref = f"{username}/hanoi-poi-e5-stage1-v4-train"
    (DATASET_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Hanoi POI Stage 1 v4",
                "id": dataset_ref,
                "licenses": [{"name": "ODbL-1.0"}],
                "subtitle": "Private 20k query training inputs without architecture holdout",
                "description": "Synthetic weak-label Hanoi POI train/dev and frozen v3 regression data. The architecture holdout is deliberately excluded.",
                "keywords": ["nlp"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (MODEL_DIR / "dataset-metadata.json").write_text(
        json.dumps(
            {
                "title": "Hanoi POI Stage 1 v3 E5 Model",
                "id": model_dataset_ref,
                "licenses": [{"name": "MIT"}],
                "subtitle": "Private frozen E5 checkpoint for v4 comparison",
                "description": "Frozen multilingual E5 Stage 1 checkpoint selected by the v3 dev protocol. Stored separately from the ODbL corpus dataset.",
                "keywords": ["nlp"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    shutil.copy2(TRAINING / "train_stage1.py", KERNEL_DIR / "train_stage1.py")
    (KERNEL_DIR / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": kernel_ref,
                "title": "Hanoi POI E5 Stage1 v4 Train",
                "code_file": "train_stage1.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": "true",
                "enable_gpu": "true",
                "enable_internet": "true",
                "dataset_sources": [dataset_ref, model_dataset_ref],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (STAGING / "staging_manifest_v4.json").write_text(
        json.dumps(
            {
                "dataset_ref": dataset_ref,
                "model_dataset_ref": model_dataset_ref,
                "kernel_ref": kernel_ref,
                "private": True,
                "architecture_holdout_uploaded": False,
                "data_files": copied_data,
                "model_files": copied_model,
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
                "dataset_files": len(copied_data),
                "dataset_bytes": sum(int(item["bytes"]) for item in copied_data),
                "model_files": len(copied_model),
                "model_bytes": sum(int(item["bytes"]) for item in copied_model),
                "architecture_holdout_uploaded": False,
                "credential_copied": False,
            }
        )
    )


if __name__ == "__main__":
    main()
