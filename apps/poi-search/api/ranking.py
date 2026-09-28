"""Stage-2 ranking, fusion, candidate policy, and nearby-name rescue merge."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from geo import haversine
from settings import BRANCH_DEPTH, POLICY, RANKING_POLICY, RRF_CONSTANT
from textnorm import (
    fold,
    is_house_atom,
    letter_compact,
    letter_runs,
    normalized_text,
    parse_query_structure,
    path_atoms,
    query_has_accents,
    text_tokens,
    _accented_tokens,
    _token_kind,
)

def is_exact_text_match(query: str, document: dict[str, Any]) -> bool:
    names = [document.get("search_label", ""), *(document.get("search_aliases") or [])]
    return bool(normalized_text(query)) and any(normalized_text(query) == normalized_text(name) for name in names)


def token_overlap(query: str, document: dict[str, Any]) -> float:
    tokens = text_tokens(query)
    fields = [document.get("search_label", ""), *(document.get("search_aliases") or []),
              document.get("address", "")]
    available = set(text_tokens(" ".join(fields)))
    if not tokens:
        return 0.0
    matched = 0.0
    for index, token in enumerate(tokens):
        if token in available:
            matched += 1.0
        elif index == len(tokens) - 1 and len(token) >= 3 and token.isalpha():
            # Only unfinished final text can prefix-match. B12 must never match B1.
            matched += 0.5 if any(t.startswith(token) for t in available) else 0.0
    return matched / len(tokens)


def _token_in_set(token: str, available: set[str], *, allow_prefix: bool) -> bool:
    if token in available:
        return True
    if allow_prefix and token.isalpha() and len(token) >= 3:
        return any(item.startswith(token) for item in available)
    return False


def _contiguous_span_in_field(
    span: list[str],
    field_tokens: list[str],
    *,
    allow_final_prefix: bool,
) -> bool:
    """True if `span` appears as an adjacent subsequence of `field_tokens`."""
    if not span or not field_tokens or len(span) > len(field_tokens):
        return False
    last = len(span) - 1
    for start in range(len(field_tokens) - len(span) + 1):
        ok = True
        for offset, token in enumerate(span):
            field = field_tokens[start + offset]
            if token == field:
                continue
            if (
                allow_final_prefix
                and offset == last
                and token.isalpha()
                and len(token) >= 2
                and field.startswith(token)
            ):
                continue
            ok = False
            break
        if ok:
            return True
    return False


def mixed_text_number_signals(query: str, document: dict[str, Any]) -> tuple[int, float, float]:
    """Letter-span length, letter coverage, number coverage.

    All three stay 0 unless the query has both a letter run and a pure number,
    so letter-only ranking is unchanged. A longer contiguous letter run outranks
    a number hit. The number only breaks ties inside the same letter span.
    House/alley paths compare catalog atoms ('259/15' ≡ '259 ngõ 15'), not raw
    slash tokens, and glue letters are not required on the name.
    """
    tokens = text_tokens(query)
    letters = [token for token in tokens if _token_kind(token) == "letter"]
    numbers = [token for token in tokens if _token_kind(token) == "number"]
    structure = parse_query_structure(query)
    if structure.has_house_street or structure.leading_path:
        letters = list(structure.named_letters) or letters
        path = []
        for part in (structure.leading_path, *structure.inner_paths):
            path.extend(part)
        numbers = [atom for atom in path if any(ch.isdigit() for ch in atom)] or numbers
    if not letters or not numbers:
        return 0, 0.0, 0.0

    name_tokens = text_tokens(
        " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
    )
    addr_tokens = text_tokens(document.get("address", "") or "")
    best = 0
    for run in letter_runs(tokens if not structure.named_letters else list(structure.named_letters)):
        for length in range(len(run), 0, -1):
            found = False
            for start in range(len(run) - length + 1):
                span = run[start : start + length]
                allow_prefix = span[-1] == (letters[-1] if letters else "")
                if _contiguous_span_in_field(
                    span, name_tokens, allow_final_prefix=allow_prefix
                ) or _contiguous_span_in_field(
                    span, addr_tokens, allow_final_prefix=allow_prefix
                ):
                    best = max(best, length)
                    found = True
                    break
            if found:
                break

    available = set(name_tokens) | set(addr_tokens)
    letter_hits = 0.0
    for index, token in enumerate(letters):
        allow_prefix = index == len(letters) - 1
        if _token_in_set(token, available, allow_prefix=allow_prefix):
            letter_hits += 1.0
    doc_house = {atom for atom in path_atoms(document.get("housenumber") or "") if is_house_atom(atom)}
    if not doc_house:
        doc_house = {atom for atom in path_atoms(document.get("address", "") or "") if is_house_atom(atom)}
    number_hits = 0.0
    for token in numbers:
        atoms = [atom for atom in (path_atoms(token) or [token]) if any(ch.isdigit() for ch in atom)]
        if atoms and all(atom in doc_house or atom in available for atom in atoms):
            number_hits += 1.0
        elif token in available:
            number_hits += 1.0
    return best, letter_hits / len(letters), number_hits / len(numbers)


def name_address_evidence(query: str, document: dict[str, Any]) -> float:
    """Brand∩street evidence via name hits + contiguous address phrase.

    Address side must match a contiguous query span (≥2 tokens) that is not
    already a contiguous span on the name/alias side. No admin stopword list —
    single-token overlaps like «thành» in «Thành phố» cannot satisfy a span.
    """
    tokens = text_tokens(query)
    min_tokens = max(2, int(RANKING_POLICY.get("name_address_min_query_tokens", 4)))
    if len(tokens) < min_tokens:
        return 0.0
    if name_match_class(query, document) is not None:
        return 0.0

    name_tokens = text_tokens(
        " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
    )
    addr_tokens = text_tokens(document.get("address", "") or "")
    if not name_tokens or not addr_tokens:
        return 0.0

    name_set = set(name_tokens)
    name_hit_idxs = [
        index
        for index, token in enumerate(tokens)
        if _token_in_set(token, name_set, allow_prefix=(index == len(tokens) - 1))
    ]
    if not name_hit_idxs:
        return 0.0

    min_span = max(2, int(RANKING_POLICY.get("name_address_min_addr_span", 2)))
    name_hit_set = set(name_hit_idxs)
    best_span = 0
    best_start = -1
    for length in range(len(tokens), min_span - 1, -1):
        for start in range(len(tokens) - length + 1):
            span = tokens[start : start + length]
            allow_prefix = start + length == len(tokens)
            if not _contiguous_span_in_field(span, addr_tokens, allow_final_prefix=allow_prefix):
                continue
            # Span already explained as a name phrase → not address-side evidence.
            if _contiguous_span_in_field(span, name_tokens, allow_final_prefix=False):
                continue
            # Need a real residual street phrase: ≥min_span query tokens in the
            # span that the name side did not already cover (avoids «Phố»+«Bồ Đề»
            # matching brand query «pho bo …» without the extra street tokens).
            residual = sum(
                1 for index in range(start, start + length) if index not in name_hit_set
            )
            if residual < min_span:
                continue
            best_span = length
            best_start = start
            break
        if best_span:
            break
    if best_span < min_span:
        return 0.0

    covered = set(name_hit_idxs) | set(range(best_start, best_start + best_span))
    return len(covered) / len(tokens)


def prioritize_name_address(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
) -> list[tuple[float, int, float | None, dict]]:
    """Promote candidates with name∩address evidence above partial one-field hits."""
    if not ranked or not bool(RANKING_POLICY.get("name_address_priority", True)):
        return ranked
    min_tokens = max(2, int(RANKING_POLICY.get("name_address_min_query_tokens", 4)))
    if len(text_tokens(query)) < min_tokens:
        return ranked
    threshold = min(1.0, max(0.0, float(RANKING_POLICY.get("name_address_min_evidence", 0.5))))
    decorated = []
    for score, rank, distance, doc in ranked:
        evidence = name_address_evidence(query, doc)
        decorated.append((1 if evidence >= threshold else 0, evidence, score, rank, distance, doc))
    decorated.sort(
        key=lambda row: (-row[0], -row[1], -row[2], row[3], row[5]["canonical_id"])
    )
    return [(score, rank, distance, doc) for _, _, score, rank, distance, doc in decorated]


def accent_token_coverage(query: str, document: dict[str, Any]) -> float:
    """Share of accent-preserving query tokens found in name/alias (not folded)."""
    tokens = _accented_tokens(query)
    if not tokens or not query_has_accents(query):
        return 0.0
    available = set(
        _accented_tokens(
            " ".join([document.get("search_label", ""), *(document.get("search_aliases") or [])])
        )
    )
    if not available:
        return 0.0
    matched = 0.0
    for index, token in enumerate(tokens):
        if token in available:
            matched += 1.0
        elif index == len(tokens) - 1 and len(token) >= 2 and token.isalpha():
            matched += 0.5 if any(item.startswith(token) for item in available) else 0.0
    return matched / len(tokens)


def prioritize_name_match_quality(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
) -> list[tuple[float, int, float | None, dict]]:
    """Prefer contiguous name/alias phrase coverage over weak single-token fold hits.

    When the query mixes a letter run with a pure number, the letter span is the
    next key after name class. The number only orders hits that share that span.
    When phrase/coverage tiers tie, keep prior geo/retrieval order.
    """
    if not ranked or not bool(RANKING_POLICY.get("name_match_quality_priority", True)):
        return ranked
    # Backward-compatible alias for the older accent-only flag.
    if RANKING_POLICY.get("accent_match_priority") is False and (
        RANKING_POLICY.get("name_match_quality_priority") is None
    ):
        return ranked
    accented = query_has_accents(query)
    decorated = []
    for position, (score, rank, distance, doc) in enumerate(ranked):
        match = name_match_class(query, doc)
        level = int(match[0]) if match else 0
        accent_hit = int(match[1]) if match and accented else 0
        coverage = token_overlap(query, doc)
        if accented:
            coverage = max(coverage, accent_token_coverage(query, doc))
        span, letter_cov, number_cov = mixed_text_number_signals(query, doc)
        # `position` keeps post-geo order when phrase quality ties.
        decorated.append(
            (level, accent_hit, span, letter_cov, number_cov, coverage, position, score, rank, distance, doc)
        )
    decorated.sort(
        key=lambda row: (
            -row[0], -row[1], -row[2], -row[3], -row[4], -row[5], row[6], -row[7], row[10]["canonical_id"]
        )
    )
    return [
        (score, rank, distance, doc)
        for _, _, _, _, _, _, _, score, rank, distance, doc in decorated
    ]


def entity_key(document: dict[str, Any]) -> tuple[str, ...]:
    canonical = str(document["canonical_id"])
    category = str(document.get("category", ""))
    access_point = document.get("preserve_individual_access_point") or any(
        marker in category for marker in ("public_transport=platform", "railway=platform", "entrance=")
    )
    group = document.get("entity_group_id")
    if access_point or not group or not RANKING_POLICY.get("deduplication", {}).get("entity_group_id", True):
        return ("poi", canonical)
    # Different branches/access points are not duplicates of the parent complex.
    return ("entity", str(group), str(document.get("branch_id") or ""))


def is_near_name_duplicate(kept: dict[str, Any], candidate: dict[str, Any], within_m: float) -> bool:
    """Same folded label within `within_m`; keeps distinct branch_id only.

    Access-point tags still collapse when the visible name matches and the points
    are near — OSM often duplicates platforms/nodes for one place.
    """
    if within_m <= 0:
        return False
    left_branch, right_branch = kept.get("branch_id"), candidate.get("branch_id")
    if (left_branch or right_branch) and left_branch != right_branch:
        return False
    if fold(kept.get("search_label", "")) != fold(candidate.get("search_label", "")):
        return False
    if not fold(kept.get("search_label", "")):
        return False
    left, right = kept.get("ranking_point"), candidate.get("ranking_point")
    if not left or not right:
        return False
    return haversine(left, right) <= within_m


def candidate_documents(ids: list[str], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from settings import RANKING_PROFILE
    return candidate_document_stages(ids, docs, dedup=RANKING_PROFILE != "raw", stop_at_budget=True)["after_cap"]


def candidate_document_stages(
    ids: list[str], docs: list[dict[str, Any]], *, budget: int | None = None, dedup: bool = True, stop_at_budget: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Stable retrieval order, entity + nearby same-name collapse, fixed Stage 1 budget."""
    by_id = {doc["canonical_id"]: doc for doc in docs}
    seen = set()
    output = []
    budget = int(POLICY["retrieval"]["candidate_budget"]) if budget is None else budget
    if budget < 1:
        raise ValueError("candidate budget must be positive")
    within_m = float(RANKING_POLICY.get("deduplication", {}).get("normalized_name_within_m") or 0)
    labels = {doc["canonical_id"]: fold(doc.get("search_label", "")) for doc in docs} if dedup else {}
    for poi_id in ids:
        doc = by_id.get(poi_id)
        if doc is None:
            continue
        key = entity_key(doc)
        if dedup and key in seen:
            continue
        if dedup and within_m > 0 and any(labels[kept["canonical_id"]] == labels[doc["canonical_id"]] and is_near_name_duplicate(kept, doc, within_m) for kept in output):
            continue
        seen.add(key)
        output.append(doc)
        if stop_at_budget and len(output) >= budget:
            break
    return {"after_dedup": output, "after_cap": output[:budget]}


def name_match_class(query: str, doc: dict[str, Any]) -> tuple[int, int] | None:
    """Conservative equivalence: contiguous name/alias phrase, not bag-of-words.

    A numeric/code token must match in full. Address-only and fuzzy matches do
    not establish enough equivalence to let distance override retrieval.
    """
    query_tokens = text_tokens(query)
    if not query_tokens:
        return None
    classes: list[tuple[int, int]] = []
    names = [doc.get("search_label", ""), *(doc.get("search_aliases") or [])]
    compact_query = letter_compact(query)
    if (
        len(compact_query) >= 6
        and not any(is_house_atom(atom) for atom in path_atoms(query))
    ):
        for name in names:
            if compact_query == letter_compact(name):
                classes.append((3, 0))
                break
    accented_query = normalized_text(query) != fold(query)
    for name in names:
        tokens = text_tokens(name)
        if len(tokens) < len(query_tokens):
            continue
        for start in range(len(tokens) - len(query_tokens) + 1):
            span = tokens[start : start + len(query_tokens)]
            if span[:-1] != query_tokens[:-1]:
                continue
            last = query_tokens[-1]
            complete = span[-1] == last
            prefix = last.isalpha() and len(last) >= 2 and span[-1].startswith(last)
            if not (complete or prefix):
                continue
            # Full name/alias > complete phrase > unfinished final token.
            level = 3 if tokens == query_tokens else 2 if complete else 1
            accent_tokens = re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(name))
            raw_query = re.findall(r"[^\W_]+(?:[/-][^\W_]+)*", normalized_text(query))
            raw_span = accent_tokens[start : start + len(raw_query)]
            accent_match = bool(
                raw_span
                and raw_span[:-1] == raw_query[:-1]
                and (
                    raw_span[-1] == raw_query[-1]
                    if complete
                    else raw_span[-1].startswith(raw_query[-1])
                )
            )
            classes.append((level, int(accent_match) if accented_query else 0))
    return max(classes) if classes else None


def rank_candidates_v5(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Personalized blend: relevance_blend * text_rel + geo_blend * exp(-d/decay)."""
    best = max((float(evidence[d["canonical_id"]]["rrf"] or 0) for d in docs), default=1.0) or 1.0
    retrieval_w = float(RANKING_POLICY.get("retrieval_weight", 0.65))
    overlap_w = float(RANKING_POLICY.get("name_token_overlap_weight", 0.35))
    relevance_blend = float(RANKING_POLICY.get("relevance_blend", 0.65))
    geo_blend = float(RANKING_POLICY.get("geo_blend", 0.35))
    decay = max(1.0, float(RANKING_POLICY.get("geo_decay_m", 5000)))
    exact_bonus = float(RANKING_POLICY.get("exact_text_bonus", 0.04))
    protect_exact = bool(RANKING_POLICY.get("protect_exact_name_or_alias", True))

    ranked: list[tuple[float, int, float | None, dict]] = []
    for rank, doc in enumerate(docs, 1):
        rrf_norm = float(evidence[doc["canonical_id"]]["rrf"] or 0) / best
        distance = haversine(anchor, doc["ranking_point"]) if anchor and doc.get("ranking_point") else None

        if anchor is None:
            ranked.append((rrf_norm, rank, distance, doc))
            continue

        coverage = token_overlap(query, doc)
        names = [doc.get("search_label", ""), *(doc.get("search_aliases") or [])]
        exact = is_exact_text_match(query, doc)
        folded_exact = bool(fold(query)) and any(fold(query) == fold(name) for name in names)
        text_rel = retrieval_w * rrf_norm + overlap_w * coverage
        if exact:
            text_rel += exact_bonus
        elif folded_exact:
            text_rel += 0.5 * exact_bonus
        if protect_exact and (exact or folded_exact):
            text_rel = max(text_rel, retrieval_w * rrf_norm + overlap_w)

        fields = " ".join([*names, doc.get("address", "")])
        available = set(text_tokens(fields))
        structured = [token for token in text_tokens(query) if any(c.isdigit() for c in token)]
        compatible = all(token in available for token in structured)
        geo = 0.0
        if distance is not None and compatible:
            geo = math.exp(-distance / decay)

        score = relevance_blend * text_rel + geo_blend * geo
        ranked.append((score, rank, distance, doc))
    return sorted(ranked, key=lambda item: (-item[0], item[1], item[3]["canonical_id"]))


def exponential_distance_points(distance_m: float | None) -> float:
    """Capped exponential decay. The cap stays below one match tier, so a nearer partial cannot pass an exact hit."""
    cap = min(0.99, max(0.0, float(RANKING_POLICY.get("geo_score_cap", RANKING_POLICY.get("geo_blend", 0.35)))))
    decay_m = max(1.0, float(RANKING_POLICY.get("geo_decay_m", 5000)))
    if distance_m is None:
        return 0.0
    return cap * math.exp(-max(0.0, float(distance_m)) / decay_m)


def rank_candidates_v6(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Reorder only the head's equivalent-name cohort by capped exp(-d/tau).

    A stricter name/code match is a different class and is not moved. The decay
    term is at most geo_score_cap < 1, so it cannot cross one match tier.
    Outside the cohort, order is unchanged. RRF itself is not rewritten.
    """
    best = max((float(evidence[d["canonical_id"]]["rrf"] or 0) for d in docs), default=1.0) or 1.0
    ranked: list[tuple[float, int, float | None, dict]] = []
    for rank, doc in enumerate(docs, 1):
        distance = haversine(anchor, doc["ranking_point"]) if anchor and doc.get("ranking_point") else None
        score = float(evidence[doc["canonical_id"]]["rrf"] or 0) / best
        ranked.append((score, rank, distance, doc))
    if anchor is None or not ranked or ranked[0][2] is None:
        return ranked
    head_class = name_match_class(query, ranked[0][3])
    if head_class is None:
        return ranked
    window = max(1, min(20, int(RANKING_POLICY.get("geo_equivalent_window", 10))))
    floor = min(1.0, max(0.0, float(RANKING_POLICY.get("geo_min_retrieval_ratio", 0.5))))
    slots = [
        i
        for i, row in enumerate(ranked[:window])
        if row[2] is not None and row[0] >= floor and name_match_class(query, row[3]) == head_class
    ]
    if len(slots) < 2:
        return ranked
    cohort = sorted(
        (ranked[i] for i in slots),
        key=lambda row: (-exponential_distance_points(row[2]), row[1]),
    )
    for slot, row in zip(slots, cohort):
        ranked[slot] = row
    return ranked


def rank_candidates(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
) -> list[tuple[float, int, float | None, dict]]:
    """Dispatch Stage-2 geo by policy `geo_mode` (`v5` blend | `v6` cohort swap)."""
    return rank_candidates_traced(query, docs, evidence, anchor)["final"]


def rank_candidates_traced(
    query: str,
    docs: list[dict[str, Any]],
    evidence: dict,
    anchor: dict | None,
    *, profile: str | None = None,
) -> dict[str, list[tuple[float, int, float | None, dict]]]:
    """Same as rank_candidates, but keep intermediate lists for freeze diagnostics."""
    from settings import RANKING_PROFILE
    profile = profile or RANKING_PROFILE
    if profile not in {"current", "raw", "dedup_only", "name_address", "name_quality"}:
        raise ValueError(f"Unknown ranking profile: {profile}")
    mode = str(RANKING_POLICY.get("geo_mode", "v6")).strip().lower()
    if profile != "current":
        after_geo = [(float(evidence[d["canonical_id"]]["rrf"] or 0), i, None, d) for i, d in enumerate(docs, 1)]
    elif mode == "v5":
        after_geo = rank_candidates_v5(query, docs, evidence, anchor)
    else:
        after_geo = rank_candidates_v6(query, docs, evidence, anchor)
    after_name_address = prioritize_name_address(query, after_geo) if profile in {"current", "name_address"} else after_geo
    after_name_match = prioritize_name_match_quality(query, after_name_address) if profile in {"current", "name_quality"} else after_name_address
    return {
        "after_geo": after_geo,
        "after_name_address": after_name_address,
        "final": after_name_match,
    }


def _history_cohort_key(query: str, doc: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Same name class, and the same address/code evidence, may be reordered by history."""
    match = name_match_class(query, doc)
    if match is None:
        return None
    codes = [token for token in text_tokens(query) if any(ch.isdigit() for ch in token)]
    fields = set(text_tokens(" ".join([
        doc.get("search_label", ""),
        doc.get("address", ""),
        " ".join(doc.get("search_aliases") or []),
    ])))
    code_hit = int(bool(codes) and all(token in fields for token in codes))
    address_hit = int(name_address_evidence(query, doc) > 0)
    return (int(match[0]), int(match[1]), address_hit, code_hit)


def apply_history_cohort(
    query: str,
    ranked: list[tuple[float, int, float | None, dict]],
    preferred_ids: list[str],
) -> list[tuple[float, int, float | None, dict]]:
    """Move history hits to the front of the head's equivalent-name window.

    Slots outside that name class, or with different address/code evidence, stay put.
    A preferred id that is not already in the window is not pulled in.
    """
    if not ranked or not preferred_ids:
        return ranked
    head_key = _history_cohort_key(query, ranked[0][3])
    if head_key is None:
        return ranked
    window = max(1, min(20, int(RANKING_POLICY.get("geo_equivalent_window", 10))))
    slots = [
        index
        for index, row in enumerate(ranked[:window])
        if _history_cohort_key(query, row[3]) == head_key
    ]
    if len(slots) < 2:
        return ranked
    preferred_rank = {poi_id: index for index, poi_id in enumerate(preferred_ids)}
    if not any(ranked[index][3]["canonical_id"] in preferred_rank for index in slots):
        return ranked
    cohort = [ranked[index] for index in slots]
    chosen = [row for row in cohort if row[3]["canonical_id"] in preferred_rank]
    chosen.sort(key=lambda row: preferred_rank[row[3]["canonical_id"]])
    rest = [row for row in cohort if row[3]["canonical_id"] not in preferred_rank]
    updated = list(ranked)
    for slot, row in zip(slots, chosen + rest):
        updated[slot] = row
    return updated


def rrf(left: list[str], right: list[str], *, depth: int | None = None) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    best: dict[str, int] = {}
    depth = BRANCH_DEPTH if depth is None else depth
    for branch in (left[:depth], right[:depth]):
        for rank, poi_id in enumerate(branch, 1):
            scores[poi_id] += 1 / (RRF_CONSTANT + rank)
            best[poi_id] = min(best.get(poi_id, rank), rank)
    return sorted(scores, key=lambda poi_id: (-scores[poi_id], best[poi_id], poi_id))


def _lexical_evidence(ids: list[str]) -> dict[str, dict[str, float | None]]:
    return {
        poi_id: {"lexical_rank": rank, "dense_rank": None, "rrf": 1 / (RRF_CONSTANT + rank)}
        for rank, poi_id in enumerate(ids, 1)
    }


def _dense_evidence(ids: list[str]) -> dict[str, dict[str, float | None]]:
    return {
        poi_id: {"lexical_rank": None, "dense_rank": rank, "rrf": 1 / (RRF_CONSTANT + rank)}
        for rank, poi_id in enumerate(ids, 1)
    }


def _hybrid_evidence(lexical_ids: list[str], dense_ids: list[str], *, depth: int | None = None) -> tuple[list[str], dict[str, dict[str, float | None]]]:
    depth = BRANCH_DEPTH if depth is None else depth
    lexical_ids, dense_ids = lexical_ids[:depth], dense_ids[:depth]
    ids = rrf(lexical_ids, dense_ids, depth=depth)
    lexical_ranks = {poi_id: rank for rank, poi_id in enumerate(lexical_ids, 1)}
    dense_ranks = {poi_id: rank for rank, poi_id in enumerate(dense_ids, 1)}
    evidence: dict[str, dict[str, float | None]] = {}
    for poi_id in ids:
        lexical_rank = lexical_ranks.get(poi_id)
        dense_rank = dense_ranks.get(poi_id)
        evidence[poi_id] = {
            "lexical_rank": lexical_rank,
            "dense_rank": dense_rank,
            "rrf": (1 / (RRF_CONSTANT + lexical_rank) if lexical_rank else 0)
            + (1 / (RRF_CONSTANT + dense_rank) if dense_rank else 0),
        }
    return ids, evidence


def nearby_name_rescue_body(
    query: str,
    anchor: dict[str, float],
    *,
    size: int,
    radius_m: float,
) -> dict[str, Any] | None:
    """BBox + folded label/alias match. ranking_point is lat/lon doubles, not geo_point."""
    folded = fold(query)
    if len(folded) < 2:
        return None
    lat, lon = float(anchor["lat"]), float(anchor["lon"])
    dlat = radius_m / 111_195.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = radius_m / (111_195.0 * cos_lat)
    return {
        "size": size,
        "track_total_hits": False,
        "_source": ["ranking_point", "search_label", "search_aliases"],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"destination_searchable": True}},
                    {"range": {"ranking_point.lat": {"gte": lat - dlat, "lte": lat + dlat}}},
                    {"range": {"ranking_point.lon": {"gte": lon - dlon, "lte": lon + dlon}}},
                ],
                "should": [
                    {"term": {"label_folded": folded}},
                    {"prefix": {"label_folded": folded}},
                    {"term": {"aliases_folded": folded}},
                    {"prefix": {"aliases_folded": folded}},
                ],
                "minimum_should_match": 1,
            }
        },
    }


def merge_nearby_name_rescue(
    query: str,
    ids: list[str],
    evidence: dict,
    rescued: list[str],
) -> tuple[list[str], dict, int]:
    """Prepend nearby same-name hits so geo-v6 window can see them. Query-only unused."""
    if not rescued:
        return ids, evidence, 0
    seen = set(ids)
    new_ids = [poi_id for poi_id in rescued if poi_id not in seen]
    if not new_ids:
        return ids, evidence, 0
    best = max((float(evidence[poi_id]["rrf"] or 0) for poi_id in ids if poi_id in evidence), default=0.0)
    base = max(best, 1.0 / (RRF_CONSTANT + 1))
    for index, poi_id in enumerate(new_ids):
        evidence[poi_id] = {
            "lexical_rank": None,
            "dense_rank": None,
            "rrf": base + (len(new_ids) - index) * 1e-6,
            "nearby_rescue": True,
        }
    return new_ids + ids, evidence, len(new_ids)


def classify_target_loss(target: str | None, stages: dict[str, list[str]], top_k: int = 5) -> str | None:
    """Map missing intended POI to the earliest pipeline stage that dropped it."""
    if not target:
        return None
    final = stages.get("final_top_k") or []
    if target in final[:top_k]:
        return None
    lexical = stages.get("lexical") or []
    dense = stages.get("dense") or []
    rrf_ids = stages.get("rrf") or []
    after_rescue = stages.get("after_nearby_rescue") or []
    after_dedup = stages.get("after_dedup_cap") or []
    after_geo = stages.get("after_geo") or []
    after_addr = stages.get("after_name_address") or []
    after_match = stages.get("after_name_match_quality") or []
    in_retrieval = target in lexical or target in dense or target in rrf_ids
    if not in_retrieval and target not in after_rescue:
        return "retrieval_miss"
    if target in after_rescue and target not in after_dedup:
        return "lost_at_dedup_or_cap"
    if target in after_dedup and target not in after_geo:
        return "lost_at_geo"
    if target in after_geo and target not in after_addr:
        return "lost_at_name_address"
    if target in after_addr and target not in after_match:
        return "lost_at_name_match_quality"
    if target in after_match and target not in final[:top_k]:
        return "lost_below_top_k"
    if target in after_match:
        return "lost_below_top_k"
    return "ranking_miss"


def _result_rows(
    ranked: list[tuple[float, int, float | None, dict]], top_k: int
) -> list[dict[str, Any]]:
    results = []
    for _, _, distance, doc in ranked[:top_k]:
        results.append({
            "poi_id": doc["canonical_id"], "name": doc["search_label"], "rank": len(results) + 1,
            "address_text": doc.get("address", ""), "context_text": doc.get("context_text", ""),
            "ranking_point": doc["ranking_point"], "routing_point": doc.get("routing_point"),
            "pickup_access_verified": doc.get("pickup_access_verified", False),
            "ranking_distance_m": round(distance) if distance is not None else None,
        })
    return results
