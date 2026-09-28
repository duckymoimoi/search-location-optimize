"""Read-only EDA of current local datasets; no model training or label mutation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/vietnam"
CATEGORICAL = {"split", "query_role", "difficulty", "review_status", "query_variant_family", "severity",
               "primary_sampling_stratum", "category", "province", "address_status", "namespace",
               "membership_status", "match_status", "geometry_status", "admin_level", "relation",
               "label", "negative_source", "source_dataset", "sample_weight", "routing_point_status",
               "pickup_access_verified", "destination_searchable", "intent_scope", "exposure_class"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normal(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def parse_ids(value):
    if isinstance(value, str):
        return json.loads(value) if value.startswith("[") else value.split("|")
    return list(value or [])


def role(path):
    name = path.as_posix()
    if "gold_stage1_v2_1" in name:
        return "historical_lineage_incomplete_provenance"
    if "gold_stage1_v2_2" in name:
        return "active_gold_reissue_not_new_holdout"
    if "hardneg_6k_clean" in name:
        return "active_devlock_training_pack_local"
    if "hardneg_" in name:
        return "historical_diagnostic_pack"
    return "current_source_or_derived_view"


def profile(path):
    source = pq.ParquetFile(path)
    cols = source.schema_arrow.names
    nulls = Counter(); blank = Counter(); freq = {c: Counter() for c in cols if c in CATEGORICAL}
    keys = {c: set() for c in ("query_id", "poi_id", "case_id", "brand_family_id") if c in cols}
    qlens = []; tokens = []; raw_queries = Counter(); norm_queries = Counter()
    for batch in source.iter_batches(batch_size=65536):
        for c in cols:
            arr = batch.column(c)
            nulls[c] += arr.null_count
            if pa.types.is_string(arr.type) or pa.types.is_large_string(arr.type):
                blank[c] += pc.sum(pc.cast(pc.fill_null(pc.equal(pc.utf8_trim_whitespace(arr), ""), False), pa.int64())).as_py() or 0
            if c in freq:
                for value in pc.value_counts(arr).to_pylist():
                    freq[c][str(value["values"])] += value["counts"]
            if c in keys:
                keys[c].update(x for x in arr.to_pylist() if x is not None)
        if "query_text" in cols:
            for value in batch.column("query_text").to_pylist():
                value = value or ""
                qlens.append(len(value)); tokens.append(len(value.split()))
                raw_queries[value] += 1; norm_queries[normal(value)] += 1
    result = {"path": path.relative_to(ROOT).as_posix(), "role": role(path), "rows": source.metadata.num_rows,
              "bytes": path.stat().st_size, "sha256": digest(path), "columns": cols,
              "null_counts": dict(nulls), "blank_string_counts": dict(blank),
              "distinct_keys": {c: len(v) for c, v in keys.items()},
              "distributions": {c: dict(v.most_common(20)) for c, v in freq.items()},
              "distribution_distinct_counts": {c: len(v) for c, v in freq.items()}}
    if qlens:
        result["query_text"] = {"characters_p50_p95_max": np.quantile(qlens, [.5, .95, 1]).tolist(),
                                "tokens_p50_p95_max": np.quantile(tokens, [.5, .95, 1]).tolist(),
                                "duplicate_raw_rows_beyond_first": sum(v-1 for v in raw_queries.values()),
                                "duplicate_normalized_rows_beyond_first": sum(v-1 for v in norm_queries.values()),
                                "normalizer": "NFKC + casefold + collapse whitespace; accents preserved"}
    return result


def special_audits():
    core = pq.read_table(DATA / "poi_corpus_v3/pois_core.parquet").to_pylist()
    corpus_ids = {r["poi_id"] for r in core}
    docs = set(pq.read_table(DATA / "poi_corpus_v3/search_documents.parquet", columns=["poi_id"])["poi_id"].to_pylist())
    names = Counter(normal(r["name"]) for r in core)
    invalid_points = 0
    for r in core:
        p = r["ranking_point"] or {}
        lat, lon = p.get("lat"), p.get("lon")
        invalid_points += lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180)
    gold_folder = DATA / "stage1_eval_suite_v2/gold_stage1_v2_2"
    gold = pq.read_table(gold_folder / "query_sessions_v2_2.parquet").to_pylist()
    gold_ids = set().union(*(set(r["acceptable_poi_ids"]) for r in gold))
    gold_text = {normal(r["query_text"]) for r in gold}
    audits = {"corpus": {"rows": len(core), "unique_poi_ids": len(corpus_ids), "search_document_id_set_matches": docs == corpus_ids,
                         "invalid_or_missing_ranking_points": invalid_points,
                         "pois_in_nonunique_normalized_name_groups": sum(n for k, n in names.items() if k and n > 1),
                         "top_repeated_names": names.most_common(15),
                         "note": "Name collisions indicate ambiguity; do not imply duplicate entities."}, "training_packs": {}}
    for folder in sorted(DATA.glob("train_stage1_v6_hardneg_*")):
        view = folder / "query_train_view.parquet"
        if not view.exists():
            continue
        rows = pq.read_table(view).to_pylist()
        train = [r for r in rows if r["split"] == "train"]
        dev = [r for r in rows if r["split"] == "dev"]
        positives = {r["intended_poi_id"] for r in train}
        train_qids = {r["query_id"] for r in train}
        train_accepted = set().union(*(set(parse_ids(r["acceptable_poi_ids"])) for r in train))
        held = {r["intended_poi_id"] for r in dev}
        pair_counts = Counter(); pair_gold = Counter(); unknown = 0; pair_dev_queries = 0
        pairs = pq.ParquetFile(folder / "training_pairs.parquet")
        for batch in pairs.iter_batches(columns=["query_id", "poi_id", "label"]):
            for r in batch.to_pylist():
                label = str(r["label"]);pair_counts[label] += 1
                pair_gold[label] += r["poi_id"] in gold_ids
                unknown += r["poi_id"] not in corpus_ids
                pair_dev_queries += r["query_id"] not in train_qids
        audits["training_packs"][folder.name] = {
            "train_queries": len(train), "dev_queries": len(dev),
            "train_dev_intended_poi_overlap": len(positives & held),
            "train_dev_normalized_text_overlap": len({normal(r["query_text"]) for r in train} & {normal(r["query_text"]) for r in dev}),
            "train_positive_gold_overlap": len(train_accepted & gold_ids),
            "train_gold_normalized_text_overlap": len({normal(r["query_text"]) for r in train} & gold_text),
            "pair_label_counts": dict(pair_counts), "pair_rows_with_gold_positive_poi_by_label": dict(pair_gold),
            "pair_poi_outside_corpus": unknown, "pair_query_outside_train_split": pair_dev_queries,
            "note": "Checks current file contents; does not retroactively certify which pack trained a historical checkpoint."}
    split = json.loads((DATA / "train_stage1_brand_splits_v1/family_split.json").read_text(encoding="utf-8"))
    assignment = {r["brand_family_id"]: r["split"] for r in split["families"]}
    brand = pq.read_table(DATA / "train_stage1_brand_queries_v3/brand_intent_queries_v3.parquet").to_pylist()
    gold_brand = pq.read_table(DATA / "stage1_eval_suite_v2/gold_stage1_brand_v1/brand_queries_v1.parquet").to_pylist()
    gold_families = {r["brand_family_id"] for r in gold_brand}
    members = pq.read_table(DATA / "train_stage1_brand_membership_v3/brand_group_members_v3.parquet").to_pylist()
    accepted = [r for r in members if r["membership_status"] == "accepted"]
    member_ids = {r["mapped_poi_id"] or r["poi_id"] for r in accepted}
    audits["brand"] = {"family_split_counts": dict(Counter(assignment.values())),
                       "duplicate_family_assignments": len(split["families"]) - len(assignment),
                       "query_split_counts": dict(Counter(assignment.get(r["brand_family_id"], "unassigned") for r in brand)),
                       "gold_families": len(gold_families),
                       "gold_family_not_test": sorted(f for f in gold_families if assignment.get(f) != "test"),
                       "accepted_member_rows": len(accepted), "accepted_unique_destination_ids": len(member_ids),
                       "accepted_ids_outside_corpus": len(member_ids-corpus_ids)}
    return audits


def main(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    tables = []
    for path in sorted(DATA.rglob("*.parquet")):
        if "staging" in path.parts:
            continue
        tables.append(profile(path))
        print("Profiled", path.relative_to(DATA), flush=True)
    report = {"schema_version": "current-datasets-eda-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runner_sha256": digest(__file__), "scope": "All local data/vietnam Parquet except staging; no training; no label changes",
              "tables": tables, "audits": special_audits(),
              "limits": ["Statistics are descriptive, not independent factual label review.",
                         "Top categorical values are truncated to 20; row counts, nulls and split audits use all rows.",
                         "No real-traffic query distribution or verified behavioral training log is established by these datasets."]}
    (out / "dataset_eda.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("EDA complete:", len(tables), "tables", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    main(parser.parse_args())
