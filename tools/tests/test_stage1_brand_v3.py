from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
KERNEL = TOOLS.parent / "training/kaggle/kernel_stage1_v6_hardneg_6k_devlock"
if str(KERNEL) not in sys.path:
    sys.path.insert(0, str(KERNEL))

from stage1_brand_v3_common import compose_migration, family_stratum  # noqa: E402
from run_train_stage1_v6_hardneg import apply_brand_epoch_sampling, sample_pool_positives  # noqa: E402


class BrandV3HelpersTests(unittest.TestCase):
    def test_compose_keeps_and_drops(self) -> None:
        mig2 = pd.DataFrame(
            [
                {"old_poi_id": "a", "canonical_poi_id": "a", "action": "keep", "reason": "", "old_name": "", "new_name": "", "distance_to_canonical_m": 0},
                {"old_poi_id": "b", "canonical_poi_id": "c", "action": "merge_duplicate", "reason": "dup", "old_name": "", "new_name": "", "distance_to_canonical_m": 1},
                {"old_poi_id": "d", "canonical_poi_id": "d", "action": "keep", "reason": "", "old_name": "", "new_name": "", "distance_to_canonical_m": 0},
            ]
        )
        mig3 = pd.DataFrame(
            [
                {"old_poi_id": "a", "canonical_poi_id": "a", "action": "keep", "reason": "", "old_name": "", "new_name": "", "distance_to_canonical_m": 0},
                {"old_poi_id": "d", "canonical_poi_id": "d", "action": "drop_junk_or_foreign", "reason": "outside_admin_vn", "old_name": "", "new_name": "", "distance_to_canonical_m": 0},
            ]
        )
        composed = compose_migration(mig2, mig3, {"a", "c"})
        by_source = {row.source_poi_id: row for row in composed.itertuples(index=False)}
        self.assertEqual(by_source["a"].mapped_poi_id, "a")
        self.assertEqual(by_source["b"].mapped_poi_id, "c")
        self.assertEqual(by_source["d"].composed_action, "dropped_no_successor")

    def test_stratum_and_sampler(self) -> None:
        self.assertTrue(family_stratum(100, 2, "ACB").startswith("xl|multi_ns"))
        rng = random.Random(0)
        chosen = sample_pool_positives(["p1", "p2", "p3", "p4", "p5"], rng)
        self.assertTrue(2 <= len(chosen) <= 4)
        rows = apply_brand_epoch_sampling(
            [
                {
                    "intent_scope": "BRAND",
                    "positive_pool": ["p1", "p2", "p3", "p4"],
                    "positives": ["p1", "p2", "p3", "p4"],
                    "ignore": ["gold"],
                }
            ],
            seed=7,
        )
        self.assertEqual(len(rows[0]["positives"]), len(set(rows[0]["positives"])))
        self.assertTrue(set(rows[0]["positives"]).isdisjoint(set(rows[0]["ignore"]) - {"gold"}))
        self.assertIn("gold", rows[0]["ignore"])


if __name__ == "__main__":
    unittest.main()
