#!/usr/bin/env python3
"""Read a hardneg summary.json and say whether the dev-only Gold pass still stands.

Does not select a checkpoint. A run that scored Gold during training is rejected.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def hit1(report: dict) -> float:
    return float(report["overall"]["diagnostic"]["Hit@1"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    profiles = summary["profiles"]
    reasons: list[str] = []
    if summary.get("checkpoint_selection") != "dev_only":
        reasons.append("checkpoint_selection is not dev_only")
    if summary.get("gold_opened_after_lock") is not True:
        reasons.append("Gold was not reserved until after the lock")
    for row in summary.get("epoch_eval") or []:
        if "gold_hit1" in row:
            reasons.append(f"epoch {row.get('epoch')} recorded gold_hit1 during selection")
    verdict = {
        "experiment": summary.get("experiment"),
        "kept_checkpoint": summary.get("kept_checkpoint"),
        "reasons": reasons,
    }
    if not reasons and "finetuned_gold" in profiles and "zero_shot_gold" in profiles:
        gold = hit1(profiles["finetuned_gold"])
        zs_gold = hit1(profiles["zero_shot_gold"])
        dev = hit1(profiles["finetuned_dev"])
        zs_dev = hit1(profiles["zero_shot_dev"])
        verdict.update(
            {
                "gold_hit1": gold,
                "zero_shot_gold_hit1": zs_gold,
                "gold_delta": gold - zs_gold,
                "dev_hit1": dev,
                "zero_shot_dev_hit1": zs_dev,
                "dev_delta": dev - zs_dev,
            }
        )
        if gold + 1e-12 < zs_gold:
            verdict["call"] = "stop"
        elif dev + 1e-12 < zs_dev:
            verdict["call"] = "stop"
        else:
            verdict["call"] = "continue"
    else:
        verdict["call"] = "reject"
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    sys.exit(0 if verdict["call"] == "continue" else 1)


if __name__ == "__main__":
    main()
