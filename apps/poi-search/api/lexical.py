"""Elasticsearch lexical query builder (policy-driven)."""
from __future__ import annotations

from typing import Any

from settings import LEXICAL_CONFIG
from textnorm import (
    expand_query,
    fold,
    glue_code_spans,
    letter_runs,
    normalized_text,
    parse_query_structure,
    query_code_compacts,
    query_fuzzy_terms,
    query_name_compacts,
    text_tokens,
    _token_kind,
)


def lexical_text_and_numbers(analyzed: str) -> tuple[str, list[str]]:
    """BM25 text, plus pure-number tokens that must not enter IDF.

    When the query has both a letter span and a pure number, BM25 sees only
    the letters. The number is scored later as a bounded bonus. Queries with
    no letter span, or no pure number, keep the full analyzed string.
    """
    tokens = text_tokens(analyzed)
    letters = [token for token in tokens if _token_kind(token) == "letter"]
    numbers = [token for token in tokens if _token_kind(token) == "number"]
    if letters and numbers:
        return " ".join(letters), numbers
    return analyzed, []


def number_bonus_clause(token: str, boost: float) -> dict[str, Any]:
    """Flat score for one pure-number token. The boost is the whole score."""
    fields = ("search_label", "search_aliases", "address", "context_text")
    return {
        "constant_score": {
            "filter": {
                "bool": {
                    "should": [
                        {"match_phrase": {field: {"query": token}}} for field in fields
                    ],
                    "minimum_should_match": 1,
                }
            },
            "boost": boost,
        }
    }


def letter_span_phrases(
    analyzed: str,
    lex: dict[str, Any],
    *,
    include_label: bool = True,
) -> list[dict[str, Any]]:
    """Phrase each letter run of length >= 2 when a pure number is also present."""
    tokens = text_tokens(analyzed)
    if not any(_token_kind(token) == "number" for token in tokens):
        return []
    clauses: list[dict[str, Any]] = []
    phrase_boost = lex["phrase"]
    address_boost = lex.get("phrase_address", 6.0)
    street_boost = float(lex.get("phrase_street", 8.0))
    for run in letter_runs(tokens):
        if len(run) < 2:
            continue
        phrase = " ".join(run)
        if include_label:
            clauses.append(
                {
                    "match_phrase": {
                        "search_label": {"query": phrase, "slop": 1, "boost": phrase_boost}
                    }
                }
            )
        clauses.append(
            {
                "match_phrase": {
                    "address": {"query": phrase, "slop": 2, "boost": address_boost}
                }
            }
        )
        clauses.append(
            {"match_phrase": {"street": {"query": phrase, "slop": 1, "boost": street_boost}}}
        )
        clauses.append(
            {
                "match_phrase": {
                    "place": {"query": phrase, "slop": 1, "boost": street_boost * 0.7}
                }
            }
        )
    return clauses


def house_path_clauses(path_keys: tuple[str, ...], lex: dict[str, Any]) -> list[dict[str, Any]]:
    """Exact catalog house/alley keys. Slash and '259 ngõ 15' share path '259 15'."""
    clauses: list[dict[str, Any]] = []
    path_boost = float(lex.get("housenumber_path", 20.0))
    exact_boost = float(lex.get("housenumber_exact", 16.0))
    seen: set[str] = set()
    for key in path_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        clauses.append(
            {
                "constant_score": {
                    "filter": {"term": {"housenumber_path_key": key}},
                    "boost": path_boost,
                }
            }
        )
        slash = key.replace(" ", "/")
        if slash != key:
            clauses.append(
                {
                    "constant_score": {
                        "filter": {"term": {"housenumber": slash}},
                        "boost": exact_boost,
                    }
                }
            )
        else:
            clauses.append(
                {
                    "constant_score": {
                        "filter": {"term": {"housenumber": key}},
                        "boost": exact_boost,
                    }
                }
            )
    return clauses


def street_span_clauses(named_letters: tuple[str, ...], lex: dict[str, Any]) -> list[dict[str, Any]]:
    if len(named_letters) < 2:
        return []
    phrase = " ".join(named_letters)
    boost = float(lex.get("phrase_street", 8.0))
    return [
        {"match_phrase": {"street": {"query": phrase, "slop": 1, "boost": boost}}},
        {"match_phrase": {"place": {"query": phrase, "slop": 1, "boost": boost * 0.7}}},
        {"term": {"street_folded": {"value": phrase, "boost": boost * 1.25}}},
        {"term": {"place_folded": {"value": phrase, "boost": boost}}},
    ]


def _bm25_view(query: str, analyzed: str, structure) -> tuple[str, list[str], bool]:
    """Letters-only BM25 when a house path is in play; keep digits inside names.

    Medial numbers ('duong 3 thang 2') stay in BM25 and do not get number_bonus.
    House-path numbers stay out of BM25 and use structured fields instead.
    """
    if structure.has_house_street:
        text = " ".join(structure.named_letters)
        _, numbers = lexical_text_and_numbers(analyzed)
        return text, numbers, True
    if structure.leading_path:
        text, numbers = lexical_text_and_numbers(analyzed)
        return text, numbers, True
    if structure.has_medial_number:
        return analyzed, [], False
    text, numbers = lexical_text_and_numbers(analyzed)
    return text, numbers, False


def lexical_body(query: str, size: int) -> dict[str, Any]:
    """Fielded ES lexical: exact + phrase + structured house/street + cross/best OR.

    A leading house/alley path uses catalog housenumber fields so a POI whose
    *name* is a different number on the same street cannot outrank the exact
    member. Letter-leading codes stay on codes_compact. MSM=1; fuzzy off.
    """
    folded = fold(query)
    analyzed = glue_code_spans(query)
    structure = parse_query_structure(query)
    text_query, number_tokens, drop_name_prefix = _bm25_view(query, analyzed, structure)
    lex = LEXICAL_CONFIG
    include_label_spans = not structure.has_house_street
    should: list[dict[str, Any]] = [
        {"term": {"label_folded": {"value": folded, "boost": lex["exact"]}}},
        {"term": {"aliases_folded": {"value": folded, "boost": lex["alias_exact"]}}},
        {"match_phrase": {"search_label": {"query": analyzed, "slop": 1, "boost": lex["phrase"]}}},
        {
            "match_phrase": {
                "address": {"query": analyzed, "slop": 2, "boost": lex.get("phrase_address", 6.0)}
            }
        },
        {
            "multi_match": {
                "query": text_query,
                "fields": [
                    "search_label^8" if include_label_spans else "search_label^3",
                    "search_aliases^5",
                    "address^6",
                    "street^7",
                    "place^4",
                    "context_text^3",
                ],
                "type": "cross_fields",
                "operator": "or",
                "minimum_should_match": "50%",
                "boost": lex.get("cross_or", 5.0),
            }
        },
        {
            "multi_match": {
                "query": text_query,
                "fields": ["search_label^4", "address^3", "street^4", "context_text^2"],
                "type": "best_fields",
                "operator": "or",
                "boost": lex.get("best_or", 2.0),
            }
        },
    ]
    if not drop_name_prefix:
        should.append(
            {
                "multi_match": {
                    "query": text_query,
                    "fields": ["search_label.prefix^5", "search_aliases.prefix^3"],
                    "type": "best_fields",
                    "operator": "or",
                    "boost": lex["prefix_field"],
                }
            }
        )
    should.extend(
        letter_span_phrases(analyzed, lex, include_label=include_label_spans)
    )
    should.extend(house_path_clauses(structure.path_keys, lex))
    should.extend(street_span_clauses(structure.named_letters, lex))
    number_boost = float(lex.get("number_bonus", 1.5))
    seen_numbers: set[str] = set()
    if number_boost > 0:
        for token in number_tokens:
            if token in seen_numbers:
                continue
            seen_numbers.add(token)
            should.append(number_bonus_clause(token, number_boost))
    code_keys = query_code_compacts(query)
    if code_keys:
        code_boost = float(lex.get("code_compact", 14.0))
        should.append({"terms": {"codes_compact": code_keys, "boost": code_boost}})
        # Prefix on compact codes: s20 → s202 (generic keyword prefix, not a fixed pattern).
        for key in code_keys:
            if len(key) >= 3:
                should.append(
                    {"prefix": {"codes_compact": {"value": key, "boost": code_boost * 0.7}}}
                )
    name_keys = query_name_compacts(query)
    if name_keys:
        name_boost = float(lex.get("name_compact", 24.0))
        should.append(
            {
                "constant_score": {
                    "filter": {"terms": {"names_compact": name_keys}},
                    "boost": name_boost,
                }
            }
        )
    if len(folded) >= 2 and not drop_name_prefix:
        should += [
            {"prefix": {"label_folded": {"value": folded, "boost": lex["leading_prefix"]}}},
            {
                "prefix": {
                    "aliases_folded": {
                        "value": folded,
                        "boost": lex["leading_prefix"] * 0.8,
                    }
                }
            },
        ]
    expanded = expand_query(query)
    if normalized_text(expanded) != normalized_text(query):
        expanded_analyzed = glue_code_spans(expanded)
        expanded_structure = parse_query_structure(expanded)
        expanded_text, expanded_numbers, _ = _bm25_view(
            expanded, expanded_analyzed, expanded_structure
        )
        should.append(
            {
                "multi_match": {
                    "query": expanded_text,
                    "fields": ["search_label^6", "address^4", "street^5", "context_text^2"],
                    "type": "cross_fields",
                    "operator": "or",
                    "boost": 2.0,
                }
            }
        )
        should.extend(house_path_clauses(expanded_structure.path_keys, lex))
        if expanded_numbers:
            # Full rewritten phrase still requires the number, so an exact
            # expanded name keeps its phrase hit. BM25 above uses letters only.
            should.append(
                {
                    "match_phrase": {
                        "search_label": {
                            "query": expanded_analyzed,
                            "slop": 1,
                            "boost": lex["phrase"],
                        }
                    }
                }
            )
            should.append(
                {
                    "match_phrase": {
                        "address": {
                            "query": expanded_analyzed,
                            "slop": 2,
                            "boost": lex.get("phrase_address", 6.0),
                        }
                    }
                }
            )
            should.extend(
                letter_span_phrases(
                    expanded_analyzed, lex, include_label=not expanded_structure.has_house_street
                )
            )
            if number_boost > 0:
                for token in expanded_numbers:
                    if token in seen_numbers:
                        continue
                    seen_numbers.add(token)
                    should.append(number_bonus_clause(token, number_boost))
    fuzzy_boost = float(lex.get("fuzzy") or 0.0)
    if fuzzy_boost > 0:
        fuzzy_terms = query_fuzzy_terms(query)
        if fuzzy_terms:
            should.append(
                {
                    "multi_match": {
                        "query": " ".join(fuzzy_terms),
                        "fields": ["search_label^4", "search_aliases^3"],
                        "type": "best_fields",
                        "operator": "or",
                        "fuzziness": 1,
                        "prefix_length": 1,
                        "max_expansions": 40,
                        "boost": fuzzy_boost,
                    }
                }
            )
    # Always 1: requiring ≥2 should-clauses zeroed recall on multi-token gold queries.
    minimum_should_match = int(lex.get("minimum_should_match", 1))
    return {
        "size": size,
        "track_total_hits": False,
        "_source": False,
        "sort": [{"_score": {"order": "desc"}}, {"canonical_id": {"order": "asc"}}],
        "query": {
            "bool": {
                "filter": [{"term": {"destination_searchable": True}}],
                "should": should,
                "minimum_should_match": minimum_should_match,
            }
        },
    }
