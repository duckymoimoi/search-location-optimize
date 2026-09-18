#!/usr/bin/env python3
"""Verify frozen gold_stage1_v1 artifacts (counts + SHA)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

GOLD = Path(__file__).resolve().parent
CSV = GOLD / "query_variants_v1.csv"
POI = GOLD / "target_pois_v1.csv"
MANIFEST = GOLD / "manifest.json"
EXPECTED_SHA = "3703931627d410f5fbda6540c89783e71bac4f1da4bdbb21c76188547961e5a4"


def main() -> None:
    raw = CSV.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    q = pd.read_csv(CSV)
    p = pd.read_csv(POI)
    assert len(p) == 180 and p.case_id.nunique() == 180
    assert len(q) == 1080 and q.case_id.nunique() == 180
    assert (q.groupby("case_id").size() == 6).all()
    assert sha == EXPECTED_SHA, f"SHA mismatch: {sha}"
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "ok": True,
                "n_pois": len(p),
                "n_queries": len(q),
                "sha256": sha,
                "status": man.get("status"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
