"""36k train-v6 lexical diagnostic + policy-knob ablation.

Authored queries, not a lock set. Slice by slot (v01-v06), severity, stratum.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "poi-search" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_stage1_v2_docker_baseline import (  # noqa: E402
    hybrid_rankings,
    lexical_rankings,
    request_json,
)
from settings import LEXICAL_CONFIG, POLICY  # noqa: E402

DEFAULT_QUERIES = ROOT / "data" / "vietnam" / "train_stage1_queries_v6" / "query_variants.parquet"
DEFAULT_OUT = ROOT / "artifacts" / "results" / "train_v6_36k_lexical_diag"
KS = (1, 20, 50)


def parse_ids(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        return [str(x) for x in ast.literal_eval(text)]
    return [text]


def slot_of(variant_id: str) -> str:
    return str(variant_id).rsplit("-", 1)[-1]


def hit_at(ranks: list[str], gold: list[str], k: int) -> bool:
    gold_set = set(gold)
    return any(doc in gold_set for doc in ranks[:k])


def summarize(rows: list[dict], ranks: list[list[str]]) -> dict:
    buckets: dict[str, list[int]] = defaultdict(list)
    per_k = {k: [] for k in KS}
    miss50 = 0
    for row, ranking in zip(rows, ranks):
        gold = row["gold"]
        hits = {k: int(hit_at(ranking, gold, k)) for k in KS}
        for k in KS:
            per_k[k].append(hits[k])
        miss50 += int(not hits[50])
        for key in (
            f"slot:{row['slot']}",
            f"severity:{row['severity']}",
            f"stratum:{row['stratum']}",
            f"family:{row['family']}",
        ):
            buckets[key].append(hits[20])
            buckets[f"{key}@1"].append(hits[1])
            buckets[f"{key}@50"].append(hits[50])
    n = len(rows)
    out = {
        "n": n,
        "hit@1": round(100 * sum(per_k[1]) / n, 2) if n else 0,
        "hit@20": round(100 * sum(per_k[20]) / n, 2) if n else 0,
        "hit@50": round(100 * sum(per_k[50]) / n, 2) if n else 0,
        "miss@50": miss50,
        "slices": {},
    }
    for key, values in sorted(buckets.items()):
        if "@" in key.split(":", 1)[-1] and key.split(":")[0] in {"slot", "severity", "stratum", "family"}:
            # keys like slot:v01@1
            pass
        if key.endswith("@1") or key.endswith("@50"):
            continue
        n_b = len(values)
        out["slices"][key] = {
            "n": n_b,
            "hit@1": round(100 * sum(buckets[f"{key}@1"]) / n_b, 2),
            "hit@20": round(100 * sum(values) / n_b, 2),
            "hit@50": round(100 * sum(buckets[f"{key}@50"]) / n_b, 2),
        }
    return out


def apply_knobs(fuzzy: float, name_compact: float) -> None:
    LEXICAL_CONFIG["fuzzy"] = fuzzy
    LEXICAL_CONFIG["name_compact"] = name_compact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--skip-lexical", action="store_true")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--es-url", default="http://127.0.0.1:9200")
    args = parser.parse_args()

    frame = pd.read_parquet(args.queries)
    rows = []
    for rec in frame.to_dict("records"):
        gold = parse_ids(rec.get("acceptable_poi_ids")) or [str(rec["intended_poi_id"])]
        rows.append(
            {
                "variant_id": rec["variant_id"],
                "query": rec["query_text"],
                "gold": gold,
                "slot": slot_of(rec["variant_id"]),
                "severity": rec.get("severity") or "",
                "stratum": rec.get("primary_sampling_stratum") or "",
                "family": rec.get("query_variant_family") or "",
            }
        )
    queries = [row["query"] for row in rows]
    args.out.mkdir(parents=True, exist_ok=True)

    knobs = [
        ("neither", 0.0, 0.0),
        ("compact_only", 0.0, 24.0),
        ("v12_current", 3.0, 24.0),
        ("fuzzy_up", 6.0, 24.0),
    ]
    report = {
        "n": len(rows),
        "policy_version": POLICY.get("version"),
        "note": "authored 36k diagnostic; knobs are user-behavior hyperparameters, not Gold-fit",
        "lexical": {},
    }
    print(f"loaded {len(rows)} queries from {args.queries}", flush=True)
    if args.skip_lexical:
        for name, _fuzzy, _name_compact in knobs:
            prior = args.out / f"lexical_{name}.json"
            if prior.exists():
                report["lexical"][name] = json.loads(prior.read_text(encoding="utf-8"))
    else:
        for name, fuzzy, name_compact in knobs:
            apply_knobs(fuzzy, name_compact)
            print(f"lexical {name} fuzzy={fuzzy} name_compact={name_compact}", flush=True)
            ranks = lexical_rankings(args.es_url, queries, batch_size=40)
            summary = summarize(rows, ranks)
            summary["fuzzy"] = fuzzy
            summary["name_compact"] = name_compact
            report["lexical"][name] = summary
            (args.out / f"lexical_{name}.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                f"  {name}: @1={summary['hit@1']} @20={summary['hit@20']} "
                f"@50={summary['hit@50']} miss@50={summary['miss@50']}",
                flush=True,
            )

    apply_knobs(3.0, 24.0)
    if args.hybrid:
        status = request_json(f"{args.api_url}/v1/status", None)
        print(f"hybrid via {args.api_url} policy={status.get('versions', {}).get('candidate_policy_version')}", flush=True)
        ranks = hybrid_rankings(args.api_url, queries, workers=4)
        summary = summarize(rows, ranks)
        report["hybrid_v12"] = summary
        (args.out / "hybrid_v12.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"  hybrid: @1={summary['hit@1']} @20={summary['hit@20']} "
            f"@50={summary['hit@50']} miss@50={summary['miss@50']}",
            flush=True,
        )

    (args.out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: {kk: report["lexical"][k][kk] for kk in ("hit@1", "hit@20", "hit@50", "miss@50")} for k in report["lexical"]}, indent=2))
    print(f"wrote {args.out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
