"""Nationwide POI EDA on vn-poi-core-v1 (W1-02 checklist)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(r"d:\vsf\data\vietnam\poi_corpus_v1")
POIS = ROOT / "pois_core.parquet"
OUT = ROOT / "eda"
OUT.mkdir(parents=True, exist_ok=True)

VN_BBOX = (102.0, 7.5, 110.5, 23.6)  # lon_min, lat_min, lon_max, lat_max


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("Ä‘", "d").replace("Ä", "D")
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def lang_bucket(name: str) -> str:
    if not name:
        return "empty"
    if re.search(r"[Ã€-á»¹]", name):
        return "vi_diacritic"
    if re.search(r"[A-Za-z]", name) and not re.search(r"[Ã€-á»¹]", name):
        return "latin_no_vi_diacritic"
    if re.search(r"\d", name):
        return "has_digit"
    return "other"


def main() -> None:
    rows = pq.read_table(POIS).to_pylist()
    n = len(rows)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ids = [r["poi_id"] for r in rows]
    id_unique = len(set(ids))

    missing_point = 0
    invalid_point = 0
    outside_vn = 0
    empty_name = 0
    with_alias = 0
    addr_status = Counter()
    addr_has_hn_street = 0
    cat0 = Counter()
    cat_unknown = 0
    osm_type = Counter()
    province = Counter()
    subdistrict_missing = 0
    preserve = 0
    platformish = 0
    brand_n = 0
    ref_n = 0
    lang = Counter()
    name_lens = []

    # same-name (folded) â€” global and within province
    fold_to_ids: dict[str, list[str]] = defaultdict(list)
    fold_prov_to_ids: dict[tuple[str, str], list[str]] = defaultdict(list)

    # node/way near-dup candidates: same folded name within 80m
    by_fold_points: dict[str, list[tuple[str, str, float, float]]] = defaultdict(list)

    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            empty_name += 1
        aliases = r.get("aliases") or []
        if hasattr(aliases, "tolist"):
            aliases = aliases.tolist()
        if aliases:
            with_alias += 1
        lang[lang_bucket(name)] += 1
        name_lens.append(len(name))

        pt = r.get("ranking_point") or {}
        try:
            lat = float(pt["lat"]) if pt.get("lat") is not None else None
            lon = float(pt["lon"]) if pt.get("lon") is not None else None
        except (TypeError, ValueError):
            lat = lon = None
        if lat is None or lon is None:
            missing_point += 1
        elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
            invalid_point += 1
        else:
            lon0, lat0, lon1, lat1 = VN_BBOX
            if not (lon0 <= lon <= lon1 and lat0 <= lat <= lat1):
                outside_vn += 1

        st = r.get("address_status") or "missing"
        addr_status[st] += 1
        addr = r.get("address") or {}
        if addr.get("housenumber") and (addr.get("street") or addr.get("place")):
            addr_has_hn_street += 1

        cat = (r.get("category") or "unknown").split("|")[0].strip() or "unknown"
        cat0[cat] += 1
        if cat in {"unknown", ""}:
            cat_unknown += 1

        osm_type[r.get("osm_type") or "?"] += 1
        prov = r.get("province") or "(unknown)"
        province[prov] += 1
        if not r.get("subdistrict"):
            subdistrict_missing += 1
        if r.get("preserve_individual_access_point"):
            preserve += 1
        if "public_transport=platform" in (r.get("category") or "") or "public_transport=stop_position" in (
            r.get("category") or ""
        ):
            platformish += 1
        if r.get("brand"):
            brand_n += 1
        if r.get("ref"):
            ref_n += 1

        if name and lat is not None and lon is not None:
            f = fold(name)
            if f:
                fold_to_ids[f].append(r["poi_id"])
                fold_prov_to_ids[(f, prov)].append(r["poi_id"])
                by_fold_points[f].append((r["poi_id"], r.get("osm_type") or "", lat, lon))

    # Ambiguity groups
    fold_ge2 = {k: v for k, v in fold_to_ids.items() if len(v) >= 2}
    fold_prov_ge2 = {k: v for k, v in fold_prov_to_ids.items() if len(v) >= 2}
    names_with_label = sum(1 for r in rows if (r.get("name") or "").strip())

    # Near-dup: same fold, different osm_type node+way within 80m, or any two within 25m
    near_dup_pairs = 0
    node_way_pairs = 0
    sampled_pairs = []
    for f, pts in by_fold_points.items():
        if len(pts) < 2 or len(pts) > 80:
            # skip huge same-name brands for pair explosion; count group only
            if len(pts) > 80:
                continue
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                a, b = pts[i], pts[j]
                d = haversine_m(a[2], a[3], b[2], b[3])
                if d <= 80:
                    near_dup_pairs += 1
                    types = {a[1], b[1]}
                    if types == {"node", "way"} and d <= 80:
                        node_way_pairs += 1
                        if len(sampled_pairs) < 30:
                            sampled_pairs.append(
                                {
                                    "fold": f,
                                    "poi_a": a[0],
                                    "poi_b": b[0],
                                    "distance_m": round(d, 1),
                                    "kind": "node_way",
                                }
                            )
                    elif d <= 25 and len(sampled_pairs) < 60:
                        sampled_pairs.append(
                            {
                                "fold": f,
                                "poi_a": a[0],
                                "poi_b": b[0],
                                "distance_m": round(d, 1),
                                "kind": "same_fold_le_25m",
                            }
                        )

    def rate(num, den):
        return round(num / den, 6) if den else None

    metrics = [
        {"metric": "rows", "n": n, "N": n, "rate": 1.0, "universe": "pois_core"},
        {"metric": "poi_id_unique", "n": id_unique, "N": n, "rate": rate(id_unique, n), "universe": "pois_core"},
        {"metric": "duplicate_poi_id_rows", "n": n - id_unique, "N": n, "rate": rate(n - id_unique, n), "universe": "pois_core"},
        {"metric": "empty_name", "n": empty_name, "N": n, "rate": rate(empty_name, n), "universe": "pois_core"},
        {"metric": "with_alias", "n": with_alias, "N": n, "rate": rate(with_alias, n), "universe": "pois_core"},
        {"metric": "missing_ranking_point", "n": missing_point, "N": n, "rate": rate(missing_point, n), "universe": "pois_core"},
        {"metric": "invalid_latlon", "n": invalid_point, "N": n, "rate": rate(invalid_point, n), "universe": "pois_core"},
        {"metric": "outside_vn_bbox", "n": outside_vn, "N": n, "rate": rate(outside_vn, n), "universe": "pois_core"},
        {"metric": "address_status_missing", "n": addr_status.get("missing", 0), "N": n, "rate": rate(addr_status.get("missing", 0), n), "universe": "pois_core"},
        {"metric": "address_status_direct", "n": addr_status.get("direct", 0), "N": n, "rate": rate(addr_status.get("direct", 0), n), "universe": "pois_core"},
        {"metric": "housenumber_and_street_or_place", "n": addr_has_hn_street, "N": n, "rate": rate(addr_has_hn_street, n), "universe": "pois_core"},
        {"metric": "subdistrict_missing", "n": subdistrict_missing, "N": n, "rate": rate(subdistrict_missing, n), "universe": "pois_core"},
        {"metric": "province_unknown", "n": province.get("(unknown)", 0), "N": n, "rate": rate(province.get("(unknown)", 0), n), "universe": "pois_core"},
        {"metric": "with_brand", "n": brand_n, "N": n, "rate": rate(brand_n, n), "universe": "pois_core"},
        {"metric": "with_ref", "n": ref_n, "N": n, "rate": rate(ref_n, n), "universe": "pois_core"},
        {"metric": "preserve_individual_access_point", "n": preserve, "N": n, "rate": rate(preserve, n), "universe": "pois_core"},
        {"metric": "category_public_transport_platform_or_stop", "n": platformish, "N": n, "rate": rate(platformish, n), "universe": "pois_core"},
        {"metric": "category_unknown", "n": cat_unknown, "N": n, "rate": rate(cat_unknown, n), "universe": "pois_core"},
        {
            "metric": "folded_name_groups_size_ge_2",
            "n": len(fold_ge2),
            "N": len(fold_to_ids),
            "rate": rate(len(fold_ge2), len(fold_to_ids)),
            "universe": "distinct_folded_names",
        },
        {
            "metric": "pois_in_folded_name_groups_ge_2",
            "n": sum(len(v) for v in fold_ge2.values()),
            "N": names_with_label,
            "rate": rate(sum(len(v) for v in fold_ge2.values()), names_with_label),
            "universe": "named_pois",
        },
        {
            "metric": "folded_name_province_groups_ge_2",
            "n": len(fold_prov_ge2),
            "N": len(fold_prov_to_ids),
            "rate": rate(len(fold_prov_ge2), len(fold_prov_to_ids)),
            "universe": "distinct_folded_name_x_province",
        },
        {
            "metric": "near_dup_pairs_same_fold_le_80m_excl_huge_groups",
            "n": near_dup_pairs,
            "N": None,
            "rate": None,
            "universe": "pair_count_heuristic",
        },
        {
            "metric": "node_way_same_fold_pairs_le_80m",
            "n": node_way_pairs,
            "N": None,
            "rate": None,
            "universe": "pair_count_heuristic",
        },
    ]

    top_ambiguous = sorted(fold_ge2.items(), key=lambda kv: -len(kv[1]))[:30]
    top_ambiguous_rows = [
        {"folded_name": k, "n_pois": len(v), "example_poi_ids": ", ".join(v[:5])} for k, v in top_ambiguous
    ]

    payload = {
        "created_at": created,
        "corpus_version": "vn-poi-core-v1",
        "source": str(POIS),
        "source_sha256_12": hashlib.sha256(POIS.read_bytes()).hexdigest()[:12],
        "n": n,
        "metrics": metrics,
        "osm_type_counts": dict(osm_type),
        "address_status_counts": dict(addr_status),
        "language_heuristic_counts": dict(lang),
        "category_top30_first_token": dict(cat0.most_common(30)),
        "province_counts": dict(province.most_common()),
        "name_length_chars": {
            "min": min(name_lens) if name_lens else None,
            "max": max(name_lens) if name_lens else None,
            "mean": round(sum(name_lens) / len(name_lens), 2) if name_lens else None,
        },
        "same_name_note": "folded_name groups are ambiguity candidates, not confirmed duplicates",
        "near_dup_sample": sampled_pairs[:40],
        "top_ambiguous_folded_names": top_ambiguous_rows,
    }

    (OUT / "poi_eda_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# W1-02 POI EDA â€” Vietnam `pois_core` (vn-poi-core-v1)",
        "",
        f"Cháº¡y: `{created}` Â· N={n:,} Â· file `{POIS.name}` (sha12 `{payload['source_sha256_12']}`).",
        "",
        "Universe chÃ­nh = toÃ n bá»™ `pois_core` (= destination_searchable trong build nÃ y).",
        "Same-name = ambiguity cho tá»›i khi cÃ³ báº±ng chá»©ng cÃ¹ng thá»±c thá»ƒ. Near-dup = á»©ng viÃªn, chÆ°a collapse.",
        "",
        "## Metrics (n/N)",
        "",
        "| metric | n | N | rate | universe |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for m in metrics:
        md.append(
            f"| {m['metric']} | {m['n'] if m['n'] is not None else ''} | {m['N'] if m['N'] is not None else ''} | {m['rate'] if m['rate'] is not None else ''} | {m['universe']} |"
        )

    md += [
        "",
        "## OSM type",
        "",
        "| type | n |",
        "| --- | ---: |",
    ]
    for k, v in osm_type.most_common():
        md.append(f"| {k} | {v} |")

    md += [
        "",
        "## Language heuristic (name)",
        "",
        "| bucket | n |",
        "| --- | ---: |",
    ]
    for k, v in lang.most_common():
        md.append(f"| {k} | {v} |")

    md += [
        "",
        "## Category top 30 (first token)",
        "",
        "| category | n |",
        "| --- | ---: |",
    ]
    for k, v in cat0.most_common(30):
        md.append(f"| {k} | {v} |")

    md += [
        "",
        "## Top ambiguous folded names (global)",
        "",
        "| folded_name | n_pois | examples |",
        "| --- | ---: | --- |",
    ]
    for row in top_ambiguous_rows:
        md.append(f"| {row['folded_name']} | {row['n_pois']} | {row['example_poi_ids']} |")

    md += [
        "",
        "## Near-dup sample (heuristic)",
        "",
        f"Pairs same-fold â‰¤80 m (groups sizeâ‰¤80): **{near_dup_pairs}**; nodeâ€“way trong Ä‘Ã³: **{node_way_pairs}**.",
        "",
        "| kind | fold | poi_a | poi_b | distance_m |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for p in sampled_pairs[:25]:
        md.append(f"| {p['kind']} | {p['fold']} | {p['poi_a']} | {p['poi_b']} | {p['distance_m']} |")

    md += [
        "",
        "## Province distribution",
        "",
        "| province | n |",
        "| --- | ---: |",
    ]
    for k, v in province.most_common():
        md.append(f"| {k} | {v} |")

    md += [
        "",
        "## Káº¿t luáº­n ngáº¯n",
        "",
        f"- ID unique: {id_unique == n}; tá»a Ä‘á»™ thiáº¿u/invalid: {missing_point}/{invalid_point}; ngoÃ i bbox VN: {outside_vn}.",
        f"- Address missing: {addr_status.get('missing', 0):,}/{n:,} ({100 * rate(addr_status.get('missing', 0), n):.1f}%).",
        f"- Folded same-name groups â‰¥2: {len(fold_ge2):,} / {len(fold_to_ids):,} tÃªn; áº£nh hÆ°á»Ÿng {sum(len(v) for v in fold_ge2.values()):,} POI.",
        f"- á»¨ng viÃªn nodeâ€“way gáº§n (â‰¤80 m, cÃ¹ng fold): {node_way_pairs} cáº·p â€” cáº§n pass dedup trÆ°á»›c canonical.",
        "- KhÃ´ng suy pickup/routing; access assumed per core schema.",
        "",
    ]
    (OUT / "poi_eda_summary.md").write_text("\n".join(md), encoding="utf-8")

    # also refresh pointer in corpus report
    pointer = ROOT / "vietnam_poi_corpus_report.md"
    extra = (
        "\n## POI EDA\n\n"
        f"BÃ¡o cÃ¡o Ä‘áº§y Ä‘á»§ W1-02: [`eda/poi_eda_summary.md`](eda/poi_eda_summary.md) "
        f"(JSON: `eda/poi_eda_summary.json`).\n"
    )
    text = pointer.read_text(encoding="utf-8")
    if "## POI EDA" not in text:
        pointer.write_text(text.rstrip() + "\n" + extra, encoding="utf-8")

    print(json.dumps({"n": n, "fold_ge2": len(fold_ge2), "node_way_pairs": node_way_pairs, "out": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
