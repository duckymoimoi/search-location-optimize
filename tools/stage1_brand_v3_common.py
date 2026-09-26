"""Shared helpers for corpus-v3 brand membership, split, and Gold compile."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from stage1_brand_query_v1_common import (
    NAMESPACE_TOKENS,
    compact_alnum,
    normalize_query,
    strip_diacritics,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS_V2 = ROOT / "data/vietnam/poi_corpus_v2"
CORPUS_V3 = ROOT / "data/vietnam/poi_corpus_v3"
BRAND_V1 = ROOT / "data/vietnam/train_stage1_brand_v1"
LOOKUP_V2 = ROOT / "data/vietnam/train_stage1_brand_lookup_v2"
PACKET_V2 = ROOT / "data/vietnam/train_stage1_brand_queries_v2/brand_authoring_packet_v2.jsonl"
STAGING_V1 = ROOT / "data/vietnam/train_stage1_brand_queries_v1/staging"
GOLD_POI = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1"
TRAIN_V6 = ROOT / "data/vietnam/train_stage1_queries_v6"
OVERRIDES = ROOT / "data/vietnam/brand_intent_overrides_v2.csv"
SCHEMA = ROOT / "docs/specs/schemas/stage1_evaluation_v2.schema.json"

MEMBERSHIP_V3 = ROOT / "data/vietnam/train_stage1_brand_membership_v3"
LOOKUP_V3 = ROOT / "data/vietnam/train_stage1_brand_lookup_v3"
SPLITS_V1 = ROOT / "data/vietnam/train_stage1_brand_splits_v1"
TRAIN_BRAND_V3 = ROOT / "data/vietnam/train_stage1_brand_queries_v3"
GOLD_BRAND_STAGING = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_brand_v1"
GOLD_BRAND_DEV = ROOT / "data/vietnam/stage1_eval_suite_v2/staging/gold_stage1_brand_dev_v1"
GOLD_BRAND = ROOT / "data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1"
UNIFIED_VIEWS = ROOT / "data/vietnam/train_stage1_poi_brand_views_v1"

CORPUS_VERSION = "vn-poi-core-v3-semantic-address-dedup50"
NORMALIZER_VERSION = "v2-nfkc-casefold"
GROUP_VERSION = "brand_groups_v1"
MEMBERSHIP_VIEW_VERSION = "brand_membership_v3"
LOOKUP_VERSION = "brand_lookup_v3"
SPLIT_VERSION = "brand_family_split_v1"
SPLIT_SEED = 20260926
TEST_FAMILY_TARGET = 70
DEV_FAMILY_TARGET = 35
PREFIX_EXPANDER_VERSION = "v2-grapheme-nfc"
LABEL_POLICY_VERSION = "v1-compatible-brand-group"
SCHEMA_VERSION = "stage1-eval-suite-v2"

OPERATOR_TO_ROLE = {
    "brand_canonical": "canonical_brand",
    "brand_namespace_form": "namespace_qualified",
    "brand_alias": "verified_alias",
    "brand_case_punct": "brand_error",
    "brand_mechanical_typo": "brand_error",
    "brand_space_variant": "brand_error",
    "brand_orthographic_ime": "brand_error",
    "brand_phonetic": "brand_error",
}
OPERATOR_TO_DIFFICULTY = {
    "brand_canonical": "clean",
    "brand_namespace_form": "clean",
    "brand_alias": "clean",
    "brand_case_punct": "mild",
    "brand_mechanical_typo": "mild",
    "brand_space_variant": "mild",
    "brand_orthographic_ime": "compound",
    "brand_phonetic": "compound",
}

LEFT_OVER_FAMILIES = {
    "brand:atm_bidv": "merged_into_brand:bidv:atm",
    "brand:can_ho_dich_vu_va_khach_san": "excluded_generic_descriptor",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refuse_nonempty(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty directory: {path}")


def fold_text(value: Any) -> str:
    return normalize_query(strip_diacritics(value))


def graphemes(text: str) -> list[str]:
    return list(unicodedata.normalize("NFC", text))


def source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.as_posix()),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def load_v3_core() -> pd.DataFrame:
    return pd.read_parquet(
        CORPUS_V3 / "pois_core.parquet",
        columns=["poi_id", "destination_searchable", "entity_group_id", "name", "brand"],
    )


def load_migration_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [
        "old_poi_id",
        "canonical_poi_id",
        "action",
        "old_name",
        "new_name",
        "distance_to_canonical_m",
        "reason",
    ]
    return (
        pd.read_parquet(CORPUS_V2 / "poi_id_migration.parquet", columns=cols),
        pd.read_parquet(CORPUS_V3 / "poi_id_migration.parquet", columns=cols),
    )


def _row_map(table: pd.DataFrame) -> dict[str, dict[str, str]]:
    mapped: dict[str, dict[str, str]] = {}
    for row in table.itertuples(index=False):
        mapped[str(row.old_poi_id)] = {
            "canonical_poi_id": str(row.canonical_poi_id),
            "action": str(row.action),
            "reason": str(row.reason or ""),
            "old_name": str(row.old_name or ""),
            "new_name": str(row.new_name or ""),
        }
    return mapped


def compose_migration(
    mig2: pd.DataFrame,
    mig3: pd.DataFrame,
    v3_ids: set[str],
) -> pd.DataFrame:
    map2 = _row_map(mig2)
    map3 = _row_map(mig3)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(source_id: str) -> None:
        if source_id in seen:
            return
        seen.add(source_id)
        v2_info = map2.get(source_id)
        mid = v2_info["canonical_poi_id"] if v2_info else source_id
        v2_action = v2_info["action"] if v2_info else ""
        v2_reason = v2_info["reason"] if v2_info else ""
        v3_info = map3.get(mid) or (map3.get(source_id) if mid != source_id else None)
        dest = ""
        v3_action = ""
        v3_reason = ""
        if mid in v3_ids:
            dest = mid
            v3_action = "already_in_v3"
        elif v3_info:
            v3_action = v3_info["action"]
            v3_reason = v3_info["reason"]
            candidate = v3_info["canonical_poi_id"]
            if candidate in v3_ids:
                dest = candidate
        composed = "unmapped"
        if dest and dest in v3_ids:
            if v2_action.startswith("drop") or v3_action.startswith("drop"):
                dest = ""
                composed = "dropped_no_successor"
            elif dest == source_id:
                composed = "already_in_v3"
            elif v3_action == "merge_duplicate" or v2_action == "merge_duplicate":
                composed = "merged_same_poi"
            else:
                composed = "keep_via_v1v2v3"
        elif (v2_action.startswith("drop") if v2_action else False) or v3_action.startswith("drop"):
            composed = "dropped_no_successor"
        rows.append(
            {
                "source_poi_id": source_id,
                "v2_poi_id": mid,
                "mapped_poi_id": dest,
                "v2_action": v2_action,
                "v3_action": v3_action,
                "v2_reason": v2_reason,
                "v3_reason": v3_reason,
                "composed_action": composed,
                "mapping_evidence": "|".join(
                    part
                    for part in (
                        f"v2:{v2_action}:{v2_reason}" if v2_action else "",
                        f"v3:{v3_action}:{v3_reason}" if v3_action else "",
                    )
                    if part
                ),
            }
        )

    for source_id in map2:
        append(source_id)
    for source_id in map3:
        append(source_id)
    return pd.DataFrame(rows)


def remap_with_table(
    source_id: str,
    composed: pd.DataFrame,
    v3_ids: set[str],
) -> tuple[str | None, str, str]:
    if source_id in v3_ids:
        return source_id, "already_in_v3", ""
    hit = composed.loc[composed["source_poi_id"] == source_id]
    if hit.empty:
        return None, "no_map", ""
    row = hit.iloc[0]
    dest = str(row.mapped_poi_id or "")
    action = str(row.composed_action)
    evidence = str(row.mapping_evidence or "")
    if dest and dest in v3_ids and action != "dropped_no_successor":
        return dest, action, evidence
    return None, action or "unmapped", evidence


def remap_lookup(
    composed: pd.DataFrame,
    v3_ids: set[str],
) -> dict[str, tuple[str | None, str, str]]:
    lookup: dict[str, tuple[str | None, str, str]] = {}
    for row in composed.itertuples(index=False):
        dest = str(row.mapped_poi_id or "")
        action = str(row.composed_action)
        evidence = str(row.mapping_evidence or "")
        mapped = dest if dest and dest in v3_ids and action != "dropped_no_successor" else None
        lookup[str(row.source_poi_id)] = (mapped, action, evidence)
    for poi_id in v3_ids:
        lookup.setdefault(poi_id, (poi_id, "already_in_v3", ""))
    return lookup


def group_ready_grapheme(query_text: str, other_folds: list[str]) -> tuple[int, str]:
    units = graphemes(query_text)
    if not units:
        return 1, query_text
    own = compact_alnum(query_text)
    rivals = [fold for fold in other_folds if fold and fold != own]
    for index in range(1, len(units) + 1):
        prefix = "".join(units[:index])
        compact = compact_alnum(prefix)
        if len(compact) < 2:
            continue
        if not any(rival.startswith(compact) or compact.startswith(rival) for rival in rivals):
            return index, prefix
    return len(units), query_text


def language_bucket(canonical: str) -> str:
    letters = [char for char in canonical if char.isalpha()]
    if not letters:
        return "other"
    vietnamese = any(ord(char) > 127 for char in canonical)
    ascii_letters = all(ord(char) < 128 for char in letters)
    if vietnamese:
        return "vi"
    if ascii_letters:
        return "en"
    return "mixed"


def acronym_flag(canonical: str) -> bool:
    compact = "".join(char for char in canonical if char.isalnum())
    return 2 <= len(compact) <= 5 and compact.isupper()


def family_stratum(n_members: int, n_namespaces: int, canonical: str) -> str:
    size = "xl" if n_members >= 80 else "lg" if n_members >= 20 else "md" if n_members >= 5 else "sm"
    ns = "multi_ns" if n_namespaces >= 2 else "single_ns"
    lang = language_bucket(canonical)
    acro = "acronym" if acronym_flag(canonical) else "name"
    return f"{size}|{ns}|{lang}|{acro}"


def has_namespace_token(query: str, namespace: str) -> bool:
    folded = normalize_query(query)
    unaccented = fold_text(query)
    return any(
        normalize_query(token) in folded or normalize_query(strip_diacritics(token)) in unaccented
        for token in NAMESPACE_TOKENS.get(namespace, ())
    )


def looks_bare_brand(query_text: str, canonical: str, namespace: str | None = None) -> bool:
    query = normalize_query(query_text)
    brand = normalize_query(canonical)
    if not query or not brand:
        return False
    tokens = query.split()
    brand_tokens = brand.split()
    extra = [token for token in tokens if token not in brand_tokens]
    if extra and namespace:
        allowed = {normalize_query(token) for token in NAMESPACE_TOKENS.get(namespace, ())}
        extra = [token for token in extra if token not in allowed and fold_text(token) not in {fold_text(item) for item in allowed}]
    return query == brand or (
        brand in query
        and len(tokens) <= len(brand_tokens) + 2
        and not extra
    )


def parse_id_list(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item) for item in raw]
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        return [str(item) for item in json.loads(text)]
    return [part for part in text.split("|") if part]


def pool_hash(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def exposure_for_family(
    member_ids: set[str],
    train_poi_ids: set[str],
    *,
    allow_cold: bool = False,
) -> str:
    if member_ids & train_poi_ids:
        return "brand_query_heldout_branch_seen"
    if allow_cold:
        return "cold_brand"
    return "brand_query_heldout_branch_unseen"


def index_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): row for row in rows}


def group_lists(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, value in pairs:
        grouped[key].append(value)
    return grouped
