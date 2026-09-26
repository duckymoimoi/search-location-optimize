"""Contract checks for evidence-based Gold v2.1 coverage diagnostics."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "audit_gold_stage1_v21_coverage.py"


def test_keyboard_neighbor_trace_requires_real_adjacent_substitution():
    spec = importlib.util.spec_from_file_location("gold_v21_coverage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.keyboard_neighbor_trace("early:Vincom→Vincon")
    assert module.keyboard_neighbor_trace("Thái→Tháo")
    assert not module.keyboard_neighbor_trace("early:Highlands→Highland")
    assert not module.keyboard_neighbor_trace("early:Nguyễn→Nguyen")
