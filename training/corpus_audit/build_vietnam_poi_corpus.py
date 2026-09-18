"""Deprecated entrypoint — corpus lives under data/vietnam/, not training/.

Canonical script:
  docs/deliveries/w1_evidence/scripts/build_vietnam_poi_corpus.py
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

CANONICAL = (
    Path(__file__).resolve().parents[2]
    / "docs/deliveries/w1_evidence/scripts/build_vietnam_poi_corpus.py"
)

if __name__ == "__main__":
    print(
        "NOTE: training/corpus_audit is deprecated for Vietnam corpus builds.\n"
        f"Forwarding to {CANONICAL}",
        file=sys.stderr,
    )
    runpy.run_path(str(CANONICAL), run_name="__main__")
