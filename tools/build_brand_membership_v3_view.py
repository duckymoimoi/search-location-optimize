"""Build a corpus-v3 compatible brand membership view. Does not edit brand v1."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from compose_poi_id_migration_v1_v3 import compose as compose_maps
from stage1_brand_v3_common import (
    BRAND_V1,
    CORPUS_V3,
    GOLD_POI,
    LEFT_OVER_FAMILIES,
    MEMBERSHIP_V3,
    MEMBERSHIP_VIEW_VERSION,
    PACKET_V2,
    STAGING_V1,
    GROUP_VERSION,
    CORPUS_VERSION,
    load_v3_core,
    refuse_nonempty,
    remap_lookup,
    sha256_file,
    source_record,
    write_json,
)
from stage1_brand_query_v1_common import read_jsonl


MEMBER_COLUMNS = [
    "brand_family_id",
    "brand_group_id",
    "brand_canonical",
    "brand_fold",
    "brand_namespace",
    "poi_id",
    "source_poi_id",
    "mapped_poi_id",
    "mapping_action",
    "mapping_evidence",
    "destination_searchable",
    "province_region_id",
    "subdistrict_region_id",
    "membership_status",
    "membership_evidence",
    "evidence_text",
    "group_version",
    "review_status",
]


def build(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    composed_path = output_dir / "composed_poi_id_migration_v1_v3.parquet"
    if not composed_path.exists():
        compose_maps(output_dir)
    composed = pd.read_parquet(composed_path)
    core = load_v3_core()
    v3_ids = set(core["poi_id"].astype(str))
    searchable = {
        str(row.poi_id): bool(row.destination_searchable)
        for row in core.itertuples(index=False)
    }
    entity_by = {
        str(row.poi_id): str(row.entity_group_id)
        for row in core.itertuples(index=False)
    }
    remap = remap_lookup(composed, v3_ids)
    members = pd.read_parquet(BRAND_V1 / "brand_group_members_v1.parquet")
    gold = pd.read_parquet(GOLD_POI / "target_pois_v2_1.parquet")
    qrels = pd.read_parquet(STAGING_V1 / "brand_query_qrels_v1.parquet")
    queries = pd.read_parquet(STAGING_V1 / "brand_intent_queries_v1.parquet")
    packet = read_jsonl(PACKET_V2)

    gold_ids = set(gold["poi_id"].astype(str))
    gold_ents = set(gold["entity_group_id"].astype(str))
    accepted = members[members["membership_status"] == "accepted"].copy()
    accepted_ids = set(accepted["poi_id"].astype(str))
    missing_direct = sorted(pid for pid in accepted_ids if pid not in v3_ids)

    view_rows: list[dict] = []
    seen_group_dest: dict[str, set[str]] = defaultdict(set)
    unmapped: list[dict] = []
    recovered = 0
    collapsed = 0
    for row in members.itertuples(index=False):
        source_id = str(row.poi_id)
        dest, action, evidence = remap.get(source_id, (None, "no_map", ""))
        if dest is None and source_id in v3_ids:
            dest, action, evidence = source_id, "already_in_v3", ""
        status = str(row.membership_status)
        if dest is None:
            if status == "accepted":
                unmapped.append(
                    {
                        "source_poi_id": source_id,
                        "brand_family_id": str(row.brand_family_id),
                        "brand_group_id": str(row.brand_group_id),
                        "brand_canonical": str(row.brand_canonical),
                        "mapping_action": action,
                        "mapping_evidence": evidence,
                        "decision": "dropped_no_successor",
                    }
                )
            continue
        if dest != source_id:
            recovered += 1
        key = f"{row.brand_group_id}|{status}"
        if dest in seen_group_dest[key]:
            collapsed += 1
            continue
        seen_group_dest[key].add(dest)
        view_rows.append(
            {
                "brand_family_id": str(row.brand_family_id),
                "brand_group_id": str(row.brand_group_id),
                "brand_canonical": str(row.brand_canonical),
                "brand_fold": str(row.brand_fold),
                "brand_namespace": str(row.brand_namespace),
                "poi_id": dest,
                "source_poi_id": source_id,
                "mapped_poi_id": dest,
                "mapping_action": action,
                "mapping_evidence": evidence,
                "destination_searchable": bool(searchable.get(dest, False)),
                "province_region_id": row.province_region_id,
                "subdistrict_region_id": row.subdistrict_region_id,
                "membership_status": status,
                "membership_evidence": str(row.membership_evidence),
                "evidence_text": str(row.evidence_text),
                "group_version": GROUP_VERSION,
                "review_status": str(row.review_status),
            }
        )

    view = pd.DataFrame(view_rows, columns=MEMBER_COLUMNS)
    view = view.sort_values(
        ["brand_family_id", "brand_group_id", "membership_status", "poi_id"],
        kind="stable",
    ).reset_index(drop=True)
    members_path = output_dir / "brand_group_members_v3.parquet"
    pq.write_table(pa.Table.from_pandas(view, preserve_index=False), members_path, compression="zstd")

    accepted_view = view[view["membership_status"] == "accepted"]
    qrel_ids = set(qrels["poi_id"].astype(str))
    qrel_missing = sorted(pid for pid in (qrel_ids & accepted_ids) if pid not in v3_ids)
    affected = int(
        qrels[qrels["poi_id"].astype(str).isin(set(qrel_missing))]["query_id"].nunique()
    )
    lost_all = 0
    for _, ids in qrels.groupby("query_id")["poi_id"]:
        if not any(str(pid) in v3_ids for pid in ids):
            lost_all += 1

    mapped_accepted = set(accepted_view["poi_id"].astype(str))
    gold_overlap = sorted(gold_ids & accepted_ids)
    gold_overlap_v3 = sorted(gold_ids & mapped_accepted)
    same_ent = set(
        core[core["entity_group_id"].astype(str).isin(gold_ents)]["poi_id"].astype(str)
    )
    extra_eq = sorted((same_ent & mapped_accepted) - gold_ids)

    query_fams = set(queries["brand_family_id"].astype(str))
    accepted_fams = set(accepted["brand_family_id"].astype(str))
    leftover = sorted(accepted_fams - query_fams)

    audit = {
        "missing_direct_accepted": len(missing_direct),
        "qrel_accepted_missing_direct": len(qrel_missing),
        "queries_with_missing_positive": affected,
        "queries_losing_all_positives_without_remap": lost_all,
        "accepted_source_rows": int(len(accepted)),
        "accepted_mapped_rows": int(len(accepted_view)),
        "accepted_unique_v3": int(accepted_view["poi_id"].nunique()),
        "recovered_or_changed_ids": recovered,
        "collapsed_duplicate_dest_rows": collapsed,
        "unmapped_accepted": len(unmapped),
        "leftover_families_without_queries": leftover,
        "leftover_family_reasons": LEFT_OVER_FAMILIES,
        "packet_intents": len(packet),
        "staging_intents": int(queries["intent_id"].nunique()),
    }
    write_json(output_dir / "id_migration_audit.json", audit)
    write_json(
        output_dir / "missing_id_adjudication.json",
        {
            "policy": "Transfer a positive only when v1→v2→v3 proves the same POI. Do not invent a successor.",
            "rows": unmapped,
        },
    )
    overlap_rows = []
    for poi_id in gold_overlap_v3:
        sub = accepted_view[accepted_view["poi_id"] == poi_id]
        gold_row = gold[gold["poi_id"] == poi_id].iloc[0]
        overlap_rows.append(
            {
                "poi_id": poi_id,
                "entity_group_id": str(gold_row.entity_group_id),
                "brand_family_id": str(sub.iloc[0].brand_family_id) if len(sub) else "",
                "brand_group_id": str(sub.iloc[0].brand_group_id) if len(sub) else "",
                "name": str(gold_row.name),
            }
        )
    write_json(
        output_dir / "gold_poi_overlap.json",
        {
            "n_gold_targets": int(len(gold_ids)),
            "n_overlap_source_ids": len(gold_overlap),
            "n_overlap_v3_ids": len(gold_overlap_v3),
            "n_families": len({row["brand_family_id"] for row in overlap_rows}),
            "extra_entity_equivalent_accepted": extra_eq,
            "rows": overlap_rows,
        },
    )

    completed = datetime.now(UTC)
    manifest = {
        "dataset": "train_stage1_brand_membership_v3",
        "membership_view_version": MEMBERSHIP_VIEW_VERSION,
        "group_version": GROUP_VERSION,
        "status": "VALIDATED",
        "created_at_utc": completed.isoformat(),
        "corpus_version": CORPUS_VERSION,
        "scope": "sidecar membership view; does not replace locked brand_groups_v1",
        "sources": {
            "brand_group_members_v1": source_record(BRAND_V1 / "brand_group_members_v1.parquet"),
            "brand_v1_manifest": source_record(BRAND_V1 / "manifest.json"),
            "composed_migration": source_record(composed_path),
            "pois_core_v3": source_record(CORPUS_V3 / "pois_core.parquet"),
            "gold_targets_v2_1": source_record(GOLD_POI / "target_pois_v2_1.parquet"),
        },
        "counts": {
            "membership_rows": int(len(view)),
            "accepted_rows": int(len(accepted_view)),
            "needs_review_rows": int((view["membership_status"] == "needs_review").sum()),
            "excluded_rows": int((view["membership_status"] == "excluded").sum()),
            "accepted_unique_poi": int(accepted_view["poi_id"].nunique()),
            "accepted_families": int(accepted_view["brand_family_id"].nunique()),
            "accepted_groups": int(accepted_view["brand_group_id"].nunique()),
            "unmapped_accepted": len(unmapped),
        },
        "artifacts": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (
                members_path,
                output_dir / "id_migration_audit.json",
                output_dir / "missing_id_adjudication.json",
                output_dir / "gold_poi_overlap.json",
            )
        },
    }
    write_json(output_dir / "manifest.json", manifest)
    write_json(
        output_dir / "LOCKED.json",
        {
            "membership_view_version": MEMBERSHIP_VIEW_VERSION,
            "status": "locked",
            "locked_at_utc": completed.isoformat(),
            "manifest_sha256": sha256_file(output_dir / "manifest.json"),
            "mutation_policy": "Do not edit in place; rebuild as brand_membership_v4.",
        },
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=MEMBERSHIP_V3)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args()
    if not args.allow_existing:
        refuse_nonempty(args.output_dir)
    print(json.dumps(build(args.output_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
