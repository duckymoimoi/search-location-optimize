"""Stage private Kaggle datasets and GPU evaluation kernel for stable-v1."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
QUERY = ROOT / "HANOI_QUERIES_20K" / "hanoi_queries_20k_stable_v1"
CORPUS = ROOT / "HANOI_POI_STABLE_V1" / "hanoi_poi_stable_v1"
MODEL = ROOT / "artifacts" / "models" / "e5-v4-finetuned" / "final_model"
EVALUATOR = ROOT / "training" / "stage1" / "prepare_stable_dense.py"


def reset(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def main() -> None:
    credentials = json.loads((Path.home() / ".kaggle" / "kaggle.json").read_text(encoding="utf-8"))
    username = credentials["username"]
    data_dir = HERE / "dataset_stable_v1"
    model_dir = HERE / "model_v4_input"
    kernel_dir = HERE / "kernel_stable_eval"
    for directory in (data_dir, model_dir, kernel_dir):
        reset(directory)

    for source in (
        QUERY / "queries_20k.parquet", QUERY / "eligibility.parquet",
        QUERY / "typing_sessions.parquet", QUERY / "qrels.parquet",
        QUERY / "manifest.json", QUERY / "validation.json",
        CORPUS / "pois.parquet", CORPUS / "search_documents.parquet",
        CORPUS / "manifest.json", CORPUS / "validation.json",
    ):
        target_name = source.name
        if target_name in {"manifest.json", "validation.json"}:
            target_name = ("query_" if source.parent == QUERY else "corpus_") + target_name
        shutil.copy2(source, data_dir / target_name)

    for source in MODEL.iterdir():
        if source.is_file():
            shutil.copy2(source, model_dir / source.name)
    shutil.copy2(EVALUATOR, kernel_dir / "prepare_stable_dense.py")

    data_ref = f"{username}/hanoi-poi-stage1-stable-v1"
    model_ref = f"{username}/hanoi-poi-stage1-v4-model"
    kernel_ref = f"{username}/hanoi-poi-stage1-stable-v1-eval"
    (data_dir / "dataset-metadata.json").write_text(json.dumps({
        "title": "Hanoi POI Stage1 Stable v1", "id": data_ref,
        "licenses": [{"name": "ODbL-1.0"}],
        "subtitle": "Private stable OSM corpus and migrated 20k evaluation queries",
    }, indent=2) + "\n", encoding="utf-8")
    (model_dir / "dataset-metadata.json").write_text(json.dumps({
        "title": "Hanoi POI Stage1 v4 Selected Model", "id": model_ref,
        "licenses": [{"name": "MIT"}],
        "subtitle": "Private selected multilingual E5 checkpoint",
    }, indent=2) + "\n", encoding="utf-8")
    (kernel_dir / "kernel-metadata.json").write_text(json.dumps({
        "id": kernel_ref, "title": "Hanoi POI Stage1 Stable v1 Eval",
        "code_file": "prepare_stable_dense.py", "language": "python",
        "kernel_type": "script", "is_private": "true", "enable_gpu": "true",
        "enable_internet": "false", "dataset_sources": [data_ref, model_ref],
        "competition_sources": [], "kernel_sources": [], "model_sources": [],
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"data_ref": data_ref, "model_ref": model_ref, "kernel_ref": kernel_ref}))


if __name__ == "__main__":
    main()
