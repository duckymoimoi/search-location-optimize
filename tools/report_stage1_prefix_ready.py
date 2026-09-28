#!/usr/bin/env python3
"""Prefix denominator and entity_ready scores for Gold POI v2.1 q01.

Headline uses checkpoints at or after entity_ready_grapheme.
Raw FHC over the whole string is diagnostic only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/prefix_evidence_v2_1.jsonl"
KS = (1, 5, 10)
WINDOW = 3


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def denominator(evidence: list[dict]) -> dict:
    ready_counts = []
    only_final = 0
    for row in evidence:
        full = int(row["full_graphemes"])
        ready = int(row["entity_ready_grapheme"])
        n_ready = full - ready + 1
        ready_counts.append(n_ready)
        if ready == full:
            only_final += 1
    shc_cases = sum(1 for count in ready_counts if count >= WINDOW)
    return {
        "n_q01": len(evidence),
        "entity_ready_checkpoints": int(sum(ready_counts)),
        "cases_entity_ready_only_at_final_char": only_final,
        "cases_with_at_least_3_entity_ready_checkpoints": shc_cases,
    }


def session_hit_stats(ranks: list[int | None]) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {"n_checkpoints": len(ranks)}
    for k in KS:
        flags = [rank is not None and rank <= k for rank in ranks]
        found = any(flags)
        out[f"FHC@{k}"] = int(found)
        shc = None
        if len(flags) >= WINDOW:
            shc = int(any(all(flags[start : start + WINDOW]) for start in range(0, len(flags) - WINDOW + 1)))
        out[f"SHC@{k}"] = shc
        out[f"PrefixAUC@{k}"] = (sum(flags) / len(flags)) if flags else None
    return out


def score(evidence: list[dict], rows: list[dict]) -> dict:
    by_query: dict[str, list[dict]] = {}
    for row in rows:
        by_query.setdefault(str(row["variant_id"]), []).append(row)
    raw_sessions = []
    ready_sessions = []
    for item in evidence:
        query_id = str(item["query_id"])
        ordered = sorted(by_query.get(query_id, []), key=lambda row: int(row["prefix_index"]))
        raw_ranks = [row.get("rank") for row in ordered]
        ready_at = int(item["entity_ready_grapheme"])
        ready_ranks = [row.get("rank") for row in ordered if int(row["prefix_index"]) >= ready_at]
        raw_sessions.append(session_hit_stats(raw_ranks))
        ready_sessions.append(session_hit_stats(ready_ranks))

    def mean_rate(sessions: list[dict], key: str) -> dict:
        values = [row[key] for row in sessions if row[key] is not None]
        return {"n": len(values), "rate": (sum(values) / len(values)) if values else None}

    report = {"raw": {}, "entity_ready": {}}
    for label, sessions in (("raw", raw_sessions), ("entity_ready", ready_sessions)):
        for k in KS:
            report[label][f"FHC@{k}"] = mean_rate(sessions, f"FHC@{k}")
            report[label][f"SHC@{k}"] = mean_rate(sessions, f"SHC@{k}")
            report[label][f"PrefixAUC@{k}"] = mean_rate(sessions, f"PrefixAUC@{k}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix-jsonl", type=Path, default=None)
    args = parser.parse_args()
    evidence = load_jsonl(EVIDENCE)
    report = {"denominator": denominator(evidence)}
    if args.prefix_jsonl is not None:
        report["scores"] = score(evidence, load_jsonl(args.prefix_jsonl))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
