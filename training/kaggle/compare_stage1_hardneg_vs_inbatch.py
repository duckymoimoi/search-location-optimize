#!/usr/bin/env python3
"""Compare hardneg-pilot gate_table against the downloaded in-batch run."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBATCH = ROOT / "output_stage1_v6_e5" / "stage1_v6_e5" / "gate_table.json"
HARDNEG = ROOT / "output_stage1_v6_hardneg" / "stage1_v6_hardneg" / "gate_table.json"


def rows(path: Path) -> dict[str, dict]:
    return {row["profile"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def fmt(row: dict, key: str) -> str:
    value = row.get(key)
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main() -> None:
    if not INBATCH.exists():
        raise SystemExit(f"Missing in-batch gate table: {INBATCH}")
    if not HARDNEG.exists():
        raise SystemExit(f"Missing hardneg gate table: {HARDNEG}")
    left = rows(INBATCH)
    right = rows(HARDNEG)
    keys = ["Recall@100", "Hit@1", "Hit@5", "MRR@10", "K@95"]
    profiles = [
        "zero_shot_gold",
        "zero_shot_dev",
        "finetuned_gold",
        "finetuned_dev",
    ]
    print("profile | metric | in-batch | hardneg | delta")
    for profile in profiles:
        a = left.get(profile)
        b = right.get(profile)
        if not a or not b:
            print(f"{profile}: missing ({'in-batch' if not a else ''} {'hardneg' if not b else ''})")
            continue
        for key in keys:
            av = a.get(key)
            bv = b.get(key)
            delta = ""
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                delta = f"{bv - av:+.3f}"
            print(f"{profile} | {key} | {fmt(a, key)} | {fmt(b, key)} | {delta}")


if __name__ == "__main__":
    main()
