#!/usr/bin/env python3
"""Compile experimental train views for the v6 hard-negative pilot.

Read-only on published v6 / brand / corpus. Writes only to
data/vietnam/train_stage1_v6_hardneg_pilot/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
TRAIN_CSV = ROOT / "data" / "vietnam" / "train_stage1_queries_v6" / "query_variants.csv"
TRAIN_MANIFEST = ROOT / "data" / "vietnam" / "train_stage1_queries_v6" / "manifest.json"
CORPUS = ROOT / "data" / "vietnam" / "poi_corpus_v3"
BRAND_MEMBERS = (
    ROOT / "data" / "vietnam" / "train_stage1_brand_membership_v3" / "brand_group_members_v3.parquet"
)
OUT = ROOT / "data" / "vietnam" / "train_stage1_v6_hardneg_pilot"
GOLD_DIR = ROOT / "data" / "vietnam" / "stage1_eval_suite_v2" / "gold_stage1_v2_1"

EXCLUDED_CASES = {
    "train20k-02003": (
        "intended osm:node/5608881031 merges into a different PNJ branch on v3"
    )
}
SLOT_WEIGHT = {
    "v01": 1.0,
    "v02": 1.0,
    "v03": 0.25,
    "v04": 0.25,
    "v05": 0.25,
    "v06": 0.25,
}
SPLIT_SEED = 42
DEV_CASE_FRACTION = 0.1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ids(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    if hasattr(raw, "tolist") and not isinstance(raw, str):
        return [str(item) for item in raw.tolist()]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def remap_id(poi_id: str, corpus_ids: set[str], migration: dict[str, str]) -> str | None:
    if poi_id in corpus_ids:
        return poi_id
    mapped = migration.get(poi_id)
    if mapped and mapped in corpus_ids:
        return mapped
    return None


def slot_of(variant_id: str) -> str:
    return str(variant_id).rsplit("-", 1)[-1]


def case_number(case_id: str) -> int:
    tail = str(case_id).rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 10**9


def load_holdout_ids(gold_dir: Path) -> set[str]:
    sessions = gold_dir / "query_sessions_v2_1.parquet"
    frame = pd.read_parquet(sessions, columns=["intended_poi_id", "acceptable_poi_ids"])
    ids = set(frame["intended_poi_id"].astype(str))
    for raw in frame["acceptable_poi_ids"]:
        ids.update(parse_ids(raw))
    targets = pd.read_parquet(gold_dir / "target_pois_v2_1.parquet", columns=["poi_id"])
    ids.update(targets["poi_id"].astype(str))
    ids.discard("")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--slot-weight",
        default="",
        help="Override slot weights, e.g. v01=1,v02=1,v03=0.5,v04=0.25,v05=0.5,v06=0.25",
    )
    parser.add_argument(
        "--holdout-gold",
        default=str(GOLD_DIR),
        help="Gold release directory whose POI ids are removed from train views. Empty disables.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Keep cases whose numeric suffix is <= N (train20k-00001). 0 keeps every published case.",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    slot_weight = dict(SLOT_WEIGHT)
    if args.slot_weight.strip():
        for part in args.slot_weight.split(","):
            slot, value = part.split("=", 1)
            slot_weight[slot.strip()] = float(value)

    for path in (
        TRAIN_CSV,
        TRAIN_MANIFEST,
        CORPUS / "search_documents.parquet",
        CORPUS / "pois_core.parquet",
        CORPUS / "poi_id_migration.parquet",
        CORPUS / "manifest.json",
        BRAND_MEMBERS,
    ):
        if not path.exists():
            raise SystemExit(f"Missing input: {path}")

    out.mkdir(parents=True, exist_ok=True)

    docs = pd.read_parquet(CORPUS / "search_documents.parquet", columns=["poi_id"])
    core = pd.read_parquet(
        CORPUS / "pois_core.parquet",
        columns=["poi_id", "entity_group_id"],
    )
    mig_table = pd.read_parquet(
        CORPUS / "poi_id_migration.parquet",
        columns=["old_poi_id", "canonical_poi_id"],
    )
    members = pd.read_parquet(BRAND_MEMBERS)
    train = pd.read_csv(TRAIN_CSV)

    corpus_ids = set(docs["poi_id"].astype(str))
    migration = {
        str(row.old_poi_id): str(row.canonical_poi_id)
        for row in mig_table.itertuples(index=False)
    }
    entity_by_id = dict(zip(core["poi_id"].astype(str), core["entity_group_id"].astype(str)))

    accepted_group: dict[str, str] = {}
    group_accepted: dict[str, set[str]] = defaultdict(set)
    group_ignore: dict[str, set[str]] = defaultdict(set)
    family_of_group: dict[str, str] = {}
    for row in members.itertuples(index=False):
        poi = remap_id(str(row.poi_id), corpus_ids, migration)
        if poi is None:
            continue
        group_id = str(row.brand_group_id)
        family_of_group[group_id] = str(row.brand_family_id)
        status = str(row.membership_status)
        if status == "accepted":
            accepted_group[poi] = group_id
            group_accepted[group_id].add(poi)
        elif status == "needs_review":
            group_ignore[group_id].add(poi)

    holdout_ids: set[str] = set()
    holdout_dir = str(args.holdout_gold or "").strip()
    if holdout_dir:
        gold_dir = Path(holdout_dir)
        if not gold_dir.is_absolute():
            gold_dir = ROOT / gold_dir
        if not (gold_dir / "query_sessions_v2_1.parquet").exists():
            raise SystemExit(f"Missing Gold sessions: {gold_dir}")
        holdout_ids = load_holdout_ids(gold_dir)
    if args.max_cases:
        train = train.loc[train["case_id"].map(lambda value: case_number(str(value)) <= args.max_cases)].copy()

    cases = sorted({str(cid) for cid in train["case_id"] if str(cid) not in EXCLUDED_CASES})
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(cases)
    n_dev = max(1, int(round(len(cases) * DEV_CASE_FRACTION)))
    dev_cases = set(cases[:n_dev])

    view_rows: list[dict[str, object]] = []
    relation_rows: list[dict[str, object]] = []
    excluded_rows = 0
    dropped_unresolved = 0
    stripped_acceptables = 0
    stripped_relations = 0

    for raw in train.to_dict("records"):
        case_id = str(raw["case_id"])
        variant_id = str(raw["variant_id"])
        if case_id in EXCLUDED_CASES:
            excluded_rows += 1
            continue
        intended = remap_id(str(raw["intended_poi_id"]), corpus_ids, migration)
        if intended is None:
            dropped_unresolved += 1
            continue
        positives: list[str] = []
        for poi_id in parse_ids(raw["acceptable_poi_ids"]):
            mapped = remap_id(poi_id, corpus_ids, migration)
            if mapped and mapped not in positives:
                positives.append(mapped)
        if intended in holdout_ids:
            raise SystemExit(f"Train intended is a Gold POI: {case_id} {intended}")
        if holdout_ids:
            kept_pos = [poi_id for poi_id in positives if poi_id not in holdout_ids]
            stripped_acceptables += len(positives) - len(kept_pos)
            positives = kept_pos
        if intended not in positives:
            positives.insert(0, intended)
        entity_id = entity_by_id.get(intended)
        if not entity_id:
            dropped_unresolved += 1
            continue
        slot = slot_of(variant_id)
        brand_group_id = accepted_group.get(intended, "")
        split = "dev" if case_id in dev_cases else "train"
        view_rows.append(
            {
                "query_id": variant_id,
                "case_id": case_id,
                "variant_id": variant_id,
                "slot": slot,
                "query_text": str(raw["query_text"]),
                "canonical_query": str(raw["canonical_query"]),
                "query_variant_family": str(raw["query_variant_family"]),
                "variant_operator": str(raw["variant_operator"]),
                "primary_sampling_stratum": str(raw["primary_sampling_stratum"]),
                "intended_poi_id": intended,
                "intended_poi_id_source": str(raw["intended_poi_id"]),
                "acceptable_poi_ids": json.dumps(positives, ensure_ascii=False),
                "n_acceptable": len(positives),
                "entity_group_id": entity_id,
                "brand_group_id": brand_group_id,
                "sample_weight": float(slot_weight.get(slot, 0.25)),
                "split": split,
                "source_dataset": "train_stage1_queries_v6",
            }
        )
        seen: set[str] = set()
        for poi_id in positives:
            relation_rows.append(
                {
                    "query_id": variant_id,
                    "poi_id": poi_id,
                    "label": "positive",
                    "label_reason": "authored_acceptable",
                    "split": split,
                }
            )
            seen.add(poi_id)
        if brand_group_id:
            for poi_id in sorted(group_ignore.get(brand_group_id, ())):
                if poi_id in holdout_ids:
                    stripped_relations += 1
                    continue
                if poi_id in seen:
                    continue
                relation_rows.append(
                    {
                        "query_id": variant_id,
                        "poi_id": poi_id,
                        "label": "ignore",
                        "label_reason": "brand_membership_needs_review",
                        "split": split,
                    }
                )
                seen.add(poi_id)
            for poi_id in sorted(group_accepted.get(brand_group_id, ())):
                if poi_id in holdout_ids:
                    stripped_relations += 1
                    continue
                if poi_id in seen:
                    continue
                relation_rows.append(
                    {
                        "query_id": variant_id,
                        "poi_id": poi_id,
                        "label": "hard_neg_candidate",
                        "label_reason": "same_brand_other_branch",
                        "split": split,
                    }
                )
                seen.add(poi_id)

    view = pd.DataFrame(view_rows)
    relations = pd.DataFrame(relation_rows)
    if holdout_ids:
        intended_overlap = sorted(set(view["intended_poi_id"].astype(str)) & holdout_ids)
        if intended_overlap:
            raise SystemExit(f"Compiled intended still overlaps Gold: {intended_overlap[:10]}")
        acceptable_overlap = []
        for raw in view["acceptable_poi_ids"]:
            acceptable_overlap.extend(poi_id for poi_id in parse_ids(raw) if poi_id in holdout_ids)
        relation_overlap = sorted(set(relations["poi_id"].astype(str)) & holdout_ids)
        if acceptable_overlap or relation_overlap:
            raise SystemExit(
                "Compiled view still contains Gold POIs: "
                f"acceptables={acceptable_overlap[:5]} relations={relation_overlap[:5]}"
            )
    pq.write_table(
        pa.Table.from_pandas(view, preserve_index=False),
        out / "query_train_view.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pandas(relations, preserve_index=False),
        out / "query_relation_view.parquet",
        compression="zstd",
    )

    manifest = {
        "dataset": out.name,
        "status": "EXPERIMENTAL",
        "note": "Compiled views only. Does not modify published v6 queries.",
        "split_seed": SPLIT_SEED,
        "dev_case_fraction": DEV_CASE_FRACTION,
        "slot_weight": slot_weight,
        "excluded_cases": EXCLUDED_CASES,
        "holdout_gold": {
            "path": holdout_dir,
            "n_ids": len(holdout_ids),
            "stripped_acceptables": stripped_acceptables,
            "stripped_relations": stripped_relations,
            "max_cases": int(args.max_cases or 0),
        },
        "counts": {
            "view_rows": int(len(view)),
            "train_rows": int((view["split"] == "train").sum()),
            "dev_rows": int((view["split"] == "dev").sum()),
            "train_cases": int(view.loc[view["split"] == "train", "case_id"].nunique()),
            "dev_cases": int(view.loc[view["split"] == "dev", "case_id"].nunique()),
            "excluded_source_rows": excluded_rows,
            "dropped_unresolved": dropped_unresolved,
            "relation_rows": int(len(relations)),
            "relations_by_label": relations["label"].value_counts().to_dict(),
            "rows_with_brand_group": int((view["brand_group_id"] != "").sum()),
        },
        "sources": {
            "query_variants.csv": {"path": str(TRAIN_CSV.as_posix()), "sha256": sha256(TRAIN_CSV)},
            "train_manifest.json": {"path": str(TRAIN_MANIFEST.as_posix()), "sha256": sha256(TRAIN_MANIFEST)},
            "search_documents.parquet": {
                "path": str((CORPUS / "search_documents.parquet").as_posix()),
                "sha256": sha256(CORPUS / "search_documents.parquet"),
            },
            "brand_group_members_v1.parquet": {
                "path": str(BRAND_MEMBERS.as_posix()),
                "sha256": sha256(BRAND_MEMBERS),
            },
        },
        "outputs": {
            "query_train_view.parquet": sha256(out / "query_train_view.parquet"),
            "query_relation_view.parquet": sha256(out / "query_relation_view.parquet"),
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "README.md").write_text(
        "# Stage-1 v6 hard-negative views (experimental)\n\n"
        "Compiled training views only. Published "
        "`train_stage1_queries_v6/query_variants.csv` is not modified.\n\n"
        "- `query_train_view.parquet`: same query text, remapped v3 IDs, slot weights, split.\n"
        "- `query_relation_view.parquet`: authored positives, ignore, same-brand hard-neg candidates.\n"
        "- `training_pairs.parquet`: written later by `tools/mine_stage1_hardneg_pilot.py`.\n"
        "- Gold holdout POIs are removed from acceptables, ignore, and hard-neg candidates "
        "when `--holdout-gold` is set.\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
