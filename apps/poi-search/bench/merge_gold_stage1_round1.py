#!/usr/bin/env python3
"""Merge Round-1 + Round-1b gold Stage-1 results into one gate report."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P1 = ROOT / "training/kaggle/output_gold_stage1_w1/gold_stage1_w1/summary_partial.json"
P2 = ROOT / "training/kaggle/output_gold_stage1_w1b/gold_stage1_w1/summary.json"
OUT = ROOT / "apps/poi-search/bench/results/gold_stage1_selection"
OUT.mkdir(parents=True, exist_ok=True)


def load_profiles(*paths: Path) -> dict:
    merged: dict = {}
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for name, prof in data.get("profiles", {}).items():
            merged[name] = prof
    return merged


def main() -> None:
    profiles = load_profiles(P1, P2)
    gate = []
    for name, prof in profiles.items():
        if "error" in prof:
            gate.append({"profile": name, "ok": False, "error": prof["error"][:200]})
            continue
        o = prof["overall"]
        m = prof.get("meta") or {}
        gate.append(
            {
                "profile": name,
                "ok": True,
                "Recall@100": o["recall"]["Recall@100"],
                "Recall@500": o["recall"]["Recall@500"],
                "Recall@1000": o["recall"]["Recall@1000"],
                "K@95": o["k_at_r"]["K@95"],
                "K@98": o["k_at_r"]["K@98"],
                "SR@1": o["diagnostic"]["SR@1"],
                "SR@5": o["diagnostic"]["SR@5"],
                "SR@10": o["diagnostic"]["SR@10"],
                "MRR@10": o["diagnostic"]["MRR@10"],
                "dim": m.get("dim"),
                "encode_corpus_s": m.get("encode_corpus_s"),
                "encode_query_ms_mean": m.get("encode_query_ms_mean"),
                "hf_id": m.get("hf_id"),
                "by_family_R1000": {
                    k: v["recall"]["Recall@1000"] for k, v in prof.get("by_family", {}).items()
                },
                "by_stratum_R1000": {
                    k: v["recall"]["Recall@1000"] for k, v in prof.get("by_stratum", {}).items()
                },
                "by_family_R100": {
                    k: v["recall"]["Recall@100"] for k, v in prof.get("by_family", {}).items()
                },
            }
        )

    ok = [r for r in gate if r["ok"]]
    ok.sort(
        key=lambda r: (
            -r["Recall@1000"],
            r["K@95"] if r["K@95"] is not None else 10**9,
            -(r["Recall@100"]),
        )
    )
    fails = [r for r in gate if not r["ok"]]

    report = {
        "dataset": "gold_stage1_v1",
        "n_queries": 1080,
        "n_cases": 180,
        "depth": 1000,
        "protocol": "SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL",
        "winner_order": ["Recall@1000", "K@95", "K@98", "family_slices", "latency", "size", "dim"],
        "gate_ranked": ok,
        "failed": fails,
        "provisional_winner": ok[0]["profile"] if ok else None,
        "notes": [
            "GTE-multilingual-base failed CUDA CUBLAS on Kaggle Round-1b — excluded from ranking.",
            "Prefix-char Round-1b still pending (separate kernel).",
            "BM25 = untuned Okapi floor, not production lexical.",
            "Do not pick by MRR@10 alone.",
        ],
    }
    out_path = OUT / "round1_merged_gate.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("PROVISIONAL WINNER:", report["provisional_winner"])
    print()
    print(f"{'profile':28} {'R@100':>6} {'R@500':>6} {'R@1000':>7} {'K95':>5} {'K98':>5} {'MRR':>6} {'q_ms':>6} {'dim':>5} {'corp_s':>7}")
    for r in ok:
        print(
            f"{r['profile']:28} {r['Recall@100']:6.3f} {r['Recall@500']:6.3f} {r['Recall@1000']:7.3f} "
            f"{str(r['K@95']):>5} {str(r['K@98']):>5} {r['MRR@10']:6.3f} "
            f"{str(r['encode_query_ms_mean'] or '-'):>6} {str(r['dim'] or '-'):>5} {str(r['encode_corpus_s'] or '-'):>7}"
        )
    for r in fails:
        print(f"FAIL {r['profile']}: {r['error'][:100]}")

    me5 = next(r for r in ok if "me5" in r["profile"])
    fams = sorted(me5["by_family_R1000"])
    print("\nFamily Recall@1000")
    print(f"{'profile':28}", " ".join(f"{f[:10]:>10}" for f in fams))
    for r in ok:
        print(
            f"{r['profile']:28}",
            " ".join(f"{r['by_family_R1000'].get(f, 0):10.3f}" for f in fams),
        )

    strata = sorted(me5["by_stratum_R1000"])
    print("\nStratum Recall@1000")
    print(f"{'profile':28}", " ".join(f"{s[:10]:>10}" for s in strata))
    for r in ok:
        print(
            f"{r['profile']:28}",
            " ".join(f"{r['by_stratum_R1000'].get(s, 0):10.3f}" for s in strata),
        )

    print("\nwrote", out_path)


if __name__ == "__main__":
    main()
