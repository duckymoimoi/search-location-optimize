#!/usr/bin/env python3
"""Deterministically validate an authored Stage-1 POI v6 batch.

The validator proves schema and contract invariants. It intentionally does not
claim to prove naturalness, factual correctness, or complete semantic qrels;
those remain blind-review gates.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from stage1_v6_common import (
    COMPOUND_PAIRS,
    DEFORMING_ERROR_TAGS,
    ERROR_TAGS,
    GENERATOR_VERSION,
    SCHEMA_COLUMNS,
    SLOT_SPECS,
    STRING_COLUMNS,
    TRACE_COLUMNS,
    canonical_csv_list,
    normalize_query,
    parse_acceptable,
    parse_subtype_tags,
    parse_variant_slot,
    read_csv_rows,
    read_jsonl,
    read_parquet_rows,
    sha256_file,
    strip_diacritics,
)


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def check(self, condition: bool, message: str) -> None:
        if not condition:
            self.error(message)


REMOVABLE_CONTEXT_LABELS = (
    "thành phố",
    "cửa hàng",
    "cây xăng",
    "trạm xăng",
    "nhà hàng",
    "nhà thờ",
    "bệnh viện",
    "tòa nhà",
    "siêu thị",
    "đường",
    "phố",
    "phường",
    "xã",
    "quận",
    "huyện",
    "tỉnh",
    "chùa",
    "trường",
    "quán",
    "số",
)


def _retained_context_labels(query: str) -> list[str]:
    """Return review candidates; semantic identity decides whether removal is safe."""

    padded = f" {normalize_query(query)} "
    return [label for label in REMOVABLE_CONTEXT_LABELS if f" {label} " in padded]


def _load_target(path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    table = pq.read_table(path)
    rows = table.to_pylist()
    return rows, {str(row["case_id"]): row for row in rows}


def _load_corpus(
    path: Path,
) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    columns = [
        "poi_id",
        "name",
        "aliases",
        "brand",
        "ref",
        "destination_searchable",
    ]
    rows = pq.read_table(path, columns=columns).to_pylist()
    searchable: set[str] = set()
    identity_index: dict[str, set[str]] = defaultdict(set)
    brand_index: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not row.get("destination_searchable"):
            continue
        poi_id = str(row["poi_id"])
        searchable.add(poi_id)
        values = [row.get("name"), row.get("brand"), row.get("ref")]
        values.extend(row.get("aliases") or [])
        for value in values:
            key = normalize_query(value)
            if key:
                identity_index[key].add(poi_id)
        brand_key = normalize_query(row.get("brand"))
        if brand_key:
            brand_index[brand_key].add(poi_id)
    return searchable, identity_index, brand_index


def _parquet_schema_checks(schema: pa.Schema, validation: Validation) -> None:
    validation.check(
        tuple(schema.names) == SCHEMA_COLUMNS,
        f"Parquet columns/order mismatch: {schema.names}",
    )
    for column in STRING_COLUMNS:
        if column in schema.names:
            validation.check(
                pa.types.is_string(schema.field(column).type),
                f"{column} must be string",
            )
    if "acceptable_poi_ids" in schema.names:
        value_type = schema.field("acceptable_poi_ids").type
        validation.check(
            pa.types.is_list(value_type) and pa.types.is_string(value_type.value_type),
            "acceptable_poi_ids must be list<string>",
        )
    if "n_acceptable" in schema.names:
        validation.check(
            pa.types.is_integer(schema.field("n_acceptable").type),
            "n_acceptable must be integer",
        )
    if "is_multipositive" in schema.names:
        validation.check(
            pa.types.is_boolean(schema.field("is_multipositive").type),
            "is_multipositive must be bool",
        )


def _csv_format_checks(path: Path, validation: Validation) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        validation.check(
            tuple(reader.fieldnames or ()) == SCHEMA_COLUMNS,
            "CSV columns/order mismatch",
        )
        for line_number, row in enumerate(reader, start=2):
            try:
                parsed = parse_acceptable(row.get("acceptable_poi_ids"))
            except ValueError as error:
                validation.error(f"CSV line {line_number}: {error}")
                continue
            expected = canonical_csv_list(parsed)
            if row.get("acceptable_poi_ids") != expected:
                validation.error(
                    f"CSV line {line_number}: acceptable_poi_ids must be canonical JSON {expected}"
                )
            if row.get("is_multipositive") not in {"true", "false"}:
                validation.error(
                    f"CSV line {line_number}: is_multipositive must be lowercase true/false"
                )


SINGLE_ALIAS_TAGS = frozenset(
    {
        "acronym_expand_contract",
        "verified_descriptor_variant",
        "verified_name_fragment",
    }
)


def _parse_single_slots(raw: str | None) -> set[str]:
    if not raw:
        return set()
    slots = {part.strip() for part in str(raw).split(",") if part.strip()}
    unknown = slots - {"v03", "v04", "v05", "v06"}
    if unknown:
        raise ValueError(f"Invalid --allow-single-slots: {sorted(unknown)}")
    return slots


def _query_type_valid(row: dict[str, Any], slot: str) -> bool:
    parts = str(row["query_types"]).split("|")
    if len(parts) != 3:
        return False
    if parts[0] != row["primary_sampling_stratum"]:
        return False
    expected = SLOT_SPECS[slot]["slot_tag"].split("|")
    if slot in {"v03", "v04", "v05", "v06"}:
        expected = [*expected, "controlled_single"]
    if parts[1] not in expected:
        return False
    return parts[2] in {"lang_vi", "lang_en", "lang_mixed"}


def _digits(value: str) -> list[str]:
    return re.findall(r"\d+[A-Za-z]?", value)


def _source_span_key(value: Any) -> str | None:
    text = str(value or "").strip()
    lowered = text.casefold()
    if not text or "full strip" in lowered or "all diacritics" in lowered:
        return None
    source = text.split("->", 1)[0].split("→", 1)[0].strip()
    if "(added)" in source.casefold():
        return None
    source = re.sub(r"\s*\((?:omitted|added)\)\s*$", "", source, flags=re.I)
    key = normalize_query(source)
    return key or None


def _affected_span_pair(value: Any) -> tuple[str, str] | None:
    """Parse the human-readable trace form without guessing an unstated edit."""

    text = str(value or "").strip()
    separator = "->" if "->" in text else "→" if "→" in text else None
    if separator is None:
        return None
    source, mutated = (part.strip() for part in text.split(separator, 1))
    lowered = source.casefold()
    if "full strip" in lowered or "all diacritics" in lowered:
        return None
    omitted = bool(re.search(r"\(omitted\)\s*$", source, flags=re.I))
    source = re.sub(r"\s*\((?:omitted|added)\)\s*$", "", source, flags=re.I)
    if omitted:
        mutated = ""
    return source.strip(), mutated.strip()


def _trace_reconstructs(record: dict[str, Any]) -> bool | None:
    """Return whether local trace spans fully reconstruct after_text.

    Non-local operators need operator-specific logic, so they are left to their
    existing checks instead of creating false certainty here.
    """

    non_local = {
        "full_diacritic_strip",
        "token_order_variant",
        "slash_address_spoken",
        "space_punct_variant",
        "token_boundary_error",
        "acronym_expand_contract",
        "acronym_case",
        "raw_ime_sequence",
        "verified_name_fragment",
        "full_address_paste",
    }
    tags = {str(tag) for tag in record.get("error_tags") or []}
    spans = list(record.get("affected_spans") or [])
    if tags & non_local or any("(added)" in str(span).casefold() for span in spans):
        return None
    pairs = [_affected_span_pair(span) for span in spans]
    if not pairs or any(pair is None for pair in pairs):
        return False

    states = {str(record.get("before_text") or "")}
    for pair in pairs:
        assert pair is not None
        source, mutated = pair
        if not source:
            return False
        next_states: set[str] = set()
        for state in states:
            start = 0
            while True:
                index = state.find(source, start)
                if index < 0:
                    break
                next_states.add(state[:index] + mutated + state[index + len(source) :])
                start = index + 1
        if not next_states:
            return False
        states = next_states
    expected = normalize_query(record.get("after_text"))
    return any(normalize_query(state) == expected for state in states)


def _mechanical_realization(source: str, mutated: str) -> str:
    """Classify a single local keyboard slip for distribution diagnostics."""

    before = list(source.casefold())
    after = list(mutated.casefold())
    if len(before) == len(after):
        changed = [i for i, (left, right) in enumerate(zip(before, after)) if left != right]
        if len(changed) == 1:
            return "substitute"
        if (
            len(changed) == 2
            and changed[1] == changed[0] + 1
            and before[changed[0]] == after[changed[1]]
            and before[changed[1]] == after[changed[0]]
        ):
            return "transpose"
    if len(after) == len(before) + 1:
        for index in range(len(after)):
            if before != after[:index] + after[index + 1 :]:
                continue
            duplicated = (index > 0 and after[index] == after[index - 1]) or (
                index + 1 < len(after) and after[index] == after[index + 1]
            )
            if index >= len(before):
                return "terminal_duplicate" if duplicated else "terminal_insert"
            return "internal_duplicate" if duplicated else "internal_insert"
    if len(before) == len(after) + 1:
        for index in range(len(before)):
            if after == before[:index] + before[index + 1 :]:
                return "terminal_delete" if index == len(before) - 1 else "internal_delete"
    return "other"


def _mechanical_position(source: str, mutated: str) -> str:
    before = list(source.casefold())
    after = list(mutated.casefold())
    changed = [
        index
        for index, (left, right) in enumerate(zip(before, after))
        if left != right
    ]
    if not changed and len(before) != len(after):
        changed = [min(len(before), len(after))]
    if not changed or not before:
        return "unknown"
    position = changed[0]
    if position < len(before) / 3:
        return "early"
    if position < 2 * len(before) / 3:
        return "middle"
    return "tail"


def _identity_span_keys(target: dict[str, Any]) -> list[str]:
    """Return conservative name/discriminator surfaces for difficulty QA."""

    fields = ["name", "street", "housenumber", "ref"]
    if str(target.get("primary_sampling_stratum")) == "brand_branch":
        brand_key = normalize_query(target.get("brand"))
        name_key = normalize_query(target.get("name"))
        fields = ["street", "housenumber", "ref", "subdistrict"]
        if name_key and name_key != brand_key:
            fields.insert(0, "name")
    keys = [normalize_query(target.get(field)) for field in fields]
    return [key for key in keys if key]


def _trace_targets_identity(record: dict[str, Any], target: dict[str, Any]) -> bool:
    keys = _identity_span_keys(target)
    generic = {
        "duong",
        "pho",
        "phuong",
        "xa",
        "quan",
        "huyen",
        "tinh",
        "thanh pho",
        "cua hang",
        "nha hang",
        "khach san",
        "ngan hang",
        "truong",
        "benh vien",
    }
    for affected in record.get("affected_spans") or []:
        pair = _affected_span_pair(affected)
        if pair is None:
            continue
        source_key = normalize_query(strip_diacritics(pair[0]))
        if not source_key or source_key in generic:
            continue
        for identity_key in keys:
            folded_identity = normalize_query(strip_diacritics(identity_key))
            if source_key in folded_identity or folded_identity in source_key:
                return True
    return False


def _trace_mutation_point_count(record: dict[str, Any]) -> int:
    """Count declared, non-empty mutation points without guessing tag semantics."""

    count = 0
    for affected in record.get("affected_spans") or []:
        lowered = str(affected).casefold()
        if "full strip" in lowered or "all diacritics" in lowered:
            continue
        pair = _affected_span_pair(affected)
        if pair is None:
            if "->" in str(affected) or "→" in str(affected):
                count += 1
            continue
        source, mutated = pair
        if normalize_query(source) != normalize_query(mutated):
            count += 1
    return count


def _trace_has_early_mutation(record: dict[str, Any]) -> bool:
    """Return whether the first non-numeric token is locally deformed."""

    before = str(record.get("before_text") or "")
    matches = list(re.finditer(r"[^\W_]+", before, flags=re.UNICODE))

    def belongs_to_digit_code(match: re.Match[str]) -> bool:
        """Treat every lexical fragment of a whitespace-delimited code as immutable."""

        left = match.start()
        while left > 0 and not before[left - 1].isspace():
            left -= 1
        right = match.end()
        while right < len(before) and not before[right].isspace():
            right += 1
        return any(char.isdigit() for char in before[left:right])

    # Address/building codes such as ``19B`` and ``A12`` are immutable under
    # the contract.  Do not force an early mutation on a token that contains
    # digits; select the first lexical token after any numeric/code prefix.
    identity_matches = [
        match
        for match in matches
        if not belongs_to_digit_code(match)
    ]
    if not identity_matches:
        return False
    token_left, token_right = identity_matches[0].span()
    folded_before = before.casefold()
    for affected in record.get("affected_spans") or []:
        pair = _affected_span_pair(affected)
        if pair is None or not pair[0]:
            continue
        source = pair[0].casefold()
        start = folded_before.find(source)
        if start < 0:
            continue
        end = start + len(source)
        # A whole-query token-order span does not prove the first token itself
        # was mistyped. The declared source must be local to that token.
        if start >= token_left and end <= token_right:
            return True
    return False


def _difficulty_stats(
    trace_by_variant: dict[str, dict[str, Any]],
    target_by_case: dict[str, dict[str, Any]],
    single_slots: set[str] | None = None,
) -> dict[str, Any]:
    identity_by_slot: Counter[str] = Counter()
    parent_counts: Counter[str] = Counter()
    mechanical: Counter[str] = Counter()
    mechanical_positions: Counter[str] = Counter()
    mechanical_pairs: Counter[str] = Counter()
    branch_brand_typo_variants: list[str] = []
    review_variants: list[str] = []
    low_point_variants: list[str] = []
    excess_point_variants: list[str] = []
    mutation_points: Counter[int] = Counter()
    late_only_variants: list[str] = []
    for variant_id, record in trace_by_variant.items():
        case_id, slot = variant_id.rsplit("-", 1)
        parent_counts[str(record.get("parent_variant_id") or "")[-3:]] += 1
        target = target_by_case.get(case_id, {})
        if _trace_targets_identity(record, target):
            identity_by_slot[slot] += 1
        else:
            review_variants.append(variant_id)
        point_count = _trace_mutation_point_count(record)
        mutation_points[point_count] += 1
        tags = [str(tag) for tag in record.get("error_tags") or []]
        if slot in (single_slots or set()):
            if point_count != 1:
                low_point_variants.append(variant_id)
            waive_early = slot == "v05" and tags and set(tags) <= SINGLE_ALIAS_TAGS
            if not waive_early and not _trace_has_early_mutation(record):
                late_only_variants.append(variant_id)
        else:
            if point_count < 2:
                low_point_variants.append(variant_id)
            if point_count > 4:
                excess_point_variants.append(variant_id)
            if not _trace_has_early_mutation(record):
                late_only_variants.append(variant_id)

        spans = list(record.get("affected_spans") or [])
        if "mechanical_typo" not in tags:
            continue
        candidates: list[tuple[str, str]] = []
        if len(tags) == len(spans):
            pair = _affected_span_pair(spans[tags.index("mechanical_typo")])
            if pair is not None:
                candidates.append(pair)
        if not candidates:
            candidates = [
                pair
                for pair in (_affected_span_pair(span) for span in spans)
                if pair is not None
            ]
        realization = "other"
        for source, mutated in candidates:
            candidate = _mechanical_realization(source, mutated)
            if candidate != "other":
                realization = candidate
                mechanical_positions[_mechanical_position(source, mutated)] += 1
                mechanical_pairs[f"{normalize_query(source)} -> {normalize_query(mutated)}"] += 1
                break
        mechanical[realization] += 1
        if str(target.get("primary_sampling_stratum")) == "brand_branch":
            brand_key = normalize_query(target.get("brand") or target.get("name"))
            if brand_key and any(
                (source_key := normalize_query(pair[0]))
                and (source_key in brand_key or brand_key in source_key)
                for pair in candidates
            ):
                branch_brand_typo_variants.append(variant_id)

    total = len(trace_by_variant)
    identity_total = sum(identity_by_slot.values())
    return {
        "trace_rows": total,
        "parent_slots": dict(sorted(parent_counts.items())),
        "identity_targeted_rows": identity_total,
        "identity_targeted_rate": identity_total / total if total else 0.0,
        "identity_targeted_by_slot": dict(sorted(identity_by_slot.items())),
        "mechanical_realizations": dict(sorted(mechanical.items())),
        "mechanical_positions": dict(sorted(mechanical_positions.items())),
        "repeated_mechanical_pairs": {
            pair: count
            for pair, count in mechanical_pairs.most_common()
            if count > 2
        },
        "branch_brand_typo_count": len(branch_brand_typo_variants),
        "branch_brand_typo_sample": branch_brand_typo_variants[:25],
        "review_variant_count": len(review_variants),
        "review_variant_ids_sample": review_variants[:25],
        "multi_error_rows": total - len(low_point_variants),
        "multi_error_rate": (total - len(low_point_variants)) / total if total else 0.0,
        "low_point_variant_count": len(low_point_variants),
        "low_point_variant_ids_sample": low_point_variants[:25],
        "excess_point_variant_count": len(excess_point_variants),
        "excess_point_variant_ids_sample": excess_point_variants[:25],
        "mutation_point_distribution": dict(sorted(mutation_points.items())),
        "early_mutation_rows": total - len(late_only_variants),
        "early_mutation_rate": (total - len(late_only_variants)) / total if total else 0.0,
        "late_only_variant_count": len(late_only_variants),
        "late_only_variant_ids_sample": late_only_variants[:25],
    }


def _merged_alphanumeric_tokens(before: str, after: str) -> list[str]:
    before_tokens = re.findall(r"[^\W_]+", before, flags=re.UNICODE)
    after_tokens = {
        normalize_query(token)
        for token in re.findall(r"[^\W_]+", after, flags=re.UNICODE)
    }
    merged: list[str] = []
    for left, right in zip(before_tokens, before_tokens[1:]):
        candidate = normalize_query(left + right)
        if candidate in after_tokens:
            merged.append(left + right)
    return merged


def _trace_has_token_boundary_change(record: dict[str, Any]) -> bool:
    """Return whether a trace changes whitespace while preserving characters."""

    for affected in record.get("affected_spans") or []:
        pair = _affected_span_pair(affected)
        if pair is None:
            continue
        source, mutated = pair
        if source == mutated:
            continue
        source_compact = re.sub(r"\s+", "", source)
        mutated_compact = re.sub(r"\s+", "", mutated)
        if (
            source_compact
            and source_compact.casefold() == mutated_compact.casefold()
            and bool(re.search(r"\s", source)) != bool(re.search(r"\s", mutated))
        ):
            return True
    return False


def _slash_change_valid(before: str, after: str, tags: list[str]) -> bool:
    """Allow slash removal only for an explicit spoken-address realization."""

    before_count = before.count("/")
    after_count = after.count("/")
    if "slash_address_spoken" in tags:
        return before_count > 0 and after_count < before_count
    return before_count == after_count


def _validate_trace(
    trace_path: Path,
    rows_by_variant: dict[str, dict[str, Any]],
    cases: set[str],
    validation: Validation,
) -> dict[str, dict[str, Any]]:
    records = read_jsonl(trace_path)
    trace_by_variant: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, start=1):
        missing = [column for column in TRACE_COLUMNS if column not in record]
        if missing:
            validation.error(f"Trace record {index} missing {missing}")
            continue
        variant_id = str(record["variant_id"])
        if variant_id in trace_by_variant:
            validation.error(f"Duplicate trace variant_id: {variant_id}")
            continue
        trace_by_variant[variant_id] = record

    expected = {f"{case_id}-v0{slot}" for case_id in cases for slot in (3, 4, 5, 6)}
    validation.check(
        set(trace_by_variant) == expected,
        "Trace must contain exactly v03-v06 for every case",
    )
    realizations_by_case: dict[str, dict[str, str]] = defaultdict(dict)
    for variant_id in sorted(expected & set(trace_by_variant)):
        record = trace_by_variant[variant_id]
        row = rows_by_variant[variant_id]
        parent_id = str(record["parent_variant_id"])
        if parent_id not in rows_by_variant:
            validation.error(f"{variant_id}: trace parent missing: {parent_id}")
            continue
        if parent_id.rsplit("-", 1)[0] != variant_id.rsplit("-", 1)[
            0
        ] or not parent_id.endswith(("-v01", "-v02")):
            validation.error(f"{variant_id}: parent must be same-case v01/v02")
        parent = rows_by_variant[parent_id]
        tags = [str(tag) for tag in record.get("error_tags") or []]
        validation.check(
            tags == parse_subtype_tags(row["variant_subtype"]),
            f"{variant_id}: trace tags != subtype",
        )
        validation.check(
            str(record["before_text"]) == parent["query_text"],
            f"{variant_id}: trace before_text != parent",
        )
        validation.check(
            str(record["after_text"]) == row["query_text"],
            f"{variant_id}: trace after_text != query",
        )
        validation.check(
            bool(record.get("affected_spans")), f"{variant_id}: affected_spans empty"
        )
        affected_spans = list(record.get("affected_spans") or [])
        for affected in affected_spans:
            pair = _affected_span_pair(affected)
            if pair is None:
                continue
            source, mutated = pair
            if source and normalize_query(source) == normalize_query(mutated):
                validation.error(f"{variant_id}: no-op affected span: {affected}")
        if {"regional_abbrev", "administrative_abbrev"} & set(tags):
            validation.check(
                not any("(added)" in str(span).casefold() for span in affected_spans),
                f"{variant_id}: abbreviation must transform a component present in parent",
            )
        validation.check(
            str(record["reviewer_status"]) in {"authored", "accepted"},
            f"{variant_id}: invalid trace reviewer_status",
        )
        reconstruction = _trace_reconstructs(record)
        if reconstruction is False:
            validation.error(
                f"{variant_id}: affected_spans do not fully reconstruct after_text"
            )
        validation.check(
            _digits(parent["query_text"]) == _digits(row["query_text"]),
            f"{variant_id}: digit/code sequence changed",
        )
        validation.check(
            _slash_change_valid(parent["query_text"], row["query_text"], tags),
            f"{variant_id}: slash change requires a realized slash_address_spoken tag",
        )
        merged_tokens = _merged_alphanumeric_tokens(
            parent["query_text"], row["query_text"]
        )
        validation.check(
            not merged_tokens or "token_boundary_error" in tags,
            f"{variant_id}: alphanumeric token merge requires token_boundary_error: {merged_tokens}",
        )
        if "token_boundary_error" in tags:
            validation.check(
                _trace_has_token_boundary_change(record),
                f"{variant_id}: token_boundary_error has no traceable whitespace-boundary change",
            )
        case_id = variant_id.rsplit("-", 1)[0]
        for affected in record.get("affected_spans") or []:
            pair = _affected_span_pair(affected)
            if pair is None:
                continue
            source, mutated = pair
            key = f"{normalize_query(source)} -> {normalize_query(mutated)}"
            previous = realizations_by_case[case_id].get(key)
            if previous and previous != variant_id:
                validation.error(
                    f"{variant_id}: mutation realization {key!r} already used by {previous}"
                )
            else:
                realizations_by_case[case_id][key] = variant_id
    return trace_by_variant


def _significant_discriminator_present(query: str, target: dict[str, Any]) -> bool:
    query_key = normalize_query(query)
    values = [
        target.get("ref"),
        target.get("housenumber"),
        target.get("street"),
        target.get("subdistrict"),
    ]
    prefixes = ("đường ", "phố ", "phường ", "xã ", "quận ", "huyện ")
    for value in values:
        key = normalize_query(value)
        if not key:
            continue
        candidates = {key}
        for prefix in prefixes:
            if key.startswith(prefix):
                candidates.add(key[len(prefix) :])
        if any(candidate and candidate in query_key for candidate in candidates):
            return True
    return False


def _canonical_has_unneeded_admin(
    canonical: str,
    target: dict[str, Any],
    identity_index: dict[str, set[str]],
) -> bool:
    if str(target.get("primary_sampling_stratum")) not in {
        "named_clear",
        "category_local",
    }:
        return False
    official_key = normalize_query(target.get("name"))
    if not official_key or len(identity_index.get(official_key, set())) != 1:
        return False
    canonical_key = normalize_query(canonical)
    for field in ("province", "subdistrict"):
        admin_key = normalize_query(target.get(field))
        if not admin_key:
            continue
        candidates = {admin_key}
        for prefix in ("tỉnh ", "thành phố ", "phường ", "xã ", "quận ", "huyện "):
            if admin_key.startswith(prefix):
                candidates.add(admin_key[len(prefix) :])
        if any(
            candidate and candidate not in official_key and candidate in canonical_key
            for candidate in candidates
        ):
            return True
    return False


def validate_batch(
    *,
    csv_path: Path,
    parquet_path: Path,
    trace_path: Path,
    target_path: Path,
    corpus_path: Path,
    gold_path: Path,
    published_paths: list[Path],
    ban_acronym_case: bool,
    enforce_hard_noise: bool = False,
    allow_partial: bool = False,
    allow_single_slots: set[str] | None = None,
) -> dict[str, Any]:
    single_slots = set(allow_single_slots or ())
    validation = Validation()
    _csv_format_checks(csv_path, validation)
    csv_columns, csv_rows = read_csv_rows(csv_path)
    parquet_schema, parquet_rows = read_parquet_rows(parquet_path)
    _parquet_schema_checks(parquet_schema, validation)
    validation.check(tuple(csv_columns) == SCHEMA_COLUMNS, "CSV schema mismatch")
    validation.check(csv_rows == parquet_rows, "CSV and Parquet rows differ")

    rows = parquet_rows
    rows_by_variant: dict[str, dict[str, Any]] = {}
    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        variant_id = row["variant_id"]
        if variant_id in rows_by_variant:
            validation.error(f"Duplicate variant_id: {variant_id}")
        rows_by_variant[variant_id] = row
        cases[row["case_id"]].append(row)

    target_rows, target_by_case = _load_target(target_path)
    target_cases = [str(row["case_id"]) for row in target_rows]
    if allow_partial:
        validation.check(
            set(cases).issubset(set(target_cases)),
            "Partial query cases must be a subset of target cases",
        )
        target_rows = [row for row in target_rows if str(row["case_id"]) in cases]
        target_by_case = {str(row["case_id"]): row for row in target_rows}
        target_cases = [str(row["case_id"]) for row in target_rows]
    else:
        validation.check(
            set(cases) == set(target_cases), "Query cases must exactly match target cases"
        )
    validation.check(
        len(rows) == 6 * len(target_rows), "Expected six query rows per target"
    )
    expected_variant_order = [
        f"{case_id}-v0{slot}" for case_id in target_cases for slot in range(1, 7)
    ]
    validation.check(
        [row["variant_id"] for row in rows] == expected_variant_order,
        "Query row order must follow target order and v01-v06 slot order",
    )
    validation.check(
        all(bool(row.get("clean_pass")) for row in target_rows),
        "All target rows must have clean_pass=true",
    )

    gold_ids = {
        str(value)
        for value in pq.read_table(gold_path, columns=["poi_id"])["poi_id"].to_pylist()
    }
    target_ids = {str(row["poi_id"]) for row in target_rows}
    validation.check(not (target_ids & gold_ids), "Target POIs overlap gold POIs")

    searchable_ids, identity_index, brand_index = _load_corpus(corpus_path)
    severity_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    normalized_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    v02_context_label_counts: Counter[str] = Counter()
    v02_context_review: list[str] = []

    for case_id, case_rows in sorted(cases.items()):
        target = target_by_case.get(case_id)
        if target is None:
            continue
        slot_rows: dict[str, dict[str, Any]] = {}
        for row in case_rows:
            slot = parse_variant_slot(row["variant_id"])
            if slot is None:
                validation.error(f"{row['variant_id']}: invalid variant suffix")
                continue
            if row["variant_id"] != f"{case_id}-{slot}":
                validation.error(
                    f"{row['variant_id']}: variant_id does not match case_id"
                )
            if slot in slot_rows:
                validation.error(f"{case_id}: duplicate slot {slot}")
            slot_rows[slot] = row
        validation.check(
            set(slot_rows) == set(SLOT_SPECS), f"{case_id}: slots must be v01-v06"
        )
        if set(slot_rows) != set(SLOT_SPECS):
            continue

        canonical = slot_rows["v01"]["query_text"]
        seen: set[str] = set()
        for slot, row in slot_rows.items():
            spec = SLOT_SPECS[slot]
            prefix = f"{row['variant_id']}:"
            severity_counts[row["severity"]] += 1
            normalized_rows[normalize_query(row["query_text"])].append(row)
            validation.check(
                row["canonical_query"] == canonical,
                f"{prefix} canonical_query mismatch",
            )
            validation.check(
                row["intended_poi_id"] == str(target["poi_id"]),
                f"{prefix} intended target mismatch",
            )
            validation.check(
                row["primary_sampling_stratum"]
                == str(target["primary_sampling_stratum"]),
                f"{prefix} stratum mismatch",
            )
            validation.check(
                row["generator_version"] == GENERATOR_VERSION,
                f"{prefix} wrong generator_version",
            )
            validation.check(
                row["query_variant_family"] == spec["family"], f"{prefix} wrong family"
            )
            validation.check(
                row["variant_operator"] == spec["operator"], f"{prefix} wrong operator"
            )
            expected_severity = (
                "SINGLE" if slot in single_slots else spec["severity"]
            )
            validation.check(
                row["severity"] == expected_severity, f"{prefix} wrong severity"
            )
            validation.check(
                _query_type_valid(row, slot), f"{prefix} invalid query_types"
            )
            validation.check(
                bool(row["query_text"].strip()), f"{prefix} empty query_text"
            )
            if slot != "v01":
                validation.check(
                    "." not in row["query_text"],
                    f"{prefix} period is forbidden in v02-v06",
                )
            if slot == "v02":
                retained_labels = _retained_context_labels(row["query_text"])
                if retained_labels:
                    v02_context_review.append(row["variant_id"])
                    v02_context_label_counts.update(retained_labels)
            query_key = normalize_query(row["query_text"])
            validation.check(
                query_key not in seen, f"{case_id}: model-normalized duplicate query"
            )
            seen.add(query_key)

            acceptable = row["acceptable_poi_ids"]
            validation.check(bool(acceptable), f"{prefix} empty acceptable_poi_ids")
            validation.check(
                len(acceptable) == len(set(acceptable)),
                f"{prefix} duplicate acceptable POI",
            )
            validation.check(
                row["intended_poi_id"] in acceptable,
                f"{prefix} intended not acceptable",
            )
            validation.check(
                row["n_acceptable"] == len(acceptable),
                f"{prefix} n_acceptable mismatch",
            )
            validation.check(
                row["is_multipositive"] == (len(acceptable) > 1),
                f"{prefix} is_multipositive mismatch",
            )
            missing = sorted(set(acceptable) - searchable_ids)
            validation.check(
                not missing,
                f"{prefix} acceptable IDs missing/non-searchable: {missing[:5]}",
            )
            validation.check(
                row["review_status"] == "authored",
                f"{prefix} review_status must be authored for publish",
            )

            exact_candidates = identity_index.get(query_key, set())
            if exact_candidates and not exact_candidates.issubset(set(acceptable)):
                absent = sorted(exact_candidates - set(acceptable))
                validation.error(
                    f"{prefix} exact-identity qrels omit {len(absent)} candidates: {absent[:5]}"
                )

            if slot in {"v01", "v02"}:
                validation.check(
                    row["variant_subtype"] == spec["subtype"], f"{prefix} wrong subtype"
                )
            else:
                tags = parse_subtype_tags(row["variant_subtype"])
                if slot in single_slots:
                    validation.check(
                        len(tags) == 1 and len(set(tags)) == 1,
                        f"{prefix} single-error row needs exactly one tag",
                    )
                    validation.check(
                        all(tag in ERROR_TAGS for tag in tags),
                        f"{prefix} unknown hard-noise tag",
                    )
                    validation.check(
                        len(set(tags) & DEFORMING_ERROR_TAGS) == 1,
                        f"{prefix} single-error tag must be deforming",
                    )
                    if slot == "v03":
                        validation.check(
                            tags == ["mechanical_typo"],
                            f"{prefix} v03 single must be mechanical_typo only",
                        )
                        validation.check(
                            "token_boundary_error" not in tags,
                            f"{prefix} v03 single must not use token_boundary_error",
                        )
                    if slot == "v05":
                        validation.check(
                            set(tags) <= SINGLE_ALIAS_TAGS,
                            f"{prefix} v05 single must be a verified alias tag",
                        )
                else:
                    validation.check(
                        2 <= len(tags) <= 3 and len(set(tags)) == len(tags),
                        f"{prefix} hard-noisy row needs 2-3 distinct tags",
                    )
                    validation.check(
                        all(tag in ERROR_TAGS for tag in tags),
                        f"{prefix} unknown hard-noise tag",
                    )
                    validation.check(
                        len(set(tags) & DEFORMING_ERROR_TAGS) >= 2,
                        f"{prefix} needs at least two deforming error types; accent normalization does not count",
                    )
                    validation.check(
                        all(
                            frozenset(pair) in COMPOUND_PAIRS
                            for pair in combinations(tags, 2)
                        ),
                        f"{prefix} hard-noise tag set is not pairwise compatible",
                    )
                for tag in tags:
                    tag_counts[tag] += 1
                pair_counts["+".join(tags)] += 1
            if ban_acronym_case and "acronym_case" in parse_subtype_tags(
                row["variant_subtype"]
            ):
                validation.error(f"{prefix} acronym_case is banned for this pilot")

        noisy_tag_sets = [
            frozenset(parse_subtype_tags(slot_rows[slot]["variant_subtype"]))
            for slot in ("v03", "v04", "v05", "v06")
        ]
        validation.check(
            len(set(noisy_tag_sets)) == 4,
            f"{case_id}: v03-v06 must use four distinct hard-noise tag sets",
        )
        slash_spoken_uses = sum(
            "slash_address_spoken"
            in parse_subtype_tags(slot_rows[slot]["variant_subtype"])
            for slot in ("v03", "v04", "v05", "v06")
        )
        validation.check(
            slash_spoken_uses <= 1,
            f"{case_id}: slash_address_spoken may appear in at most one noisy slot",
        )

        official_name = str(target.get("name") or "").strip()
        if official_name:
            validation.check(
                normalize_query(official_name) in normalize_query(canonical),
                f"{case_id}-v01: official name is not a contiguous span",
            )
        if _canonical_has_unneeded_admin(canonical, target, identity_index):
            validation.warn(
                f"{case_id}-v01: unique official name has added admin tokens; semantic review must justify them"
            )
        if str(target.get("primary_sampling_stratum")) == "brand_branch":
            v02 = slot_rows["v02"]
            brand_key = normalize_query(target.get("brand") or target.get("name"))
            if (
                brand_key
                and normalize_query(v02["query_text"]) == brand_key
                and len(brand_index.get(brand_key, set())) > 1
            ):
                validation.error(f"{case_id}-v02: bare multi-branch brand")
            if not _significant_discriminator_present(v02["query_text"], target):
                validation.warn(
                    f"{case_id}-v02: no deterministic address/ref discriminator found; semantic review required"
                )
            if single_slots and (
                str(target.get("street") or "").strip()
                or str(target.get("housenumber") or "").strip()
            ):
                query_key = normalize_query(v02["query_text"])
                loc_ok = False
                for field in ("housenumber", "street"):
                    key = normalize_query(target.get(field))
                    if not key:
                        continue
                    candidates = {key}
                    for prefix in ("đường ", "phố "):
                        if key.startswith(prefix):
                            candidates.add(key[len(prefix) :])
                    if any(candidate and candidate in query_key for candidate in candidates):
                        loc_ok = True
                        break
                validation.check(
                    loc_ok,
                    f"{case_id}-v02: brand_branch must keep street or housenumber",
                )

    trace_by_variant = _validate_trace(
        trace_path, rows_by_variant, set(cases), validation
    )
    difficulty = _difficulty_stats(
        trace_by_variant, target_by_case, single_slots=single_slots
    )
    if single_slots:
        for case_id, slot_rows in cases.items():
            v03 = trace_by_variant.get(f"{case_id}-v03")
            v04 = trace_by_variant.get(f"{case_id}-v04")
            if not v03 or not v04:
                continue
            def _typo_keys(record: dict[str, Any]) -> set[str]:
                keys: set[str] = set()
                for affected in record.get("affected_spans") or []:
                    pair = _affected_span_pair(affected)
                    if pair is None:
                        continue
                    source, mutated = pair
                    if normalize_query(source) == normalize_query(mutated):
                        continue
                    keys.add(
                        f"{normalize_query(source)} -> {normalize_query(mutated)}"
                    )
                    keys.add(
                        f"{normalize_query(strip_diacritics(source))} -> {normalize_query(strip_diacritics(mutated))}"
                    )
                return keys
            overlap = _typo_keys(v03) & _typo_keys(v04)
            validation.check(
                not overlap,
                f"{case_id}: v03 first-token typo must differ from v04: {sorted(overlap)[:2]}",
            )
    validation.check(
        int(difficulty["low_point_variant_count"]) == 0,
        (
            "Single-error slots need exactly one mutation point; compound slots need at least two"
            if single_slots
            else "Every v03-v06 row must declare at least two meaningful mutation points"
        ),
    )
    validation.check(
        int(difficulty["excess_point_variant_count"]) == 0,
        "Every v03-v06 row must stay at or below four mutation points",
    )
    validation.check(
        int(difficulty["late_only_variant_count"]) == 0,
        "Every v03-v06 row must locally deform its first non-numeric token",
    )

    n_cases = len(target_rows)
    if single_slots:
        expected_severity = {
            "CLEAN": 2 * n_cases,
            "SINGLE": len(single_slots) * n_cases,
            "COMPOUND": (4 - len(single_slots)) * n_cases,
        }
    else:
        expected_severity = {
            "CLEAN": 2 * n_cases,
            "COMPOUND": 4 * n_cases,
        }
    validation.check(
        dict(severity_counts) == expected_severity,
        f"Severity distribution mismatch: {dict(severity_counts)}",
    )

    noisy_rows = max(1, 4 * len(target_rows))
    if tag_counts["mechanical_typo"] / noisy_rows > 0.50:
        validation.warn(
            "mechanical_typo appears in more than 50% of v03-v06 rows; review for formulaic authoring"
        )
    low_deforming_count = sum(
        len(
            set(
                parse_subtype_tags(row["variant_subtype"])
            )
            & DEFORMING_ERROR_TAGS
        )
        < 2
        for row in rows
        if parse_variant_slot(row["variant_id"]) in {"v03", "v04", "v05", "v06"}
    )
    trace_rows = max(1, int(difficulty["trace_rows"]))
    preferred_points = sum(
        int(count)
        for points, count in difficulty["mutation_point_distribution"].items()
        if int(points) in {2, 3}
    )
    if preferred_points / trace_rows < 0.70:
        validation.warn(
            "fewer than 70% of controlled rows use the preferred 2-3 mutation points"
        )
    if difficulty["identity_targeted_rows"] / trace_rows < 0.60:
        validation.warn(
            "fewer than 60% of noisy rows target identity/discriminator spans; review mutation placement"
        )
    parent_slots = difficulty["parent_slots"]
    if trace_rows and int(parent_slots.get("v02", 0)) / trace_rows < 0.50:
        validation.warn(
            "fewer than 50% of noisy rows use v02 as parent; excess v01 context can make errors too easy"
        )
    mechanical = difficulty["mechanical_realizations"]
    mechanical_total = sum(int(value) for value in mechanical.values())
    if mechanical_total:
        high_value = int(mechanical.get("transpose", 0)) + int(
            mechanical.get("substitute", 0)
        )
        if high_value / mechanical_total < 0.50:
            validation.warn(
                "fewer than 50% of mechanical typos are transpose/substitute realizations"
            )
        terminal_add = int(mechanical.get("terminal_duplicate", 0)) + int(
            mechanical.get("terminal_insert", 0)
        )
        if terminal_add / mechanical_total > 0.10:
            validation.warn(
                "more than 10% of mechanical typos add/duplicate the final character"
            )
        if int(mechanical.get("other", 0)) / mechanical_total > 0.20:
            validation.warn(
                "more than 20% of mechanical typo traces are not isolated as one local slip"
            )
        positions = difficulty["mechanical_positions"]
        positioned = sum(int(value) for value in positions.values())
        early_middle = int(positions.get("early", 0)) + int(
            positions.get("middle", 0)
        )
        if positioned and early_middle / positioned < 0.70:
            validation.warn(
                "fewer than 70% of classifiable mechanical typos occur in the early/middle token positions"
            )
    if int(difficulty["branch_brand_typo_count"]):
        validation.warn(
            f"{difficulty['branch_brand_typo_count']} branch rows mutate the brand span; review handoff/deduplication with the brand dataset"
        )
    if cases and len(v02_context_review) / len(cases) > 0.25:
        validation.warn(
            f"{len(v02_context_review)} v02 rows retain possible context labels; review identity-core trimming"
        )
    compound_rows = max(1, 4 * len(target_rows))
    pair_frequencies = sorted(pair_counts.values(), reverse=True)
    if pair_frequencies and pair_frequencies[0] / compound_rows > 0.35:
        validation.warn(
            "one hard-noise tag set exceeds 35% of v03-v06 rows; review distribution by stratum"
        )
    if sum(pair_frequencies[:2]) / compound_rows >= 0.50:
        validation.warn(
            "top two hard-noise tag sets cover at least 50% of v03-v06 rows; review for template repetition"
        )

    collision_records: list[dict[str, Any]] = []
    for key, collision_rows in normalized_rows.items():
        if len(collision_rows) < 2:
            continue
        acceptable_sets = {
            tuple(sorted(row["acceptable_poi_ids"])) for row in collision_rows
        }
        record = {
            "normalized_query": key,
            "variant_ids": [row["variant_id"] for row in collision_rows],
            "acceptable_sets": [list(values) for values in sorted(acceptable_sets)],
        }
        collision_records.append(record)
        if len(acceptable_sets) > 1:
            validation.error(
                f"Unadjudicated intra-batch collision: {record['variant_ids']}"
            )
        else:
            validation.warn(
                f"Duplicate weighted query with identical qrels: {record['variant_ids']}"
            )

    published_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in published_paths:
        _, published_rows = read_parquet_rows(path)
        for row in published_rows:
            published_index[normalize_query(row["query_text"])].append(row)
    for key, current_rows in normalized_rows.items():
        previous_rows = published_index.get(key, [])
        if not previous_rows:
            continue
        all_rows = current_rows + previous_rows
        acceptable_sets = {tuple(sorted(row["acceptable_poi_ids"])) for row in all_rows}
        variants = [row["variant_id"] for row in all_rows]
        if len(acceptable_sets) > 1:
            validation.error(f"Unadjudicated cross-batch collision: {variants}")
        else:
            validation.warn(f"Cross-batch duplicate with identical qrels: {variants}")

    return {
        "verdict": "PASS" if not validation.errors else "FAIL",
        "errors": validation.errors,
        "warnings": validation.warnings,
        "stats": {
            "n_cases": len(cases),
            "n_queries": len(rows),
            "severity": dict(sorted(severity_counts.items())),
            "error_tags": dict(sorted(tag_counts.items())),
            "compound_pairs": dict(sorted(pair_counts.items())),
            "low_deforming_row_count": low_deforming_count,
            "v02_context_labels": {
                "row_count": len(v02_context_review),
                "labels": dict(sorted(v02_context_label_counts.items())),
                "variant_ids_sample": v02_context_review[:25],
            },
            "difficulty": difficulty,
            "n_normalized_collisions": len(collision_records),
        },
        "collisions": collision_records,
        "files": {
            "csv": {"path": str(csv_path), "sha256": sha256_file(csv_path)},
            "parquet": {"path": str(parquet_path), "sha256": sha256_file(parquet_path)},
            "trace": {"path": str(trace_path), "sha256": sha256_file(trace_path)},
        },
        "semantic_review_required": [
            "query naturalness and intent preservation",
            "facts not inferable from target/corpus structure",
            "qrels completeness beyond exact identity matches",
            "brand/namespace adjudication",
            "whether each mutation text truly realizes its declared error tag",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--published", type=Path, action="append", default=[])
    parser.add_argument("--report", type=Path)
    parser.add_argument("--ban-acronym-case", action="store_true")
    parser.add_argument(
        "--enforce-hard-noise",
        action="store_true",
        help="Require 2+ mutation points and an early identity mutation in every noisy row",
    )
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument(
        "--allow-single-slots",
        default="",
        help="Comma-separated noisy slots allowed to be 1-tag/1-point SINGLE (e.g. v03,v05)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = validate_batch(
            csv_path=args.csv,
            parquet_path=args.parquet,
            trace_path=args.trace,
            target_path=args.target,
            corpus_path=args.corpus,
            gold_path=args.gold,
            published_paths=args.published,
            ban_acronym_case=args.ban_acronym_case,
            enforce_hard_noise=args.enforce_hard_noise,
            allow_partial=args.allow_partial,
            allow_single_slots=_parse_single_slots(args.allow_single_slots),
        )
    except (
        Exception
    ) as error:  # convert malformed inputs into a stable nonzero CLI result
        report = {
            "verdict": "FAIL",
            "errors": [f"Validator exception: {error}"],
            "warnings": [],
        }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
