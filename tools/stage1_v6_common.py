"""Shared deterministic contracts for Stage-1 POI v6 tooling.

This module validates and serializes authored data. It must never generate
``query_text`` or make semantic relevance decisions for an author.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA_COLUMNS = (
    "case_id",
    "variant_id",
    "query_text",
    "canonical_query",
    "query_variant_family",
    "variant_operator",
    "variant_subtype",
    "severity",
    "query_types",
    "intended_poi_id",
    "acceptable_poi_ids",
    "primary_sampling_stratum",
    "review_status",
    "generator_version",
    "n_acceptable",
    "is_multipositive",
)

STRING_COLUMNS = tuple(
    column
    for column in SCHEMA_COLUMNS
    if column not in {"acceptable_poi_ids", "n_acceptable", "is_multipositive"}
)

GENERATOR_VERSION = "manual_authored_v6"
PHYSICAL_SCHEMA_VERSION = "1.2"
CONTRACT_VERSION = "v6_coverage_pool_1"
OPERATOR_TAXONOMY_VERSION = "v6_coverage_pool_1"

ERROR_TAGS = frozenset(
    {
        "partial_diacritic_drop",
        "full_diacritic_strip",
        "mechanical_typo",
        "phonetic_confusion",
        "space_punct_variant",
        "slash_address_spoken",
        "ime_telex_residual",
        "raw_ime_sequence",
        "orthographic_equivalent",
        "token_boundary_error",
        "token_order_variant",
        "verified_name_fragment",
        "full_address_paste",
        "acronym_case",
        "acronym_expand_contract",
        "administrative_abbrev",
        "regional_abbrev",
        "verified_descriptor_variant",
        "safe_omission",
    }
)

# Accent normalization is useful coverage but does not count toward hard-noise
# difficulty. Every v03-v06 row needs at least two distinct tags from this set.
DEFORMING_ERROR_TAGS = frozenset(
    {
        "full_diacritic_strip",
        "mechanical_typo",
        "phonetic_confusion",
        "space_punct_variant",
        "slash_address_spoken",
        "ime_telex_residual",
        "raw_ime_sequence",
        "orthographic_equivalent",
        "token_boundary_error",
        "token_order_variant",
        "verified_name_fragment",
        "full_address_paste",
        "acronym_expand_contract",
        "verified_descriptor_variant",
        "safe_omission",
    }
)

COMPOUND_PAIRS = frozenset(
    {
        frozenset(("mechanical_typo", "full_diacritic_strip")),
        frozenset(("mechanical_typo", "partial_diacritic_drop")),
        frozenset(("administrative_abbrev", "full_diacritic_strip")),
        frozenset(("regional_abbrev", "full_diacritic_strip")),
        frozenset(("acronym_expand_contract", "mechanical_typo")),
        frozenset(("space_punct_variant", "mechanical_typo")),
        frozenset(("space_punct_variant", "full_diacritic_strip")),
        frozenset(("phonetic_confusion", "partial_diacritic_drop")),
        frozenset(("administrative_abbrev", "partial_diacritic_drop")),
        frozenset(("verified_descriptor_variant", "mechanical_typo")),
        frozenset(("verified_descriptor_variant", "phonetic_confusion")),
        frozenset(("verified_descriptor_variant", "regional_abbrev")),
        frozenset(("safe_omission", "mechanical_typo")),
        frozenset(("acronym_case", "mechanical_typo")),
        frozenset(("acronym_expand_contract", "regional_abbrev")),
        frozenset(("slash_address_spoken", "partial_diacritic_drop")),
        frozenset(("slash_address_spoken", "full_diacritic_strip")),
        frozenset(("slash_address_spoken", "mechanical_typo")),
        frozenset(("slash_address_spoken", "regional_abbrev")),
        frozenset(("ime_telex_residual", "partial_diacritic_drop")),
        frozenset(("ime_telex_residual", "mechanical_typo")),
        frozenset(("raw_ime_sequence", "mechanical_typo")),
        frozenset(("orthographic_equivalent", "mechanical_typo")),
        frozenset(("token_boundary_error", "mechanical_typo")),
        frozenset(("verified_name_fragment", "mechanical_typo")),
        frozenset(("full_address_paste", "mechanical_typo")),
        frozenset(("token_order_variant", "full_diacritic_strip")),
        frozenset(("token_order_variant", "partial_diacritic_drop")),
        frozenset(("token_order_variant", "mechanical_typo")),
        frozenset(("token_order_variant", "ime_telex_residual")),
        frozenset(("safe_omission", "full_diacritic_strip")),
        frozenset(("safe_omission", "partial_diacritic_drop")),
        frozenset(("mechanical_typo", "phonetic_confusion")),
        frozenset(("phonetic_confusion", "ime_telex_residual")),
        frozenset(("phonetic_confusion", "token_order_variant")),
        frozenset(("phonetic_confusion", "safe_omission")),
        frozenset(("phonetic_confusion", "space_punct_variant")),
        frozenset(("ime_telex_residual", "safe_omission")),
        frozenset(("ime_telex_residual", "space_punct_variant")),
        frozenset(("ime_telex_residual", "token_boundary_error")),
        frozenset(("raw_ime_sequence", "token_boundary_error")),
        frozenset(("raw_ime_sequence", "verified_name_fragment")),
        frozenset(("raw_ime_sequence", "safe_omission")),
        frozenset(("orthographic_equivalent", "token_boundary_error")),
        frozenset(("orthographic_equivalent", "safe_omission")),
        frozenset(("token_boundary_error", "full_diacritic_strip")),
        frozenset(("token_boundary_error", "partial_diacritic_drop")),
        frozenset(("token_boundary_error", "phonetic_confusion")),
        frozenset(("token_boundary_error", "token_order_variant")),
        frozenset(("token_boundary_error", "verified_name_fragment")),
        frozenset(("token_boundary_error", "safe_omission")),
        frozenset(("verified_name_fragment", "full_diacritic_strip")),
        frozenset(("verified_name_fragment", "partial_diacritic_drop")),
        frozenset(("verified_name_fragment", "phonetic_confusion")),
        frozenset(("full_address_paste", "full_diacritic_strip")),
        frozenset(("full_address_paste", "partial_diacritic_drop")),
        frozenset(("full_address_paste", "administrative_abbrev")),
        frozenset(("safe_omission", "token_order_variant")),
        frozenset(("safe_omission", "space_punct_variant")),
        frozenset(("space_punct_variant", "token_order_variant")),
    }
)

SLOT_SPECS: dict[str, dict[str, str]] = {
    "v01": {
        "family": "CLEAN",
        "operator": "canonical",
        "subtype": "canonical_anchor",
        "severity": "CLEAN",
        "slot_tag": "canonical_anchor",
    },
    "v02": {
        "family": "ALIAS",
        "operator": "short_name",
        "subtype": "standalone_or_natural_address",
        "severity": "CLEAN",
        "slot_tag": "standalone_name|natural_address",
    },
    "v03": {
        "family": "COMPOUND",
        "operator": "controlled_compound",
        "severity": "COMPOUND",
        "slot_tag": "controlled_compound",
    },
    "v04": {
        "family": "COMPOUND",
        "operator": "controlled_compound",
        "severity": "COMPOUND",
        "slot_tag": "controlled_compound",
    },
    "v05": {
        "family": "COMPOUND",
        "operator": "controlled_compound",
        "severity": "COMPOUND",
        "slot_tag": "controlled_compound",
    },
    "v06": {
        "family": "COMPOUND",
        "operator": "controlled_compound",
        "severity": "COMPOUND",
        "slot_tag": "controlled_compound",
    },
}

TRACE_COLUMNS = (
    "variant_id",
    "parent_variant_id",
    "error_tags",
    "affected_spans",
    "before_text",
    "after_text",
    "reviewer_status",
)


def normalize_query(value: Any) -> str:
    """Return the frozen v6 QA key, not an encoder transformation."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.casefold().split())


def strip_diacritics(value: Any) -> str:
    """Strip Vietnamese diacritics while preserving token order and punctuation."""

    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if not unicodedata.combining(char))
    )


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"Invalid boolean: {value!r}")


def parse_acceptable(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "as_py"):
        value = value.as_py()
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        parsed: Any
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError) as error:
                raise ValueError(f"Invalid acceptable_poi_ids: {value!r}") from error
        if not isinstance(parsed, (list, tuple, set)):
            raise ValueError("acceptable_poi_ids must be a list")
        items = list(parsed)
    else:
        raise ValueError(f"Invalid acceptable_poi_ids type: {type(value).__name__}")
    return [str(item).strip() for item in items if str(item).strip()]


def canonical_csv_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def canonical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in STRING_COLUMNS:
        value = row.get(column)
        result[column] = "" if value is None else str(value)
    result["acceptable_poi_ids"] = parse_acceptable(row.get("acceptable_poi_ids"))
    try:
        result["n_acceptable"] = int(row.get("n_acceptable"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid n_acceptable for {row.get('variant_id')!r}"
        ) from error
    result["is_multipositive"] = parse_bool(row.get("is_multipositive"))
    return {column: result[column] for column in SCHEMA_COLUMNS}


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = [canonical_row(row) for row in reader]
    return columns, rows


def read_parquet_rows(path: Path) -> tuple[Any, list[dict[str, Any]]]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = [canonical_row(row) for row in table.to_pylist()]
    return table.schema, rows


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSONL {path}:{line_number}: {error}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(f"JSONL record is not an object: {path}:{line_number}")
            records.append(record)
    return records


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    lines = [
        json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        for record in records
    ]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def parse_variant_slot(variant_id: str) -> str | None:
    match = re.search(r"-(v0[1-6])$", variant_id)
    return match.group(1) if match else None


def parse_subtype_tags(subtype: str) -> list[str]:
    return [part.strip() for part in subtype.split("+") if part.strip()]


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    return value
