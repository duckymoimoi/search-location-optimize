from __future__ import annotations

import csv
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from serialize_stage1_v6 import serialize  # noqa: E402
from stage1_v6_common import (  # noqa: E402
    COMPOUND_PAIRS,
    ERROR_TAGS,
    SCHEMA_COLUMNS,
    normalize_query,
    strip_diacritics,
)
from validate_stage1_train_v6 import (  # noqa: E402
    _retained_context_labels,
    _slash_change_valid,
    _trace_has_early_mutation,
    _trace_has_token_boundary_change,
    validate_batch,
)


class Stage1V6ToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = self._write_valid_fixture()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_valid_fixture(self) -> dict[str, Path]:
        case_id = "train20k-00001"
        poi_id = "poi:1"
        canonical = "Trường THCS Quảng Phú Lâm Thao"
        query_rows = [
            self._row(
                case_id,
                "v01",
                canonical,
                canonical,
                "CLEAN",
                "canonical",
                "canonical_anchor",
                "CLEAN",
                "canonical_anchor",
                poi_id,
            ),
            self._row(
                case_id,
                "v02",
                "Trường THCS Quảng Phú",
                canonical,
                "ALIAS",
                "short_name",
                "standalone_or_natural_address",
                "CLEAN",
                "standalone_name",
                poi_id,
            ),
            self._row(
                case_id,
                "v03",
                "Tường THCS Quảng Phủ",
                canonical,
                "COMPOUND",
                "controlled_compound",
                "mechanical_typo+phonetic_confusion",
                "COMPOUND",
                "controlled_compound",
                poi_id,
            ),
            self._row(
                case_id,
                "v04",
                "Trờng trung học cơ sở Quảng Phú",
                canonical,
                "COMPOUND",
                "controlled_compound",
                "mechanical_typo+acronym_expand_contract",
                "COMPOUND",
                "controlled_compound",
                poi_id,
            ),
            self._row(
                case_id,
                "v05",
                "Trườngf Quảng Phú THCS",
                canonical,
                "COMPOUND",
                "controlled_compound",
                "ime_telex_residual+token_order_variant",
                "COMPOUND",
                "controlled_compound",
                poi_id,
            ),
            self._row(
                case_id,
                "v06",
                "Rtường THCS Phú",
                canonical,
                "COMPOUND",
                "controlled_compound",
                "mechanical_typo+safe_omission",
                "COMPOUND",
                "controlled_compound",
                poi_id,
            ),
        ]
        csv_path = self.root / "queries.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCHEMA_COLUMNS)
            writer.writeheader()
            for row in query_rows:
                csv_row = dict(row)
                csv_row["acceptable_poi_ids"] = json.dumps(
                    row["acceptable_poi_ids"], separators=(",", ":")
                )
                csv_row["is_multipositive"] = (
                    "true" if row["is_multipositive"] else "false"
                )
                writer.writerow(csv_row)
        parquet_path = self.root / "queries.parquet"
        pq.write_table(pa.Table.from_pylist(query_rows), parquet_path)

        target_path = self.root / "target.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "case_id": case_id,
                        "poi_id": poi_id,
                        "name": "Trường THCS Quảng Phú",
                        "brand": None,
                        "ref": None,
                        "category": "amenity=school",
                        "province": "Bắc Ninh",
                        "subdistrict": "Lâm Thao",
                        "housenumber": None,
                        "street": None,
                        "address_text": "Lâm Thao, Bắc Ninh",
                        "address_status": "direct",
                        "primary_sampling_stratum": "named_clear",
                        "region": "North",
                        "clean_reason": "fixture",
                        "clean_pass": True,
                    }
                ]
            ),
            target_path,
        )
        corpus_path = self.root / "corpus.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "poi_id": poi_id,
                        "name": "Trường THCS Quảng Phú",
                        "aliases": [],
                        "brand": None,
                        "ref": None,
                        "destination_searchable": True,
                    }
                ]
            ),
            corpus_path,
        )
        gold_path = self.root / "gold.parquet"
        pq.write_table(pa.Table.from_pylist([{"poi_id": "poi:gold"}]), gold_path)

        trace_path = self.root / "trace.jsonl"
        traces = [
            self._trace(
                f"{case_id}-v03",
                f"{case_id}-v02",
                ["mechanical_typo", "phonetic_confusion"],
                query_rows[1]["query_text"],
                query_rows[2]["query_text"],
                ["Trường -> Tường", "Phú -> Phủ"],
            ),
            self._trace(
                f"{case_id}-v04",
                f"{case_id}-v02",
                ["mechanical_typo", "acronym_expand_contract"],
                query_rows[1]["query_text"],
                query_rows[3]["query_text"],
                ["Trư -> Tr", "THCS -> trung học cơ sở"],
            ),
            self._trace(
                f"{case_id}-v05",
                f"{case_id}-v02",
                ["ime_telex_residual", "token_order_variant"],
                query_rows[1]["query_text"],
                query_rows[4]["query_text"],
                ["ường -> ườngf", "THCS Quảng Phú -> Quảng Phú THCS"],
            ),
            self._trace(
                f"{case_id}-v06",
                f"{case_id}-v02",
                ["mechanical_typo", "safe_omission"],
                query_rows[1]["query_text"],
                query_rows[5]["query_text"],
                ["Tr -> Rt", "Quảng (omitted) -> "],
            ),
        ]
        trace_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in traces),
            encoding="utf-8",
        )
        return {
            "csv": csv_path,
            "parquet": parquet_path,
            "target": target_path,
            "corpus": corpus_path,
            "gold": gold_path,
            "trace": trace_path,
        }

    @staticmethod
    def _row(
        case_id: str,
        slot: str,
        query: str,
        canonical: str,
        family: str,
        operator: str,
        subtype: str,
        severity: str,
        slot_tag: str,
        poi_id: str,
    ) -> dict:
        return {
            "case_id": case_id,
            "variant_id": f"{case_id}-{slot}",
            "query_text": query,
            "canonical_query": canonical,
            "query_variant_family": family,
            "variant_operator": operator,
            "variant_subtype": subtype,
            "severity": severity,
            "query_types": f"named_clear|{slot_tag}|lang_vi",
            "intended_poi_id": poi_id,
            "acceptable_poi_ids": [poi_id],
            "primary_sampling_stratum": "named_clear",
            "review_status": "authored",
            "generator_version": "manual_authored_v6",
            "n_acceptable": 1,
            "is_multipositive": False,
        }

    @staticmethod
    def _trace(
        variant: str,
        parent: str,
        tags: list[str],
        before: str,
        after: str,
        spans: list[str],
    ) -> dict:
        return {
            "variant_id": variant,
            "parent_variant_id": parent,
            "error_tags": tags,
            "affected_spans": spans,
            "before_text": before,
            "after_text": after,
            "reviewer_status": "authored",
        }

    def _validate(self) -> dict:
        return validate_batch(
            csv_path=self.paths["csv"],
            parquet_path=self.paths["parquet"],
            trace_path=self.paths["trace"],
            target_path=self.paths["target"],
            corpus_path=self.paths["corpus"],
            gold_path=self.paths["gold"],
            published_paths=[],
            ban_acronym_case=True,
        )

    def test_valid_fixture_passes(self) -> None:
        report = self._validate()
        self.assertEqual("PASS", report["verdict"], report["errors"])
        self.assertEqual(
            {"CLEAN": 2, "COMPOUND": 4}, report["stats"]["severity"]
        )

    def test_wrong_v03_parent_fails(self) -> None:
        table = pq.read_table(self.paths["parquet"])
        rows = table.to_pylist()
        rows[2]["query_text"] = "Truong THCS Quang Phu Lam Thao"
        pq.write_table(pa.Table.from_pylist(rows), self.paths["parquet"])
        report = self._validate()
        self.assertEqual("FAIL", report["verdict"])
        self.assertTrue(
            any("CSV and Parquet rows differ" in error for error in report["errors"])
        )

    def test_common_normalizers(self) -> None:
        self.assertEqual("trường thcs", normalize_query("  TRƯỜNG   THCS "))
        self.assertEqual("Truong THCS", strip_diacritics("Trường THCS"))

    def test_identity_core_context_labels_are_reviewable(self) -> None:
        self.assertEqual(
            ["đường", "phường"],
            _retained_context_labels("350 Đường Lê Văn Thọ Phường 9"),
        )
        self.assertEqual([], _retained_context_labels("350 Lê Văn Thọ"))

    def test_spoken_slash_address_requires_explicit_tag(self) -> None:
        before = "30/48D Nguyễn Văn Linh"
        after = "Số 30 hẻm 48D Nguyễn Văn Linh"
        self.assertTrue(_slash_change_valid(before, after, ["slash_address_spoken"]))
        self.assertFalse(_slash_change_valid(before, after, ["safe_omission"]))
        self.assertFalse(
            _slash_change_valid(before, before, ["slash_address_spoken"])
        )

    def test_early_mutation_skips_immutable_digit_code_token(self) -> None:
        base = {
            "before_text": "A12-TT1 Five Star Mỹ Đình",
            "affected_spans": ["A -> E", "Star (omitted) -> ", "Mỹ -> Mỷ"],
        }
        self.assertFalse(_trace_has_early_mutation(base))
        base["affected_spans"] = [
            "Five -> Faiv",
            "Star (omitted) -> ",
            "Mỹ -> Mỷ",
        ]
        self.assertTrue(_trace_has_early_mutation(base))

    def test_token_boundary_trace_preserves_non_whitespace_characters(self) -> None:
        self.assertTrue(
            _trace_has_token_boundary_change(
                {"affected_spans": ["Bách Hóa -> BáchHóa"]}
            )
        )
        self.assertTrue(
            _trace_has_token_boundary_change(
                {"affected_spans": ["Highlands -> High lands"]}
            )
        )
        self.assertFalse(
            _trace_has_token_boundary_change(
                {"affected_spans": ["Bách Hóa -> BáhHóa"]}
            )
        )

    def test_operator_markdown_matches_deterministic_taxonomy(self) -> None:
        operators = (
            Path.cwd()
            / ".cursor/skills/search20-stage1-query-variants/operators.md"
        ).read_text(encoding="utf-8")
        tag_section = operators.split("## Controlled variation whitelist", 1)[1].split(
            "### Token boundary", 1
        )[0]
        documented_tags = set(
            re.findall(r"^\| `([^`]+)` \|", tag_section, flags=re.MULTILINE)
        )
        self.assertEqual(set(ERROR_TAGS), documented_tags)
        pair_section = operators.split("## Compatible pairs", 1)[1].split(
            "## Difficulty", 1
        )[0]
        documented_pairs = {
            frozenset(match.groups())
            for line in pair_section.splitlines()
            if (match := re.fullmatch(r"([a-z_]+) \+ ([a-z_]+)", line.strip()))
        }
        self.assertEqual(set(COMPOUND_PAIRS), documented_pairs)

    def test_serializer_writes_canonical_csv_and_typed_parquet(self) -> None:
        rows = pq.read_table(self.paths["parquet"]).to_pylist()
        source = self.root / "authored.jsonl"
        source.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        csv_path = self.root / "serialized.csv"
        parquet_path = self.root / "serialized.parquet"
        self.assertEqual(6, serialize(source, csv_path, parquet_path))
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            first = next(csv.DictReader(handle))
        self.assertEqual('["poi:1"]', first["acceptable_poi_ids"])
        self.assertEqual("false", first["is_multipositive"])
        schema = pq.read_schema(parquet_path)
        self.assertTrue(pa.types.is_list(schema.field("acceptable_poi_ids").type))
        self.assertTrue(pa.types.is_boolean(schema.field("is_multipositive").type))

if __name__ == "__main__":
    unittest.main()
