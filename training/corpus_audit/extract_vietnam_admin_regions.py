"""Deprecated entrypoint — admin artifacts live under data/vietnam/, not training/.

Canonical script:
  docs/deliveries/w1_evidence/scripts/extract_vietnam_admin_regions.py
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

CANONICAL = (
    Path(__file__).resolve().parents[2]
    / "docs/deliveries/w1_evidence/scripts/extract_vietnam_admin_regions.py"
)

if __name__ == "__main__":
    print(
        "NOTE: training/corpus_audit is deprecated for Vietnam admin extracts.\n"
        f"Forwarding to {CANONICAL}",
        file=sys.stderr,
    )
    runpy.run_path(str(CANONICAL), run_name="__main__")
