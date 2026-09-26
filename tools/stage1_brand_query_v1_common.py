"""Shared contracts for manually authored Stage-1 brand queries v1."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any


GENERATOR_VERSION = "manual_brand_authored_v1"
QRELS_VERSION = "brand_qrels_v1"

QUERY_COLUMNS = (
    "query_id",
    "query_text",
    "canonical_brand_query",
    "brand_family_id",
    "namespace_scope",
    "intent_scope",
    "intent_id",
    "qrel_policy",
    "query_variant_family",
    "variant_operator",
    "severity",
    "language_tag",
    "review_status",
    "generator_version",
)

QREL_COLUMNS = (
    "query_id",
    "poi_id",
    "relation",
    "label_reason",
    "brand_group_id",
    "qrels_version",
)

OPERATOR_SPECS = {
    "brand_canonical": ("BRAND_CANONICAL", "CLEAN"),
    "brand_namespace_form": ("BRAND_NAMESPACE", "CLEAN"),
    "brand_alias": ("BRAND_ALIAS", "CLEAN"),
    "brand_case_punct": ("BRAND_CASE_PUNCT", "SINGLE"),
    "brand_mechanical_typo": ("BRAND_MECHANICAL_TYPO", "SINGLE"),
    "brand_space_variant": ("BRAND_SPACE_VARIANT", "SINGLE"),
    "brand_orthographic_ime": ("BRAND_ORTHOGRAPHIC_IME", "SINGLE"),
    "brand_phonetic": ("BRAND_PHONETIC", "SINGLE"),
}

NAMESPACE_TOKENS = {
    "atm": ("atm",),
    "bank": ("ngân hàng", "ngan hang", "bank"),
    "fuel": ("cây xăng", "cay xang", "trạm xăng", "tram xang", "xăng dầu", "xang dau"),
    "cafe": ("cà phê", "ca phe", "cafe", "coffee"),
    "restaurant": ("nhà hàng", "nha hang", "restaurant"),
    "convenience_store": ("cửa hàng tiện lợi", "cua hang tien loi"),
    "supermarket": ("siêu thị", "sieu thi", "supermarket"),
    "pharmacy": ("nhà thuốc", "nha thuoc", "pharmacy"),
    "hotel": ("khách sạn", "khach san", "hotel"),
    "retail": ("cửa hàng", "cua hang", "shop", "store"),
}


def normalize_query(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.casefold().split())


def strip_diacritics(value: Any) -> str:
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if not unicodedata.combining(char))
    )


def compact_alnum(value: Any) -> str:
    return "".join(char for char in normalize_query(value) if char.isalnum() or char == "+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not an object")
            rows.append(value)
    return rows
