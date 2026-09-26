from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from build_brand_groups_v1 import build as build_groups  # noqa: E402
from build_brand_authoring_packet_v1 import build as build_brand_packet  # noqa: E402
from build_brand_lookup_v2 import build as build_lookup  # noqa: E402
from build_stage1_authoring_packet import build as build_packet  # noqa: E402
from query_brand_lookup_v2 import lookup_text  # noqa: E402
from validate_brand_authoring_packet_v1 import (  # noqa: E402
    validate as validate_brand_packet,
)


class BrandAuthoringPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus.parquet"
        rows = [
            {
                "poi_id": "poi:1",
                "name": "Eneos",
                "aliases": ["Eneos Nguyễn Oanh"],
                "brand": "Eneos",
                "ref": None,
                "category": "amenity=fuel",
                "address": {
                    "housenumber": None,
                    "street": "Nguyễn Oanh",
                    "subdistrict": "An Nhơn",
                    "province": "TP.HCM",
                },
                "province_region_id": "province:hcm",
                "subdistrict_region_id": "ward:an_nhon",
                "destination_searchable": True,
            },
            {
                "poi_id": "poi:2",
                "name": "Eneos",
                "aliases": [],
                "brand": "Eneos",
                "ref": None,
                "category": "amenity=fuel",
                "address": {
                    "housenumber": None,
                    "street": "Lê Văn Việt",
                    "subdistrict": "Tăng Nhơn Phú",
                    "province": "TP.HCM",
                },
                "province_region_id": "province:hcm",
                "subdistrict_region_id": "ward:tang_nhon_phu",
                "destination_searchable": True,
            },
            {
                "poi_id": "poi:3",
                "name": "Quán Cà Phê Độc Lập",
                "aliases": [],
                "brand": None,
                "ref": None,
                "category": "amenity=cafe",
                "address": {
                    "housenumber": "5",
                    "street": "Phố Huế",
                    "subdistrict": "Cửa Nam",
                    "province": "Hà Nội",
                },
                "province_region_id": "province:hanoi",
                "subdistrict_region_id": "ward:cua_nam",
                "destination_searchable": True,
            },
        ]
        pd.DataFrame(rows).to_parquet(self.corpus, index=False)
        self.overrides = self.root / "overrides.csv"
        with self.overrides.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["brand_fold", "decision", "note"])
            writer.writeheader()
            writer.writerow(
                {
                    "brand_fold": "eneos",
                    "decision": "accept_identity",
                    "note": "fixture",
                }
            )
        self.release = self.root / "brand_release"
        self.lookup = self.root / "brand_lookup"
        build_groups(self.corpus, self.overrides, self.release)
        build_lookup(self.release, self.lookup)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_packet_contains_fast_brand_context_and_exact_contract(self) -> None:
        target = self.root / "target.parquet"
        pd.DataFrame(
            [
                {
                    "case_id": "train20k-00001",
                    "poi_id": "poi:1",
                    "name": "Eneos",
                    "brand": "Eneos",
                    "ref": None,
                    "category": "amenity=fuel",
                    "housenumber": None,
                    "street": "Nguyễn Oanh",
                    "subdistrict": "An Nhơn",
                    "province": "TP.HCM",
                    "primary_sampling_stratum": "brand_branch",
                    "clean_pass": True,
                }
            ]
        ).to_parquet(target, index=False)
        packet = self.root / "packet.jsonl"
        manifest = self.root / "packet_manifest.json"
        build_packet(target, self.corpus, self.lookup, packet, manifest)
        row = json.loads(packet.read_text(encoding="utf-8").strip())
        membership = row["brand_context"]["accepted_memberships"][0]
        self.assertEqual("brand:eneos:fuel", membership["brand_group_id"])
        self.assertEqual(2, membership["group_accepted_count"])
        self.assertTrue(membership["requires_branch_discriminator"])
        self.assertEqual(
            2, row["collisions"]["exact_name_or_alias"]["searchable_count"]
        )
        contract = json.loads(manifest.read_text(encoding="utf-8"))[
            "authoring_contract"
        ]
        self.assertEqual(
            ["standalone_name", "natural_address"],
            contract["slot_specs"]["v02"]["accepted_slot_tags"],
        )
        self.assertIn("ime_telex_residual", contract["error_tags"])
        self.assertIn("token_order_variant", contract["error_tags"])

    def test_index_refuses_overwrite(self) -> None:
        with self.assertRaises(FileExistsError):
            build_lookup(self.release, self.lookup)

    def test_alias_candidate_is_not_promoted_to_accepted(self) -> None:
        connection = sqlite3.connect(self.lookup / "brand_lookup_v2.sqlite")
        try:
            result = lookup_text(connection, "Eneos Nguyễn Oanh", "fuel")
        finally:
            connection.close()
        self.assertFalse(result["has_accepted_decision"])
        self.assertTrue(result["hits"])
        self.assertTrue(
            all(hit["decision_status"] == "needs_review" for hit in result["hits"])
        )

    def test_brand_query_packet_has_one_group_and_complete_positive_pool(self) -> None:
        output = self.root / "brand_query_packet"
        manifest = build_brand_packet(self.release, self.lookup, output)
        packet_rows = [
            json.loads(line)
            for line in (output / "brand_authoring_packet_v1.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertEqual(1, len(packet_rows))
        row = packet_rows[0]
        self.assertEqual("brand:eneos:fuel", row["brand_group_id"])
        self.assertEqual("FAMILY_NAMESPACE", row["qrel_policy"])
        self.assertEqual(["fuel"], row["namespace_scope"])
        self.assertEqual(["poi:1", "poi:2"], row["positive_poi_ids"])
        self.assertEqual(2, row["n_positive"])
        self.assertEqual([], row["verified_aliases"])
        self.assertEqual(1, row["alias_review"]["candidate_count"])
        self.assertFalse(row["requires_namespace_token"])
        self.assertEqual(1, manifest["stats"]["packet_rows"])
        report = validate_brand_packet(output, self.release, self.lookup)
        self.assertEqual("PASS", report["verdict"], report["errors"])
        with self.assertRaises(FileExistsError):
            build_brand_packet(self.release, self.lookup, output)


if __name__ == "__main__":
    unittest.main()
