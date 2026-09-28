#!/usr/bin/env python3
"""Kaggle GPU hard-negative miner for the clean 6k views.

Encodes passages and queries on the GPU. The input dataset has no embedding npy.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def resolve_input() -> Path:
    root = Path("/kaggle/input")
    if not root.exists():
        raise SystemExit("This script runs on Kaggle")
    matches = sorted(root.rglob("gold_holdout_ids.json"))
    for match in matches:
        parent = match.parent
        needed = [
            "query_train_view.parquet",
            "query_relation_view.parquet",
            "search_documents.parquet",
            "pois_entity.parquet",
        ]
        if all((parent / name).exists() for name in needed):
            return parent
    raise SystemExit("Mine input pack not found under /kaggle/input")


def ensure_gpu_compat() -> None:
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.stdout.strip().startswith("6.0"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--force-reinstall",
                "torch==2.7.1",
                "--index-url",
                "https://download.pytorch.org/whl/cu126",
            ],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "torchvision", "torchaudio"],
            check=False,
        )


def main() -> None:
    ensure_gpu_compat()
    data = resolve_input()
    out = Path("/kaggle/working/mine_6k_clean")
    out.mkdir(parents=True, exist_ok=True)
    sys.argv = [
        "mine_stage1_hardneg_pilot.py",
        "--views",
        str(data),
        "--out",
        str(out),
        "--docs",
        str(data / "search_documents.parquet"),
        "--core",
        str(data / "pois_entity.parquet"),
        "--holdout-ids",
        str(data / "gold_holdout_ids.json"),
        "--holdout-gold",
        "",
        "--lexical-quota",
        "1",
        "--sibling-quota",
        "0",
        "--encode-corpus",
        "--require-gpu",
        "--passage-max-tokens",
        "128",
        "--encode-batch-size",
        "64",
    ]
    from mine_stage1_hardneg_pilot import main as mine_main

    mine_main()


if __name__ == "__main__":
    main()
