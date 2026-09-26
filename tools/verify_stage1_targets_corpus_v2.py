"""Verify Gold migration snapshot and active train targets against corpus v2."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/vietnam"
GOLD = DATA / "gold_stage1_v1_corpus_v2"
TRAIN = DATA / "train_stage1_20k"
CORPUS = DATA / "poi_corpus_v2"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    gold_manifest = json.loads((GOLD / "manifest.json").read_text(encoding="utf-8"))
    train_manifest = json.loads((TRAIN / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in gold_manifest["files"].items():
        assert digest(GOLD / name) == entry["sha256"], name
    for name, entry in train_manifest["files"].items():
        assert digest(TRAIN / name) == entry["sha256"], name
    live = set(pq.read_table(CORPUS / "pois_core.parquet", columns=["poi_id"])["poi_id"].to_pylist())
    gold_pois = pq.read_table(GOLD / "target_pois.parquet").to_pylist()
    gold_queries = pq.read_table(GOLD / "query_variants.parquet").to_pylist()
    train_pois = pq.read_table(TRAIN / "target_pois_20k.parquet").to_pylist()
    assert len(gold_pois) == len(rows_csv(GOLD / "target_pois.csv")) == 180
    assert len(gold_queries) == len(rows_csv(GOLD / "query_variants.csv")) == 1080
    assert len(train_pois) == len(rows_csv(TRAIN / "target_pois_20k.csv")) == 19939
    assert len({r["case_id"] for r in gold_pois}) == 180
    assert len({r["poi_id"] for r in gold_pois}) == 180
    assert len({r["case_id"] for r in train_pois}) == len(train_pois)
    assert len({r["poi_id"] for r in train_pois}) == len(train_pois)
    gold_by_case = {r["case_id"]: r["poi_id"] for r in gold_pois}
    query_counts = Counter()
    gold_positives = set()
    for row, csv_row in zip(gold_queries, rows_csv(GOLD / "query_variants.csv"), strict=True):
        assert row["variant_id"] == csv_row["variant_id"]
        assert row["query_text"] == csv_row["query_text"]
        assert row["intended_poi_id"] == gold_by_case[row["case_id"]] == csv_row["intended_poi_id"]
        acceptable = row["acceptable_poi_ids"]
        assert acceptable == csv_row["acceptable_poi_ids"].split("|")
        assert row["intended_poi_id"] in acceptable
        assert len(acceptable) == len(set(acceptable)) == row["n_acceptable"]
        assert row["is_multipositive"] == (len(acceptable) > 1)
        assert set(acceptable) <= live
        gold_positives.update(acceptable)
        query_counts[row["case_id"]] += 1
    assert set(query_counts) == set(gold_by_case) and set(query_counts.values()) == {6}
    assert {r["poi_id"] for r in gold_pois} <= live
    train_ids = {r["poi_id"] for r in train_pois}
    assert train_ids <= live
    assert not train_ids & gold_positives
    assert train_manifest["total_target_pois"] == len(train_pois)
    assert train_manifest["strata_distribution"] == dict(Counter(r["primary_sampling_stratum"] for r in train_pois))
    assert train_manifest["regional_distribution"] == dict(Counter(r["region"] for r in train_pois))
    locked500 = set(pq.read_table(DATA / "train_stage1_queries_v6/staging/003_hard_noise_500/target_subset.parquet",
                                  columns=["poi_id"])["poi_id"].to_pylist())
    assert len(locked500) == 500 and locked500 <= train_ids
    print(json.dumps({"verdict": "PASS", "gold_pois": len(gold_pois),
                      "gold_queries": len(gold_queries), "train_pois": len(train_pois),
                      "gold_positive_overlap": len(train_ids & gold_positives),
                      "locked_500_retained": len(locked500)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
