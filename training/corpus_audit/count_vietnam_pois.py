"""Deprecated entrypoint — count reports write to data/vietnam/, not training/.

Canonical script:
  docs/deliveries/w1_evidence/scripts/run_poi_eda.py
  (PBF scan report: data/vietnam/vietnam_nationwide_poi_count_report.*)
"""
from __future__ import annotations

import sys
from pathlib import Path

HINT = Path(__file__).resolve().parents[2] / "docs/deliveries/w1_evidence/scripts"

if __name__ == "__main__":
    print(
        "NOTE: training/corpus_audit is deprecated for Vietnam POI counts.\n"
        f"Use scripts under {HINT} and read outputs in data/vietnam/.",
        file=sys.stderr,
    )
    sys.exit(2)
