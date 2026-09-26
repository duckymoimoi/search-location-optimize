"""Query locked brand_lookup_v2 or create a compact brand-context packet."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from build_brand_groups_v1 import alias_values, match_key, namespace_for, stripped_name_key


def dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def family_context(
    connection: sqlite3.Connection,
    family_id: str,
    namespace: str | None = None,
    include_members: bool = False,
) -> dict[str, Any]:
    family_rows = dict_rows(
        connection.execute(
            "SELECT * FROM brand_families WHERE brand_family_id = ?", (family_id,)
        )
    )
    sql = "SELECT * FROM brand_groups WHERE brand_family_id = ?"
    params: list[Any] = [family_id]
    if namespace:
        sql += " AND brand_namespace = ?"
        params.append(namespace)
    sql += " ORDER BY CASE group_status WHEN 'accepted' THEN 0 ELSE 1 END, n_accepted DESC, brand_group_id"
    groups = dict_rows(connection.execute(sql, params))
    if include_members:
        for group in groups:
            group["accepted_poi_ids"] = [
                row[0]
                for row in connection.execute(
                    "SELECT poi_id FROM brand_members WHERE brand_group_id = ? "
                    "AND membership_status = 'accepted' ORDER BY poi_id",
                    (group["brand_group_id"],),
                )
            ]
    return {
        "brand_family_id": family_id,
        "family": family_rows[0] if family_rows else None,
        "groups": groups,
        "usable_groups": [group for group in groups if group["group_status"] == "accepted"],
    }


def lookup_text(
    connection: sqlite3.Connection,
    text: str,
    namespace: str | None = None,
    include_members: bool = False,
) -> dict[str, Any]:
    exact_key = match_key(text)
    stripped_key = stripped_name_key(text)
    keys = [exact_key] + (
        [stripped_key] if stripped_key and stripped_key != exact_key else []
    )
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rank, key in enumerate(keys):
        rows = dict_rows(
            connection.execute(
                "SELECT * FROM brand_match_index WHERE lookup_key = ? "
                "ORDER BY CASE match_status WHEN 'accepted' THEN 0 WHEN 'needs_review' THEN 1 ELSE 2 END, "
                "source_poi_count DESC, brand_family_id",
                (key,),
            )
        )
        for row in rows:
            identity = (row["brand_family_id"], row["match_source"])
            if identity in seen:
                continue
            seen.add(identity)
            context = family_context(
                connection, row["brand_family_id"], namespace, include_members
            )
            usable = row["match_status"] == "accepted" and bool(
                context["usable_groups"]
            )
            canonical = row["match_source"] == "canonical"
            if usable and canonical:
                score = 100 if rank == 0 else 90
            elif usable:
                score = 80 if rank == 0 else 70
            elif row["match_status"] == "excluded":
                score = 10 if rank == 0 else 5
            else:
                score = 50 if rank == 0 else 40
            hits.append(
                {
                    **row,
                    "match_mode": "exact" if rank == 0 else "descriptor_stripped",
                    "decision_status": "accepted" if usable else row["match_status"],
                    "match_score": score,
                    "context": context,
                }
            )
    hits.sort(
        key=lambda hit: (
            -hit["match_score"],
            hit["brand_family_id"],
            hit["match_source"],
        )
    )
    primary_score = hits[0]["match_score"] if hits else None
    for hit in hits:
        hit["is_primary"] = hit["match_score"] == primary_score
    primary = [hit for hit in hits if hit["is_primary"]]
    return {
        "input_text": text,
        "lookup_key": exact_key,
        "namespace_filter": namespace,
        "hits": primary,
        "review_alternatives": [hit for hit in hits if not hit["is_primary"]],
        "ambiguous": len({hit["brand_family_id"] for hit in primary}) > 1,
        "has_accepted_decision": any(
            hit["decision_status"] == "accepted" for hit in primary
        ),
    }


def lookup_poi(
    connection: sqlite3.Connection, poi_id: str, include_members: bool = False
) -> dict[str, Any]:
    memberships = dict_rows(
        connection.execute(
            "SELECT m.*, g.group_status, g.n_accepted AS group_accepted_count, "
            "g.n_needs_review AS group_needs_review_count "
            "FROM brand_members m JOIN brand_groups g USING (brand_group_id) "
            "WHERE m.poi_id = ? ORDER BY CASE m.membership_status "
            "WHEN 'accepted' THEN 0 WHEN 'needs_review' THEN 1 ELSE 2 END, m.brand_group_id",
            (poi_id,),
        )
    )
    accepted = [
        row
        for row in memberships
        if row["membership_status"] == "accepted" and row["group_status"] == "accepted"
    ]
    review = [
        row
        for row in memberships
        if row["membership_status"] == "needs_review"
        or row["group_status"] == "needs_review"
    ]
    excluded = [
        row
        for row in memberships
        if row["membership_status"] == "excluded" or row["group_status"] == "excluded"
    ]
    family_ids = sorted({row["brand_family_id"] for row in memberships})
    return {
        "poi_id": poi_id,
        "accepted_memberships": accepted,
        "review_memberships": review,
        "excluded_memberships": excluded,
        "families": [
            family_context(connection, family_id, include_members=include_members)
            for family_id in family_ids
        ],
    }


def packet_row(connection: sqlite3.Connection, row: dict[str, Any]) -> dict[str, Any]:
    poi_id = str(row.get("poi_id") or "")
    direct = (
        lookup_poi(connection, poi_id)
        if poi_id
        else {
            "accepted_memberships": [],
            "review_memberships": [],
            "excluded_memberships": [],
            "families": [],
        }
    )
    sources: list[tuple[str, str]] = []
    if row.get("brand"):
        sources.append(("brand", str(row["brand"])))
    if row.get("name"):
        sources.append(("name", str(row["name"])))
    for alias in alias_values(row.get("aliases")):
        sources.append(("alias", alias))
    namespace = namespace_for(row.get("category"))
    accepted_hits: list[dict[str, Any]] = []
    review_alternatives: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source, value in sources:
        result = lookup_text(connection, value, namespace)
        for hit in result["hits"] + result["review_alternatives"]:
            identity = (source, hit["brand_family_id"])
            if identity in seen:
                continue
            seen.add(identity)
            compact = {
                "source_field": source,
                "source_text": value,
                "match_mode": hit["match_mode"],
                "match_source": hit["match_source"],
                "decision_status": hit["decision_status"],
                "brand_family_id": hit["brand_family_id"],
                "family": hit["context"]["family"],
                "groups": hit["context"]["groups"],
            }
            if hit["decision_status"] == "accepted" and hit["is_primary"]:
                accepted_hits.append(compact)
            else:
                review_alternatives.append(compact)
    if direct["accepted_memberships"]:
        boundary = "accepted_brand_member"
    elif direct["review_memberships"] or review_alternatives:
        boundary = "needs_review"
    elif direct["excluded_memberships"]:
        boundary = "excluded_generic_or_invalid_brand"
    else:
        boundary = "non_brand_or_unresolved"
    return {
        "case_id": row.get("case_id"),
        "poi_id": poi_id,
        "name": row.get("name"),
        "brand": row.get("brand"),
        "category": row.get("category"),
        "inferred_namespace": namespace,
        "direct_membership": direct,
        "accepted_text_hits": accepted_hits,
        "review_alternatives": review_alternatives,
        "brand_boundary": boundary,
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".parquet":
        return pd.read_parquet(path).to_dict("records")
    if path.suffix.casefold() == ".csv":
        return pd.read_csv(path).where(pd.notna, None).to_dict("records")
    raise ValueError("--input must be .parquet or .csv")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text")
    mode.add_argument("--poi-id")
    mode.add_argument("--input", type=Path)
    parser.add_argument("--namespace")
    parser.add_argument("--include-members", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    connection = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    try:
        if args.text:
            result: Any = lookup_text(
                connection, args.text, args.namespace, args.include_members
            )
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        elif args.poi_id:
            result = lookup_poi(connection, args.poi_id, args.include_members)
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        else:
            payload = "".join(
                json.dumps(packet_row(connection, row), ensure_ascii=False) + "\n"
                for row in load_rows(args.input)
            )
    finally:
        connection.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
