"""Audit Kaggle weighting logic without invoking any optimizer or CUDA."""
import ast
from pathlib import Path
import random

import numpy as np
import pytest

source = Path(__file__).parents[1] / "kaggle/kernel_stage1_v6_hardneg_6k_devlock/run_train_stage1_v6_hardneg.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
names = {"configure_training_weights", "sample_epoch_rows"}
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
ns = {"random": random, "np": np, "apply_brand_epoch_sampling": lambda rows, seed: rows}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), ns)


def test_loss_only_does_not_downsample_hard_variants():
    rows = ns["configure_training_weights"]([{"sample_weight": .25}] * 100, "loss_only")
    assert len(ns["sample_epoch_rows"](rows, 42)) == 100
    assert all(r["loss_weight"] == .25 for r in rows)


def test_sampling_only_does_not_downweight_again():
    rows = ns["configure_training_weights"]([{"sample_weight": .25}] * 100, "sampling_only")
    assert all(r["loss_weight"] == 1 for r in rows)
    assert 0 < len(ns["sample_epoch_rows"](rows, 42)) < 100


def test_zero_weight_is_excluded_and_legacy_preserved():
    for mode in ("legacy_both", "loss_only", "sampling_only"):
        rows = ns["configure_training_weights"]([{"sample_weight": 0}], mode)
        assert ns["sample_epoch_rows"](rows, 42) == []
    row = ns["configure_training_weights"]([{"sample_weight": .25}], "legacy_both")[0]
    assert row["sampling_probability"] == row["loss_weight"] == .25
    with pytest.raises(ValueError):
        ns["configure_training_weights"]([{"sample_weight": float("nan")}], "loss_only")
