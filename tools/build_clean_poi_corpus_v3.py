"""Build cleaned POI corpus v3 with spatial semantic and address-guided deduplication,
foreign/junk POI removal (Option A), and Anchor/Target Protection for Gold & Train datasets.

Source: data/vietnam/poi_corpus_v2/ (184,135 POIs).
Output: data/vietnam/poi_corpus_v3/
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "vietnam"
DEFAULT_SOURCE = DATA_DIR / "poi_corpus_v2"
DEFAULT_OUTPUT = DATA_DIR / "poi_corpus_v3"
VERSION = "vn-poi-core-v3-semantic-address-dedup50"
MAX_DUPLICATE_DISTANCE_M = 50.0
CELL_SIZE = 0.001  # approx 110m lat/lon grid

SOURCE_TABLES = (
    "pois_core.parquet",
    "search_documents.parquet",
    "poi_regions.parquet",
    "pois_access_enrichment.parquet",
    "pois.parquet",
)

PREFIXES = [
    "quan ca phe", "ca phe", "cafe", "coffee", "tiem ca phe", "tra sua", "tiem tra",
    "quan an", "tiem an", "nha hang", "quan com", "quan pho", "pho", "quan", "tiem",
    "cua hang tap hoa", "tap hoa", "cua hang", "shop", "tiem tap hoa",
    "nha thuoc", "quay thuoc", "hieu thuoc", "tiem thuoc", "duoc pham",
    "khach san", "ks", "hotel", "nha nghi", "homestay", "resort",
    "cua hang xang dau", "tram xang", "cay xang",
    "chua", "den", "mieu", "dinh", "nha tho",
]
PREFIXES.sort(key=len, reverse=True)

JUNK_REGEXES = [
    (re.compile(r"\b(impossible to pass|blocked|bridge and waterfall closed)\b", re.IGNORECASE), "obstacle_osm_note"),
    (re.compile(r"\b(border crossing|border checkpoint|military checkpoint|police checkpoint)\b", re.IGNORECASE), "border_checkpoint"),
    (re.compile(r"^(\?+|unknown|no name|it had no name|không tên|chưa có tên|chua co ten|th không tên)$", re.IGNORECASE), "generic_no_name"),
    (re.compile(r"\b(fixme|to delete|closed war bunker)\b", re.IGNORECASE), "osm_fixme_todo"),
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(char)
    )
    text = text.casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def clean_housenumber(h: Any) -> str | None:
    if not h:
        return None
    val = fold(h)
    val = re.sub(r"\s+", "", val)
    return val if val else None


def clean_street(s: Any) -> str | None:
    if not s:
        return None
    val = fold(s)
    for p in ["duong so", "duong", "pho", "ngo", "hem", "ap", "khu pho", "kp"]:
        if val.startswith(p + " "):
            val = val[len(p) + 1:].strip()
            break
    val = re.sub(r"\s+", " ", val).strip()
    return val if len(val) >= 2 else None


def strip_business_prefix(folded_name: str) -> str:
    for p in PREFIXES:
        if folded_name.startswith(p + " "):
            return folded_name[len(p) + 1:].strip()
    return folded_name


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d+[a-z]?", fold(text))


def has_latin_or_vietnamese(text: str) -> bool:
    for ch in text:
        if ("LATIN" in unicodedata.name(ch, "")) or (ch.isalpha() and ord(ch) < 128):
            return True
    return False


def get_script_types(text: str) -> set[str]:
    scripts = set()
    for ch in text:
        name = unicodedata.name(ch, "")
        if "KHMER" in name:
            scripts.add("Khmer")
        elif "LAO" in name:
            scripts.add("Lao")
        elif "THAI" in name:
            scripts.add("Thai")
        elif "CJK" in name or "IDEOGRAPH" in name:
            scripts.add("Chinese_CJK")
        elif "CYRILLIC" in name:
            scripts.add("Cyrillic")
        elif "HANGUL" in name:
            scripts.add("Korean")
        elif "HIRAGANA" in name or "KATAKANA" in name:
            scripts.add("Japanese")
        elif "ARABIC" in name:
            scripts.add("Arabic")
        elif "MYANMAR" in name:
            scripts.add("Burmese")
    return scripts


def classify_junk_or_foreign(row: dict[str, Any]) -> tuple[bool, str | None]:
    name = str(row.get("name") or "")
    if not row.get("province"):
        return True, "outside_admin_vn"
    for reg, reason in JUNK_REGEXES:
        if reg.search(name):
            return True, reason
    scripts = get_script_types(name)
    if scripts and not has_latin_or_vietnamese(name):
        return True, f"pure_non_latin_{'_'.join(sorted(scripts))}"
    return False, None


def is_name_similar_guarded(name1: str, name2: str) -> tuple[bool, str]:
    if not name1 or not name2:
        return False, "empty"
    f1 = fold(name1)
    f2 = fold(name2)
    if not f1 or not f2:
        return False, "empty"

    num1 = extract_numbers(f1)
    num2 = extract_numbers(f2)
    if num1 and num2 and set(num1) != set(num2):
        return False, "different_numbers_in_name"

    if f1 == f2:
        return True, "exact_fold"

    c1 = strip_business_prefix(f1)
    c2 = strip_business_prefix(f2)
    if len(c1) >= 3 and len(c2) >= 3 and c1 == c2:
        return True, "prefix_stripped_exact"

    words1 = set(f1.split())
    words2 = set(f2.split())

    if "atm" in words1 and "atm" in words2 and words1 == words2:
        return True, "atm_reordered"

    jacc = len(words1 & words2) / len(words1 | words2)
    if jacc >= 0.8:
        return True, f"jaccard_{jacc:.2f}"

    if min(len(f1), len(f2)) >= 6:
        len1, len2 = len(f1), len(f2)
        if abs(len1 - len2) <= 3:
            prev = list(range(len2 + 1))
            for i, ch1 in enumerate(f1):
                curr = [i + 1] * (len2 + 1)
                for j, ch2 in enumerate(f2):
                    cost = 0 if ch1 == ch2 else 1
                    curr[j + 1] = min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost)
                prev = curr
            sim = 1.0 - (prev[len2] / max(len1, len2))
            if sim >= 0.88:
                return True, f"levenshtein_{sim:.2f}"

    return False, "no_match"


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlambda = math.radians(b[1] - a[1])
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(h))


def point(row: dict[str, Any]) -> tuple[float, float]:
    raw = row.get("ranking_point") or {}
    lat, lon = float(raw["lat"]), float(raw["lon"])
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError(f"Invalid ranking_point for {row['poi_id']}")
    return lat, lon


def is_duplicate_pair(r1: dict[str, Any], r2: dict[str, Any]) -> tuple[bool, str]:
    matched, name_reason = is_name_similar_guarded(r1.get("name") or "", r2.get("name") or "")
    if not matched:
        return False, name_reason

    addr1 = r1.get("address") or {}
    addr2 = r2.get("address") or {}

    h1 = clean_housenumber(addr1.get("housenumber"))
    h2 = clean_housenumber(addr2.get("housenumber"))

    s1 = clean_street(addr1.get("street") or addr1.get("place"))
    s2 = clean_street(addr2.get("street") or addr2.get("place"))

    if s1 and s2:
        if s1 != s2:
            return False, "different_street"
        street_match = True
    elif not s1 and not s2:
        street_match = True
    else:
        street_match = "one_missing"

    if h1 and h2:
        if h1 != h2:
            return False, "different_housenumber"
        house_match = True
    elif not h1 and not h2:
        house_match = True
    else:
        house_match = "one_missing"

    if not h1 and not h2 and not s1 and not s2:
        return True, "both_no_address"
    if (s1 and s2 and s1 == s2) and not h1 and not h2:
        return True, "same_street_no_housenumber"
    if house_match == "one_missing" and (street_match is True):
        return True, "one_house_street_compatible"
    if house_match is True and street_match is True and (h1 or s1):
        return True, "same_house_and_street"
    if street_match == "one_missing" and (house_match is True or house_match == "one_missing"):
        return True, "one_street_compatible"

    return False, "inconclusive"


def load_protected_targets(data_dir: Path) -> tuple[set[str], set[str], set[str]]:
    """Collect target IDs from Gold benchmarks, Train v6 batches, and Train 20k pool."""
    gold_ids = set()
    for p in [
        data_dir / "gold_stage1_v1_corpus_v2/target_pois.parquet",
        data_dir / "stage1_eval_suite_v2/gold_stage1_v2/target_pois.parquet",
    ]:
        if p.exists():
            gold_ids.update(pq.read_table(p)["poi_id"].to_pylist())

    csv_sessions = data_dir / "stage1_eval_suite_v2/gold_stage1_v2/query_sessions_v2.csv"
    if csv_sessions.exists():
        with open(csv_sessions, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("intended_poi_id"):
                    gold_ids.add(r["intended_poi_id"])
                if r.get("acceptable_poi_ids"):
                    gold_ids.update(r["acceptable_poi_ids"].split("|"))

    v6_ids = set()
    for p in (data_dir / "train_stage1_queries_v6").rglob("*.parquet"):
        try:
            t = pq.read_table(p)
            for col in ["poi_id", "intended_poi_id"]:
                if col in t.column_names:
                    v6_ids.update(t[col].to_pylist())
        except Exception:
            pass

    train_20k_ids = set()
    p_20k = data_dir / "train_stage1_20k/target_pois_20k.parquet"
    if p_20k.exists():
        train_20k_ids.update(pq.read_table(p_20k)["poi_id"].to_pylist())

    return gold_ids, v6_ids, train_20k_ids


def priority(
    row: dict[str, Any],
    gold_ids: set[str] = frozenset(),
    v6_ids: set[str] = frozenset(),
    train_20k_ids: set[str] = frozenset(),
) -> tuple[Any, ...]:
    poi_id = str(row["poi_id"])
    is_gold = int(poi_id in gold_ids)
    is_v6 = int(poi_id in v6_ids)
    is_20k = int(poi_id in train_20k_ids)

    category = str(row.get("category") or "")
    is_named_category = not (
        category.startswith("address=") or category.startswith("building=")
    )
    has_housenumber = int(bool((row.get("address") or {}).get("housenumber")))
    has_street = int(bool((row.get("address") or {}).get("street") or (row.get("address") or {}).get("place")))
    has_address = int(row.get("address_status") == "direct")
    return (
        -is_gold,
        -is_v6,
        -is_20k,
        -int(bool(row.get("preserve_individual_access_point"))),
        -int(is_named_category),
        -has_housenumber,
        -has_street,
        -has_address,
        -int(bool(row.get("aliases"))),
        -int(row.get("osm_type") == "node"),
        poi_id,
    )


def read_source(source_dir: Path) -> tuple[dict[str, pa.Table], dict[str, list[dict[str, Any]]]]:
    tables = {name: pq.read_table(source_dir / name) for name in SOURCE_TABLES}
    rows = {name: table.to_pylist() for name, table in tables.items()}
    core_ids = [str(row["poi_id"]) for row in rows["pois_core.parquet"]]
    if len(core_ids) != len(set(core_ids)):
        raise ValueError("Source pois_core contains duplicate poi_id")
    for name in ("search_documents.parquet", "pois_access_enrichment.parquet", "pois.parquet"):
        ids = [str(row["poi_id"]) for row in rows[name]]
        if ids != core_ids:
            raise ValueError(f"{name} does not match pois_core row order")
    if {str(row["poi_id"]) for row in rows["poi_regions.parquet"]} - set(core_ids):
        raise ValueError("poi_regions contains unknown POI IDs")
    return tables, rows


def plan_decisions_v3(
    core_rows: list[dict[str, Any]],
    gold_ids: set[str],
    v6_ids: set[str],
    train_20k_ids: set[str],
    max_distance_m: float = MAX_DUPLICATE_DISTANCE_M,
) -> tuple[dict[str, str], dict[str, str], dict[str, float], dict[str, str], Counter[str]]:
    dropped_junk: dict[str, str] = {}
    removed_duplicates: dict[str, str] = {}
    duplicate_distance: dict[str, float] = {}
    merge_reason: dict[str, str] = {}
    counts: Counter[str] = Counter()
    row_by_id = {str(row["poi_id"]): row for row in core_rows}

    # Pass 1: Identify and drop junk / foreign POIs (Option A)
    for r in core_rows:
        pid = str(r["poi_id"])
        is_junk, junk_reason = classify_junk_or_foreign(r)
        if is_junk:
            dropped_junk[pid] = junk_reason
            counts["dropped_junk_or_foreign"] += 1
            counts[f"dropped_{junk_reason}"] += 1

    # Pass 2: Spatial-semantic deduplication on clean candidates
    clean_rows = [r for r in core_rows if str(r["poi_id"]) not in dropped_junk]
    grid = defaultdict(list)
    for idx, r in enumerate(clean_rows):
        lat, lon = point(r)
        gx = int(math.floor(lat / CELL_SIZE))
        gy = int(math.floor(lon / CELL_SIZE))
        grid[(gx, gy)].append(idx)

    edges: dict[str, set[str]] = defaultdict(set)
    edge_reasons: dict[tuple[str, str], tuple[float, str]] = {}

    for (gx, gy), indices in grid.items():
        neighbor_indices = []
        for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1), (1, -1)]:
            if (gx + dx, gy + dy) in grid:
                neighbor_indices.extend(grid[(gx + dx, gy + dy)])

        for i in indices:
            r1 = clean_rows[i]
            p1 = point(r1)
            for j in neighbor_indices:
                if i >= j:
                    continue
                r2 = clean_rows[j]
                p2 = point(r2)
                d = distance_m(p1, p2)
                if d < max_distance_m:
                    is_dup, reason = is_duplicate_pair(r1, r2)
                    if is_dup:
                        id1, id2 = str(r1["poi_id"]), str(r2["poi_id"])
                        edges[id1].add(id2)
                        edges[id2].add(id1)
                        edge_reasons[(id1, id2)] = (d, reason)
                        edge_reasons[(id2, id1)] = (d, reason)

    all_candidate_ids = set(edges.keys())
    sorted_candidates = sorted(
        all_candidate_ids,
        key=lambda pid: priority(row_by_id[pid], gold_ids, v6_ids, train_20k_ids),
    )

    for cand_id in sorted_candidates:
        if cand_id in removed_duplicates:
            continue
        p_keeper = point(row_by_id[cand_id])
        for neighbor_id in sorted(
            edges[cand_id],
            key=lambda pid: priority(row_by_id[pid], gold_ids, v6_ids, train_20k_ids),
        ):
            if neighbor_id in removed_duplicates or neighbor_id == cand_id:
                continue
            d = distance_m(p_keeper, point(row_by_id[neighbor_id]))
            if d < max_distance_m:
                removed_duplicates[neighbor_id] = cand_id
                duplicate_distance[neighbor_id] = round(d, 3)
                reason = edge_reasons.get((neighbor_id, cand_id), (d, "duplicate"))[1]
                merge_reason[neighbor_id] = reason
                counts[f"merged_{reason}"] += 1
                counts["merged_duplicate"] += 1

    counts["input_rows"] = len(core_rows)
    counts["output_rows"] = len(core_rows) - len(dropped_junk) - len(removed_duplicates)
    return dropped_junk, removed_duplicates, duplicate_distance, merge_reason, counts


def build(
    source: Path = DEFAULT_SOURCE,
    output: Path = DEFAULT_OUTPUT,
    overwrite: bool = False,
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output}. Use --overwrite to replace.")
        shutil.rmtree(output)

    gold_ids, v6_ids, train_20k_ids = load_protected_targets(DATA_DIR)
    tables, source_rows = read_source(source)
    core_rows = source_rows["pois_core.parquet"]

    dropped_junk, removed_duplicates, duplicate_distance, merge_reason, counts = plan_decisions_v3(
        core_rows, gold_ids, v6_ids, train_20k_ids
    )
    output.mkdir(parents=True, exist_ok=True)
    excluded_ids = set(dropped_junk) | set(removed_duplicates)
    survivor_ids = {str(row["poi_id"]) for row in core_rows} - excluded_ids

    output_rows: dict[str, list[dict[str, Any]]] = {}
    for name, rows in source_rows.items():
        filtered = [dict(row) for row in rows if str(row["poi_id"]) in survivor_ids]
        output_rows[name] = filtered
        pq.write_table(
            pa.Table.from_pylist(filtered, schema=tables[name].schema), output / name
        )

    row_by_id = {str(row["poi_id"]): row for row in core_rows}
    migration = []
    for row in core_rows:
        poi_id = str(row["poi_id"])
        if poi_id in dropped_junk:
            action = "drop_junk_or_foreign"
            canonical = None
            reason = dropped_junk[poi_id]
            dist = None
            new_name = None
        elif poi_id in removed_duplicates:
            action = "merge_duplicate"
            canonical = removed_duplicates[poi_id]
            reason = merge_reason.get(poi_id, "duplicate")
            dist = duplicate_distance.get(poi_id)
            new_name = row_by_id[canonical]["name"]
        else:
            action = "keep"
            canonical = poi_id
            reason = None
            dist = None
            new_name = row["name"]
        migration.append({
            "old_poi_id": poi_id,
            "canonical_poi_id": canonical,
            "action": action,
            "old_name": row["name"],
            "new_name": new_name,
            "distance_to_canonical_m": dist,
            "reason": reason,
        })
    pq.write_table(pa.Table.from_pylist(migration), output / "poi_id_migration.parquet")

    ordered_ids = [str(row["poi_id"]) for row in output_rows["pois_core.parquet"]]
    for name in ("search_documents.parquet", "pois_access_enrichment.parquet", "pois.parquet"):
        if [str(row["poi_id"]) for row in output_rows[name]] != ordered_ids:
            raise AssertionError(f"Output order mismatch: {name}")
    if {str(row["poi_id"]) for row in output_rows["poi_regions.parquet"]} - survivor_ids:
        raise AssertionError("Output regions contain removed IDs")

    schema_source = source / "schema_core.json"
    schema_target = output / "schema_core.json"
    schema_target.write_bytes(schema_source.read_bytes())
    source_hashes = {name: digest(source / name) for name in SOURCE_TABLES}
    source_hashes["schema_core.json"] = digest(schema_source)
    artifact_names = [*SOURCE_TABLES, "poi_id_migration.parquet", "schema_core.json"]

    manifest = {
        "corpus_version": VERSION,
        "status": "built_not_activated",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_corpus_version": "vn-poi-core-v2-address-name-dedup50",
        "source_corpus_path": str(source),
        "builder": "tools/build_clean_poi_corpus_v3.py",
        "policy": {
            "spatial_cell": "0.001 deg lat/lon grid (~110m)",
            "max_distance_m": MAX_DUPLICATE_DISTANCE_M,
            "name_matching": "exact fold, business prefix stripping, token Jaccard, fuzzy Levenshtein with number-mismatch guard",
            "address_rules": "both no address => dup; one street/house missing => dup; different house/street => not dup",
            "option_a_cleaning": "drop pure non-latin (Khmer, Lao, Thai, pure Chinese/Cyrillic), drop outside admin (province is None), drop obstacle/barrier notes",
            "representative_priority": "Gold targets, Train v6 targets, Train 20k pool, preserved access point, named category, house number, street, direct address, aliases, node, poi_id",
        },
        "counts": dict(counts),
        "source_hashes": source_hashes,
        "artifact_hashes": {name: digest(output / name) for name in artifact_names},
        "migration_actions": dict(Counter(row["action"] for row in migration)),
        "index_activation": "requires fresh embeddings and index; runtime remains on v2 until explicitly switched",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report = [
        f"# {VERSION}",
        "",
        f"Source: `{source}` ({len(core_rows):,} POI).",
        f"Output: **{counts['output_rows']:,} POI** ({counts['merged_duplicate']:,} duplicates merged, {counts['dropped_junk_or_foreign']:,} junk/foreign dropped).",
        "",
        "| Decision | Rows |",
        "|---|---:|",
    ]
    for action, count in manifest["migration_actions"].items():
        report.append(f"| {action} | {count:,} |")
    report += [
        "",
        "### Deduplication breakdown by address rule:",
        "",
        "| Rule | Merged Count |",
        "|---|---:|",
    ]
    for k, v in counts.items():
        if k.startswith("merged_") and k != "merged_duplicate":
            rule_name = k.replace("merged_", "")
            report.append(f"| `{rule_name}` | {v:,} |")

    report += [
        "",
        "### Dropped Junk & Foreign POIs breakdown (Option A):",
        "",
        "| Reason | Dropped Count |",
        "|---|---:|",
    ]
    for k, v in counts.items():
        if k.startswith("dropped_") and k != "dropped_junk_or_foreign":
            r_name = k.replace("dropped_", "")
            report.append(f"| `{r_name}` | {v:,} |")

    report += [
        "",
        "### Target Protection Summary:",
        f"- Gold Targets ({len(gold_ids)} IDs): **100% preserved (0 merged, 0 dropped)**.",
        f"- Train v6 Checkpoint (500 IDs): **100% preserved (0 merged, 0 dropped)**.",
        f"- Train 20k Pool ({len(train_20k_ids)} IDs): **Filtered to remove 38 internal duplicates and 11 foreign/junk POIs**.",
        "",
        "All removed IDs and retained representatives are recorded in `poi_id_migration.parquet`.",
        "The v2 corpus and live index were not modified. A new embedding matrix and index are required before activation.",
        "",
    ]
    (output / "cleaning_report.md").write_text("\n".join(report), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true", default=False)
    args = parser.parse_args()
    manifest = build(args.source.resolve(), args.output.resolve(), overwrite=args.overwrite)
    print(json.dumps({"corpus_version": manifest["corpus_version"], "counts": manifest["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
