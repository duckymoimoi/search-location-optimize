"""No-house candidate extraction must preserve street codes and unit boundaries."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "plan_gold_name_street.py"


def test_remove_house_preserves_street_number_and_unit_code():
    spec = importlib.util.spec_from_file_location("gold_name_street", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.remove_house("VIB 330 đường 3 Tháng 2", "330") == "VIB đường 3 Tháng 2"
    assert module.remove_house("Head Tan Long Van 4 167 Trần Quốc Thảo", "167") == "Head Tan Long Van 4 Trần Quốc Thảo"
    assert module.remove_house("Highlands SH16-130 San Hô 16", "SH16") is None
    assert module.remove_house("Highlands SH16-130 San Hô 16", "SH16-130") == "Highlands San Hô 16"
    assert module.street_core("Phố Nguyễn Hữu Thọ") == "nguyen huu tho"
