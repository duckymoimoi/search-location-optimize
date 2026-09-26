"""Build and lock corpus-wide brand family/group membership version 1.

The script never authors brand queries. It extracts auditable membership evidence,
keeps uncertain name/alias candidates in review queues, and refuses to overwrite an
existing release directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


GROUP_VERSION = "brand_groups_v1"
NAMESPACES = {
    "fuel",
    "bank",
    "atm",
    "cafe",
    "restaurant",
    "convenience_store",
    "supermarket",
    "pharmacy",
    "hotel",
    "retail",
    "other_reviewed",
}
GENERIC_KEYS = {
    "a",
    "b",
    "c",
    "yes",
    "no",
    "none",
    "unknown",
    "shop",
    "store",
    "cafe",
    "coffee",
    "hotel",
    "bank",
    "atm",
    "restaurant",
    "fuel station",
    "cửa hàng",
    "cửa hàng xăng dầu",
    "cây xăng",
    "trạm xăng",
    "nhà thuốc",
    "hiệu thuốc",
    "quán cà phê",
    "quán cafe",
    "homestay",
    "khách sạn",
    "nhà hàng",
    "tạp hóa",
}
DESCRIPTOR_PATTERNS = (
    r"^(?:ngân hàng|cây xăng|trạm xăng|cửa hàng xăng dầu|cửa hàng)\s+",
    r"\s*(?:-|–|—)?\s*(?:atm|chi nhánh|phòng giao dịch)\s*$",
    r"\s+(?:số|no\.?|number)\s*[a-z0-9./-]+\s*$",
)

MEMBER_COLUMNS = [
    "brand_family_id",
    "brand_group_id",
    "brand_canonical",
    "brand_fold",
    "brand_namespace",
    "poi_id",
    "destination_searchable",
    "province_region_id",
    "subdistrict_region_id",
    "membership_status",
    "membership_evidence",
    "evidence_text",
    "group_version",
    "review_status",
]


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return " ".join(text.split())


def match_key(value: Any) -> str:
    text = normalize_text(value).replace("+", " plus ")
    return "".join(char for char in text if char.isalnum())


def ascii_slug(value: str) -> str:
    text = normalize_text(value).replace("+", " plus ").replace("đ", "d")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char)
    )
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return slug or "unnamed"


def namespace_for(category: Any) -> str:
    text = normalize_text(category)
    if "amenity=atm" in text:
        return "atm"
    if "amenity=bank" in text:
        return "bank"
    if "amenity=fuel" in text:
        return "fuel"
    if "amenity=cafe" in text:
        return "cafe"
    if "amenity=restaurant" in text or "amenity=fast_food" in text:
        return "restaurant"
    if "shop=convenience" in text:
        return "convenience_store"
    if "shop=supermarket" in text:
        return "supermarket"
    if any(
        token in text
        for token in (
            "amenity=pharmacy",
            "healthcare=pharmacy",
            "shop=pharmacy",
            "shop=chemist",
        )
    ):
        return "pharmacy"
    if "tourism=hotel" in text:
        return "hotel"
    if "shop=" in text:
        return "retail"
    return "other_reviewed"


def stripped_name_key(name: Any) -> str:
    text = normalize_text(name)
    for pattern in DESCRIPTOR_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return match_key(text)


def alias_values(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_overrides(path: Path) -> dict[str, dict[str, str]]:
    decisions: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            fold = normalize_text(row.get("brand_fold"))
            if not fold or row.get("decision") not in {"accept_identity", "reject_identity"}:
                raise ValueError(f"Invalid review override: {row}")
            if fold in decisions:
                raise ValueError(f"Duplicate review override: {fold}")
            decisions[fold] = {
                "decision": str(row["decision"]),
                "note": str(row.get("note") or "").strip(),
            }
    return decisions


def stable_family_ids(keys: list[str], canonical_by_key: dict[str, str]) -> dict[str, str]:
    by_slug: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        by_slug[ascii_slug(canonical_by_key[key])].append(key)
    result: dict[str, str] = {}
    for slug, slug_keys in sorted(by_slug.items()):
        for key in sorted(slug_keys):
            suffix = "" if len(slug_keys) == 1 else "_" + hashlib.sha1(key.encode()).hexdigest()[:8]
            result[key] = f"brand:{slug}{suffix}"
    return result


def choose_canonical(values: pd.Series) -> str:
    counts = Counter(str(value).strip() for value in values if str(value).strip())
    return sorted(counts, key=lambda value: (-counts[value], normalize_text(value), value))[0]


def write_parquet(rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    frame = pd.DataFrame(rows, columns=columns)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")


def build(corpus_path: Path, overrides_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty release: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    overrides = read_overrides(overrides_path)
    columns = [
        "poi_id",
        "name",
        "aliases",
        "brand",
        "category",
        "province_region_id",
        "subdistrict_region_id",
        "destination_searchable",
    ]
    frame = pd.read_parquet(corpus_path, columns=columns)
    frame["brand_raw"] = frame["brand"].fillna("").astype(str).str.strip()
    explicit = frame[frame["brand_raw"] != ""].copy()
    explicit["brand_fold"] = explicit["brand_raw"].map(normalize_text)
    explicit["brand_key"] = explicit["brand_raw"].map(match_key)
    explicit = explicit[explicit["brand_key"] != ""]

    canonical_by_key = {
        key: choose_canonical(group["brand_raw"])
        for key, group in explicit.groupby("brand_key", sort=True)
    }
    family_ids = stable_family_ids(sorted(canonical_by_key), canonical_by_key)
    fold_to_keys: dict[str, set[str]] = defaultdict(set)
    for key, canonical in canonical_by_key.items():
        fold_to_keys[normalize_text(canonical)].add(key)
        for value in explicit.loc[explicit["brand_key"] == key, "brand_raw"].unique():
            fold_to_keys[normalize_text(value)].add(key)

    explicit_counts = Counter(explicit["brand_key"])
    key_is_generic = {
        key: normalize_text(canonical_by_key[key]) in GENERIC_KEYS
        or len(match_key(canonical_by_key[key])) < 2
        for key in canonical_by_key
    }
    reviewed_keys = {
        key
        for fold, decision in overrides.items()
        if decision["decision"] == "accept_identity"
        for key in fold_to_keys.get(fold, set())
    }
    rejected_keys = {
        key
        for fold, decision in overrides.items()
        if decision["decision"] == "reject_identity"
        for key in fold_to_keys.get(fold, set())
    }

    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    def add_candidate(row: pd.Series, key: str, evidence: str, evidence_text: str) -> None:
        namespace = namespace_for(row["category"])
        family_id = family_ids[key]
        group_id = f"{family_id}:{namespace}"
        pk = (group_id, str(row["poi_id"]))
        rank = {
            "explicit_brand": 4,
            "exact_name_pattern": 3,
            "verified_alias": 2,
            "name_pattern_candidate": 1,
        }
        record = {
            "brand_family_id": family_id,
            "brand_group_id": group_id,
            "brand_canonical": canonical_by_key[key],
            "brand_fold": normalize_text(canonical_by_key[key]),
            "brand_namespace": namespace,
            "poi_id": str(row["poi_id"]),
            "destination_searchable": bool(row["destination_searchable"]),
            "province_region_id": None
            if pd.isna(row["province_region_id"])
            else str(row["province_region_id"]),
            "subdistrict_region_id": None
            if pd.isna(row["subdistrict_region_id"])
            else str(row["subdistrict_region_id"]),
            "membership_status": "needs_review",
            "membership_evidence": evidence,
            "evidence_text": evidence_text,
            "group_version": GROUP_VERSION,
            "review_status": "needs_review",
            "_brand_key": key,
            "_rank": rank[evidence],
        }
        previous = candidates.get(pk)
        if previous is None or record["_rank"] > previous["_rank"]:
            candidates[pk] = record

    for _, row in explicit.iterrows():
        add_candidate(
            row,
            str(row["brand_key"]),
            "explicit_brand",
            f"brand={row['brand_raw']}",
        )

    no_brand = frame[frame["brand_raw"] == ""]
    key_to_family = {key: family_ids[key] for key in canonical_by_key}
    for _, row in no_brand.iterrows():
        exact = match_key(row["name"])
        if exact in key_to_family:
            add_candidate(row, exact, "exact_name_pattern", f"name={row['name']}")
            continue
        alias_keys = {
            match_key(alias)
            for alias in alias_values(row["aliases"])
            if match_key(alias) in key_to_family
        }
        if len(alias_keys) == 1:
            key = next(iter(alias_keys))
            add_candidate(row, key, "verified_alias", f"alias_exact={canonical_by_key[key]}")
            continue
        stripped = stripped_name_key(row["name"])
        if stripped in key_to_family and stripped != exact:
            add_candidate(
                row,
                stripped,
                "name_pattern_candidate",
                f"name_pattern={row['name']}",
            )

    group_sizes = Counter(record["brand_group_id"] for record in candidates.values())
    strong_searchable_group_sizes = Counter(
        record["brand_group_id"]
        for record in candidates.values()
        if record["membership_evidence"] in {"explicit_brand", "exact_name_pattern"}
        and record["destination_searchable"]
    )
    for record in candidates.values():
        key = record.pop("_brand_key")
        record.pop("_rank")
        searchable = record["destination_searchable"]
        evidence = record["membership_evidence"]
        group_size = group_sizes[record["brand_group_id"]]
        strong_group_size = strong_searchable_group_sizes[record["brand_group_id"]]
        if not searchable or key in rejected_keys:
            record["membership_status"] = "excluded"
            record["review_status"] = "accepted" if key in reviewed_keys else "authored"
        elif (
            key_is_generic[key]
            or group_size < 2
            or strong_group_size < 2
            or record["brand_namespace"] == "other_reviewed"
        ):
            record["membership_status"] = "needs_review"
            record["review_status"] = "needs_review"
        elif evidence == "name_pattern_candidate" and key not in reviewed_keys:
            record["membership_status"] = "needs_review"
            record["review_status"] = "needs_review"
        elif evidence == "verified_alias" and key not in reviewed_keys:
            record["membership_status"] = "needs_review"
            record["review_status"] = "needs_review"
        else:
            record["membership_status"] = "accepted"
            record["review_status"] = "accepted" if key in reviewed_keys else "authored"

    member_rows = sorted(
        candidates.values(), key=lambda row: (row["brand_group_id"], row["poi_id"])
    )

    known_name_keys = set(canonical_by_key)
    unresolved_rows = no_brand.copy()
    unresolved_rows["name_key"] = unresolved_rows["name"].map(match_key)
    repeated_names = Counter(
        key for key in unresolved_rows["name_key"] if key and key not in known_name_keys
    )
    repeated_aliases: Counter[str] = Counter()
    alias_display: dict[str, Counter[str]] = defaultdict(Counter)
    for aliases in unresolved_rows["aliases"]:
        for alias in alias_values(aliases):
            key = match_key(alias)
            if key and key not in known_name_keys:
                repeated_aliases[key] += 1
                alias_display[key][str(alias).strip()] += 1

    family_rows: list[dict[str, Any]] = []
    for key in sorted(canonical_by_key):
        members = [row for row in member_rows if row["brand_family_id"] == family_ids[key]]
        status_counts = Counter(row["membership_status"] for row in members)
        family_rows.append(
            {
                "brand_family_id": family_ids[key],
                "brand_canonical": canonical_by_key[key],
                "brand_fold": normalize_text(canonical_by_key[key]),
                "brand_match_key": key,
                "candidate_source": "explicit_brand",
                "n_source_pois": int(explicit_counts[key]),
                "n_member_rows": len(members),
                "n_accepted": status_counts["accepted"],
                "n_needs_review": status_counts["needs_review"],
                "candidate_status": "excluded"
                if key in rejected_keys
                else ("needs_review" if key_is_generic[key] else "accepted"),
                "review_note": next(
                    (
                        value["note"]
                        for fold, value in overrides.items()
                        if key in fold_to_keys.get(fold, set())
                    ),
                    "",
                ),
                "group_version": GROUP_VERSION,
            }
        )

    unresolved_seen: set[tuple[str, str]] = set()
    for source, counts, display in (
        ("repeated_name", repeated_names, None),
        ("repeated_alias", repeated_aliases, alias_display),
    ):
        for key, count in sorted(counts.items()):
            if count < 3:
                continue
            if source == "repeated_name":
                values = unresolved_rows.loc[unresolved_rows["name_key"] == key, "name"]
                canonical = choose_canonical(values)
            else:
                canonical = sorted(
                    display[key], key=lambda value: (-display[key][value], normalize_text(value))
                )[0]
            fold = normalize_text(canonical)
            if fold in GENERIC_KEYS or len(key) < 3:
                reason = "generic_or_too_short"
            else:
                reason = "no_explicit_brand_evidence"
            candidate_id = f"candidate:{ascii_slug(canonical)}"
            pair = (source, candidate_id)
            if pair in unresolved_seen:
                candidate_id += "_" + hashlib.sha1(key.encode()).hexdigest()[:8]
            unresolved_seen.add((source, candidate_id))
            family_rows.append(
                {
                    "brand_family_id": candidate_id,
                    "brand_canonical": canonical,
                    "brand_fold": fold,
                    "brand_match_key": key,
                    "candidate_source": source,
                    "n_source_pois": int(count),
                    "n_member_rows": 0,
                    "n_accepted": 0,
                    "n_needs_review": int(count),
                    "candidate_status": "needs_review",
                    "review_note": reason,
                    "group_version": GROUP_VERSION,
                }
            )
    family_rows.sort(key=lambda row: (row["brand_family_id"], row["candidate_source"]))

    alias_rows: list[dict[str, Any]] = []
    alias_family_counts: Counter[tuple[str, str]] = Counter()
    alias_text_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for _, row in explicit.iterrows():
        key = str(row["brand_key"])
        family_id = family_ids[key]
        for alias in alias_values(row["aliases"]):
            alias_fold = normalize_text(alias)
            if not alias_fold or match_key(alias) == key:
                continue
            pair = (family_id, alias_fold)
            alias_family_counts[pair] += 1
            alias_text_counts[pair][str(alias).strip()] += 1
    for (family_id, alias_fold), count in sorted(alias_family_counts.items()):
        canonical = sorted(
            alias_text_counts[(family_id, alias_fold)],
            key=lambda value: (-alias_text_counts[(family_id, alias_fold)][value], value),
        )[0]
        alias_rows.append(
            {
                "brand_family_id": family_id,
                "alias_text": canonical,
                "alias_fold": alias_fold,
                "source_poi_count": int(count),
                "candidate_status": "needs_review",
                "review_reason": "poi alias may describe branch/name rather than family",
                "group_version": GROUP_VERSION,
            }
        )

    members_path = output_dir / "brand_group_members_v1.parquet"
    families_path = output_dir / "brand_family_candidates_v1.parquet"
    aliases_path = output_dir / "brand_alias_candidates_v1.parquet"
    write_parquet(member_rows, MEMBER_COLUMNS, members_path)
    write_parquet(
        family_rows,
        [
            "brand_family_id",
            "brand_canonical",
            "brand_fold",
            "brand_match_key",
            "candidate_source",
            "n_source_pois",
            "n_member_rows",
            "n_accepted",
            "n_needs_review",
            "candidate_status",
            "review_note",
            "group_version",
        ],
        families_path,
    )
    write_parquet(
        alias_rows,
        [
            "brand_family_id",
            "alias_text",
            "alias_fold",
            "source_poi_count",
            "candidate_status",
            "review_reason",
            "group_version",
        ],
        aliases_path,
    )

    member_frame = pd.DataFrame(member_rows)
    top = (
        member_frame.groupby(["brand_family_id", "brand_canonical"], sort=False)
        .agg(
            n_members=("poi_id", "size"),
            n_accepted=("membership_status", lambda values: int((values == "accepted").sum())),
            n_needs_review=(
                "membership_status", lambda values: int((values == "needs_review").sum())
            ),
            namespaces=("brand_namespace", lambda values: ", ".join(sorted(set(values)))),
            evidence=("membership_evidence", lambda values: ", ".join(sorted(set(values)))),
        )
        .reset_index()
        .sort_values(["n_members", "brand_family_id"], ascending=[False, True])
        .head(50)
    )
    reviewed_family_ids = {family_ids[key] for key in reviewed_keys}
    rejected_family_ids = {family_ids[key] for key in rejected_keys}
    top["identity_review"] = top["brand_family_id"].map(
        lambda family_id: "accepted"
        if family_id in reviewed_family_ids
        else ("rejected" if family_id in rejected_family_ids else "not_manually_reviewed")
    )
    top_path = output_dir / "top_multibranch_review_v1.csv"
    top.to_csv(top_path, index=False, encoding="utf-8-sig")

    audit_errors: list[str] = []
    audit_warnings: list[str] = []
    if len(member_frame) != len(member_frame.drop_duplicates(["brand_group_id", "poi_id"])):
        audit_errors.append("duplicate brand_group_id + poi_id")
    accepted = member_frame[member_frame["membership_status"] == "accepted"]
    if not accepted["destination_searchable"].all():
        audit_errors.append("accepted member is non-searchable")
    if not set(member_frame["brand_namespace"]).issubset(NAMESPACES):
        audit_errors.append("unknown namespace")
    if (member_frame["group_version"] != GROUP_VERSION).any():
        audit_errors.append("wrong group_version")
    singleton_groups = int((member_frame.groupby("brand_group_id").size() == 1).sum())
    if singleton_groups:
        audit_warnings.append(f"{singleton_groups} singleton groups remain needs_review/excluded")
    other_count = int((member_frame["brand_namespace"] == "other_reviewed").sum())
    if other_count:
        audit_warnings.append(f"{other_count} other_reviewed memberships require semantic review")

    audit = {
        "version": GROUP_VERSION,
        "verdict": "PASS" if not audit_errors else "FAIL",
        "errors": audit_errors,
        "warnings": audit_warnings,
        "stats": {
            "corpus_rows": len(frame),
            "explicit_brand_rows": len(explicit),
            "known_families": len(canonical_by_key),
            "family_candidate_rows": len(family_rows),
            "membership_rows": len(member_rows),
            "accepted_members": int((member_frame["membership_status"] == "accepted").sum()),
            "needs_review_members": int(
                (member_frame["membership_status"] == "needs_review").sum()
            ),
            "excluded_members": int((member_frame["membership_status"] == "excluded").sum()),
            "alias_candidates": len(alias_rows),
            "reviewed_identity_overrides": len(reviewed_keys),
            "singleton_groups": singleton_groups,
        },
    }
    audit_path = output_dir / "audit_report.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if audit_errors:
        raise RuntimeError(f"Brand group audit failed: {audit_errors}")

    override_copy = output_dir / "brand_family_review_overrides_v1.csv"
    override_copy.write_bytes(overrides_path.read_bytes())
    artifact_paths = [members_path, families_path, aliases_path, top_path, audit_path, override_copy]
    completed = datetime.now(UTC)
    manifest = {
        "dataset": "train_stage1_brand_v1_membership",
        "group_version": GROUP_VERSION,
        "status": "LOCKED",
        "scope": "membership_only; brand queries and qrels are not built",
        "created_at_utc": completed.isoformat(),
        "elapsed_seconds": round((completed - started).total_seconds(), 3),
        "source": {
            "corpus": str(corpus_path),
            "corpus_sha256": sha256_file(corpus_path),
        },
        "artifacts": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in artifact_paths
        },
        "stats": audit["stats"],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lock = {
        "group_version": GROUP_VERSION,
        "locked_at_utc": completed.isoformat(),
        "manifest_sha256": sha256_file(manifest_path),
        "mutation_policy": "Do not edit in place; create brand_groups_v2.",
    }
    (output_dir / "LOCKED.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"manifest": manifest, "audit": audit}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--review-overrides", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = build(args.corpus, args.review_overrides, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
