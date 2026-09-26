"""Validate authored Stage-1 brand queries and materialized namespace qrels."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from stage1_brand_query_v1_common import (
    GENERATOR_VERSION,
    NAMESPACE_TOKENS,
    OPERATOR_SPECS,
    QRELS_VERSION,
    QUERY_COLUMNS,
    compact_alnum,
    normalize_query,
    read_jsonl,
    strip_diacritics,
)


def _one_keyboard_slip(before: str, after: str) -> bool:
    left = list(normalize_query(before))
    right = list(normalize_query(after))
    if len(left) == len(right):
        changed = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        if len(changed) == 1:
            return True
        return bool(
            len(changed) == 2
            and changed[1] == changed[0] + 1
            and left[changed[0]] == right[changed[1]]
            and left[changed[1]] == right[changed[0]]
        )
    if abs(len(left) - len(right)) != 1:
        return False
    longer, shorter = (left, right) if len(left) > len(right) else (right, left)
    return any(shorter == longer[:i] + longer[i + 1 :] for i in range(len(longer)))


def _has_namespace_token(query: str, namespace: str) -> bool:
    folded = normalize_query(query)
    unaccented = normalize_query(strip_diacritics(query))
    return any(
        normalize_query(token) in folded
        or normalize_query(strip_diacritics(token)) in unaccented
        for token in NAMESPACE_TOKENS.get(namespace, ())
    )


def validate(
    query_path: Path,
    qrels_path: Path,
    packet_path: Path,
    *,
    allow_partial: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    packet_rows = read_jsonl(packet_path)
    packet_by_intent = {str(row["intent_id"]): row for row in packet_rows}
    query_table = pq.read_table(query_path)
    qrels_table = pq.read_table(qrels_path)
    queries = query_table.to_pylist()
    qrels = qrels_table.to_pylist()
    if tuple(query_table.schema.names) != QUERY_COLUMNS:
        errors.append("query parquet schema/order mismatch")

    query_ids: set[str] = set()
    by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_global: dict[str, list[dict[str, Any]]] = defaultdict(list)
    operator_counts: Counter[str] = Counter()
    for row in queries:
        query_id = str(row.get("query_id") or "")
        intent_id = str(row.get("intent_id") or "")
        if query_id in query_ids:
            errors.append(f"duplicate query_id: {query_id}")
        query_ids.add(query_id)
        packet = packet_by_intent.get(intent_id)
        if packet is None:
            errors.append(f"{query_id}: intent missing from packet")
            continue
        if not re.fullmatch(r"brandq1-\d{5}-v\d{2}", query_id):
            errors.append(f"{query_id}: invalid query_id format")
        if row.get("intent_scope") != "BRAND":
            errors.append(f"{query_id}: intent_scope must be BRAND")
        if row.get("qrel_policy") != "FAMILY_NAMESPACE":
            errors.append(f"{query_id}: qrel_policy must be FAMILY_NAMESPACE")
        if row.get("brand_family_id") != packet["brand_family_id"]:
            errors.append(f"{query_id}: brand_family_id mismatch")
        if row.get("namespace_scope") != packet["namespace_scope"]:
            errors.append(f"{query_id}: namespace_scope mismatch")
        if row.get("generator_version") != GENERATOR_VERSION:
            errors.append(f"{query_id}: generator version mismatch")
        if row.get("review_status") not in {"authored", "accepted", "needs_review"}:
            errors.append(f"{query_id}: invalid review_status")
        if row.get("language_tag") not in {"lang_vi", "lang_en", "lang_mixed"}:
            errors.append(f"{query_id}: invalid language_tag")
        query_text = str(row.get("query_text") or "").strip()
        if not query_text:
            errors.append(f"{query_id}: empty query_text")
        operator = str(row.get("variant_operator") or "")
        spec = OPERATOR_SPECS.get(operator)
        if spec is None:
            errors.append(f"{query_id}: unknown operator {operator}")
        elif (row.get("query_variant_family"), row.get("severity")) != spec:
            errors.append(f"{query_id}: family/severity mismatch for {operator}")
        operator_counts[operator] += 1
        if operator == "brand_alias" and query_text not in packet["verified_aliases"]:
            errors.append(f"{query_id}: alias is not verified for family")
        canonical = str(row.get("canonical_brand_query") or "")
        if operator == "brand_mechanical_typo" and not _one_keyboard_slip(
            canonical, query_text
        ):
            errors.append(f"{query_id}: mechanical typo is not one local slip")
        if operator == "brand_case_punct" and compact_alnum(canonical) != compact_alnum(
            query_text
        ):
            errors.append(f"{query_id}: case/punctuation variant changes identity")
        if operator == "brand_space_variant" and compact_alnum(canonical) != compact_alnum(
            query_text
        ):
            errors.append(f"{query_id}: space variant changes identity")
        namespace = str(packet["brand_namespace"])
        if packet["requires_namespace_token"] and not _has_namespace_token(
            query_text, namespace
        ):
            errors.append(f"{query_id}: multi-namespace family query lacks namespace token")
        normalized = normalize_query(query_text)
        normalized_global[normalized].append(row)
        by_intent[intent_id].append(row)

    for intent_id, rows in by_intent.items():
        if not 2 <= len(rows) <= 6:
            errors.append(f"{intent_id}: expected 2-6 query rows, got {len(rows)}")
        canonicals = [row for row in rows if row["variant_operator"] == "brand_canonical"]
        if len(canonicals) != 1:
            errors.append(f"{intent_id}: expected exactly one brand_canonical row")
        canonical_values = {str(row["canonical_brand_query"]) for row in rows}
        if len(canonical_values) != 1:
            errors.append(f"{intent_id}: canonical_brand_query is inconsistent")
        normalized = [normalize_query(row["query_text"]) for row in rows]
        if len(normalized) != len(set(normalized)):
            errors.append(f"{intent_id}: normalized duplicate query")
    authored_intents = set(by_intent)
    expected_intents = set(packet_by_intent)
    if not authored_intents.issubset(expected_intents):
        errors.append("authored intent set contains unknown values")
    if not allow_partial and authored_intents != expected_intents:
        errors.append("final release must cover every packet intent")
    for normalized, rows in normalized_global.items():
        intents = {str(row["intent_id"]) for row in rows}
        if len(intents) > 1:
            errors.append(
                f"cross-intent normalized query collision {normalized!r}: {sorted(intents)}"
            )

    qrel_pairs: set[tuple[str, str]] = set()
    qrels_by_query: dict[str, set[str]] = defaultdict(set)
    for row in qrels:
        pair = (str(row.get("query_id") or ""), str(row.get("poi_id") or ""))
        if pair in qrel_pairs:
            errors.append(f"duplicate qrel: {pair}")
        qrel_pairs.add(pair)
        query_id, poi_id = pair
        if query_id not in query_ids:
            errors.append(f"qrel references unknown query: {query_id}")
        if row.get("relation") != "positive_pool":
            errors.append(f"{query_id}: unsupported relation")
        if row.get("qrels_version") != QRELS_VERSION:
            errors.append(f"{query_id}: wrong qrels version")
        qrels_by_query[query_id].add(poi_id)
    query_by_id = {str(row["query_id"]): row for row in queries}
    for query_id, row in query_by_id.items():
        expected = set(packet_by_intent[str(row["intent_id"])]["positive_poi_ids"])
        if qrels_by_query.get(query_id, set()) != expected:
            errors.append(f"{query_id}: qrels differ from packet positive pool")

    accent_collisions: dict[str, set[str]] = defaultdict(set)
    for row in queries:
        accent_collisions[normalize_query(strip_diacritics(row["query_text"]))].add(
            str(row["intent_id"])
        )
    for key, intents in accent_collisions.items():
        if len(intents) > 1:
            warnings.append(f"accent-fold collision {key!r}: {sorted(intents)}")

    return {
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "authored_intents": len(authored_intents),
            "query_rows": len(queries),
            "qrel_rows": len(qrels),
            "operators": dict(sorted(operator_counts.items())),
            "accent_collision_count": len(warnings),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(
        args.queries, args.qrels, args.packet, allow_partial=args.allow_partial
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
