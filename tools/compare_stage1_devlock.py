#!/usr/bin/env python3
"""Compare two dev-only Stage-1 runs on the same Gold and dev Hit metrics.

Rejects a run that scored Gold during checkpoint selection. Does not pick a winner
from a protocol mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def hit(report: dict, key: str) -> float:
    return float(report["overall"]["diagnostic"][key])


def protocol_reasons(summary: dict) -> list[str]:
    reasons = []
    if summary.get("checkpoint_selection") != "dev_only":
        reasons.append("checkpoint_selection is not dev_only")
    if summary.get("gold_opened_after_lock") is not True:
        reasons.append("Gold was not reserved until after the lock")
    for row in summary.get("epoch_eval") or []:
        if "gold_hit1" in row:
            reasons.append(f"epoch {row.get('epoch')} recorded gold_hit1 during selection")
    return reasons


def arm(summary: dict) -> dict:
    profiles = summary["profiles"]
    gold = profiles["finetuned_gold"]
    dev = profiles["finetuned_dev"]
    return {
        "experiment": summary.get("experiment"),
        "kept_epoch": (summary.get("kept_checkpoint") or {}).get("epoch"),
        "dev_hit1": hit(dev, "Hit@1"),
        "gold_hit1": hit(gold, "Hit@1"),
        "gold_hit20": hit(gold, "Hit@20"),
        "gold_hit50": hit(gold, "Hit@50"),
        "gold_mrr10": hit(gold, "MRR@10"),
        "zero_shot_dev_hit1": hit(profiles["zero_shot_dev"], "Hit@1"),
        "zero_shot_gold_hit1": hit(profiles["zero_shot_gold"], "Hit@1"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--left-name", default="left")
    parser.add_argument("--right-name", default="right")
    args = parser.parse_args()
    left_summary = json.loads(args.left.read_text(encoding="utf-8"))
    right_summary = json.loads(args.right.read_text(encoding="utf-8"))
    reasons = {
        args.left_name: protocol_reasons(left_summary),
        args.right_name: protocol_reasons(right_summary),
    }
    report: dict = {"reasons": reasons}
    if any(reasons.values()):
        report["call"] = "reject"
    else:
        left = arm(left_summary)
        right = arm(right_summary)
        keys = ("dev_hit1", "gold_hit1", "gold_hit20", "gold_hit50", "gold_mrr10")
        report["arms"] = {args.left_name: left, args.right_name: right}
        report["right_minus_left"] = {key: right[key] - left[key] for key in keys}
        report["call"] = "compare"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["call"] == "compare" else 1)


if __name__ == "__main__":
    main()
