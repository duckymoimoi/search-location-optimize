"""Compare locked E0 vs E1 reports against pre-registered deltas. Does not open test labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "data/vietnam/train_stage1_poi_brand_views_v1/e1_experiment_protocol.json"
E0_POI = ROOT / "artifacts/results/gold_stage1_v21_docker_baseline/baseline_report.json"
E0_BRAND = ROOT / "artifacts/results/gold_stage1_brand_v1_docker_baseline/baseline_report.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(protocol: dict, e0_poi: dict, e0_brand: dict, e1_poi: dict | None, e1_brand: dict | None) -> dict:
    acc = protocol["acceptance"]
    ref = protocol["e0_reference"]
    if e1_poi is None or e1_brand is None:
        return {
            "verdict": "E1_NOT_RUN",
            "note": "Sampler/mask is implemented; train E1 on the unified views before comparing.",
            "thresholds_locked": acc,
            "e0_reference": ref,
        }
    poi_e1 = e1_poi["profiles"]["hybrid_api"]["overall"]
    poi_e1_q01 = e1_poi["profiles"]["hybrid_api"]["by_role"]["q01"]
    brand_e1 = e1_brand["profiles"]["hybrid_api"]["AnyCompatibleHit"]["20"]
    checks = {
        "poi_hit1": ref["poi_hybrid_hit1"] - poi_e1["Hit@1"] <= acc["max_poi_hit1_drop"],
        "poi_hit20": ref["poi_hybrid_hit20"] - poi_e1["Hit@20"] <= acc["max_poi_hit20_drop"],
        "poi_q01_hit1": ref["poi_hybrid_q01_hit1"] - poi_e1_q01["Hit@1"] <= acc["max_poi_q01_hit1_drop"],
        "poi_hit50": ref["poi_hybrid_hit50"] - poi_e1["Hit@50"] <= acc["max_poi_hit50_drop"],
        "brand_hit20_gain": brand_e1 - ref["brand_family_anycompatible_hit20"]
        >= acc["min_brand_anycompatible_hit20_gain"],
    }
    return {
        "verdict": "ACCEPT_E1" if all(checks.values()) else "REJECT_E1",
        "checks": checks,
        "e1": {
            "poi_hit1": poi_e1["Hit@1"],
            "poi_hit20": poi_e1["Hit@20"],
            "poi_q01_hit1": poi_e1_q01["Hit@1"],
            "poi_hit50": poi_e1["Hit@50"],
            "brand_anycompatible_hit20": brand_e1,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    parser.add_argument("--e0-poi", type=Path, default=E0_POI)
    parser.add_argument("--e0-brand", type=Path, default=E0_BRAND)
    parser.add_argument("--e1-poi", type=Path)
    parser.add_argument("--e1-brand", type=Path)
    args = parser.parse_args()
    report = compare(
        load(args.protocol),
        load(args.e0_poi),
        load(args.e0_brand),
        load(args.e1_poi) if args.e1_poi and args.e1_poi.exists() else None,
        load(args.e1_brand) if args.e1_brand and args.e1_brand.exists() else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
