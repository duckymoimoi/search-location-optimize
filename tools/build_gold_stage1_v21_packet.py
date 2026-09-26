"""Build source-only, compact case cards for manual Gold v2.1 authoring.

Do not read prior Gold queries or model results here. The packet contains POI
facts and same-name collision candidates only; an agent authors query text.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/vietnam"
TARGETS = BASE / "stage1_eval_suite_v2/gold_stage1_v2/target_pois_v2.parquet"
CORPUS = BASE / "poi_corpus_v3/pois_core.parquet"
TRAIN = BASE / "train_stage1_20k/target_pois_20k.parquet"
PINNED_TRAIN_V2 = BASE / "train_stage1_20k/target_pois_20k.parquet.v2bak"
OUT = BASE / "stage1_eval_suite_v2/staging/gold_stage1_v2_1"
OVERRIDES = OUT / "target_overrides_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fold(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("đ", "d")
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
    return " ".join(text.split())


def distance_m(a: dict | None, b: dict | None) -> float | None:
    if not a or not b or a.get("lat") is None or b.get("lat") is None:
        return None
    lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lon"]))
    lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lon"]))
    return 2 * 6371000 * math.asin(math.sqrt(
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    ))


def facts(row: dict) -> dict:
    return {
        "poi_id": row["poi_id"],
        "name": row.get("name"),
        "aliases": list(row.get("aliases") or [])[:12],
        "brand": row.get("brand"),
        "ref": row.get("ref"),
        "category": row.get("category"),
        "housenumber": (row.get("address") or {}).get("housenumber"),
        "street": (row.get("address") or {}).get("street"),
        "place": (row.get("address") or {}).get("place"),
        "subdistrict": row.get("subdistrict"),
        "province": row.get("province"),
        "address_text": row.get("address_text"),
        "entity_group_id": row.get("entity_group_id"),
        "ranking_point": row.get("ranking_point"),
    }


def collision_fact(row: dict, distance: float | None) -> dict:
    address = row.get("address") or {}
    return {
        "poi_id": row["poi_id"], "name": row.get("name"),
        "category": row.get("category"),
        "housenumber": address.get("housenumber"),
        "street": address.get("street"),
        "subdistrict": row.get("subdistrict"),
        "province": row.get("province"),
        "distance_m": round(distance, 1) if distance is not None else None,
    }


def main() -> None:
    targets = pq.read_table(TARGETS).to_pylist()
    if len(targets) != 200 or len({row["poi_id"] for row in targets}) != 200:
        raise SystemExit("Expected exactly 200 unique Gold target POIs")
    override_file = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    overrides = {row["case_id"]: row for row in override_file["replacements"]}
    if len(overrides) != len(override_file["replacements"]):
        raise SystemExit("Duplicate case_id in target overrides")
    target_cases = {row["case_id"] for row in targets}
    if set(overrides) - target_cases:
        raise SystemExit("Override references unknown Gold target case")
    effective_targets = []
    for original in targets:
        target = dict(original)
        if override := overrides.get(target["case_id"]):
            if target["poi_id"] != override["old_poi_id"]:
                raise SystemExit(f"Override old POI mismatch: {target['case_id']}")
            target["poi_id"] = override["new_poi_id"]
            target["case_origin"] = override["case_origin"]
            target["exposure_class"] = override["exposure_class"]
        effective_targets.append(target)
    if len({row["poi_id"] for row in effective_targets}) != 200:
        raise SystemExit("Effective Gold v2.1 targets are not unique")
    train_ids = set(pq.read_table(TRAIN, columns=["poi_id"])["poi_id"].to_pylist())
    train_ids.update(pq.read_table(PINNED_TRAIN_V2, columns=["poi_id"])["poi_id"].to_pylist())
    corpus_columns = [
        "poi_id", "name", "aliases", "brand", "ref", "category", "address",
        "address_text", "province", "subdistrict", "ranking_point",
        "destination_searchable", "entity_group_id",
    ]
    corpus_rows = pq.read_table(CORPUS, columns=corpus_columns).to_pylist()
    by_id = {row["poi_id"]: row for row in corpus_rows}
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in corpus_rows:
        if row["destination_searchable"] and (key := fold(row.get("name"))):
            by_name[key].append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    packet_path = OUT / "authoring_packet.jsonl"
    audit = {"missing_from_corpus": [], "not_searchable": [], "train_target_overlap": []}
    with packet_path.open("w", encoding="utf-8", newline="\n") as handle:
        for target in effective_targets:
            poi_id = target["poi_id"]
            row = by_id.get(poi_id)
            if row is None:
                audit["missing_from_corpus"].append(poi_id)
                continue
            if not row["destination_searchable"]:
                audit["not_searchable"].append(poi_id)
            if poi_id in train_ids:
                audit["train_target_overlap"].append(poi_id)
            candidates = [other for other in by_name.get(fold(row["name"]), [])
                          if other["poi_id"] != poi_id]
            distances = [(other, distance_m(row.get("ranking_point"), other.get("ranking_point")))
                         for other in candidates]
            distances.sort(key=lambda pair: (
                pair[1] if pair[1] is not None else float("inf"), pair[0]["poi_id"]
            ))
            collision_sample = [collision_fact(other, distance)
                                for other, distance in distances[:8]]
            card = {
                "case_id": target["case_id"],
                "poi_id": poi_id,
                "case_origin": target.get("case_origin"),
                "exposure_class": target.get("exposure_class"),
                "primary_sampling_stratum": target.get("primary_sampling_stratum"),
                "source": facts(row),
                "same_folded_name_count_excluding_target": len(candidates),
                "same_folded_name_nearest": collision_sample,
            }
            handle.write(json.dumps(card, ensure_ascii=False) + "\n")
    manifest = {
        "packet_version": "gold_stage1_v2_1_source_only_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "target_count": len(targets),
        "packet_rows": len(targets) - len(audit["missing_from_corpus"]),
        "source_hashes": {
            "target_pois_v2.parquet": sha256(TARGETS),
            "pois_core.parquet": sha256(CORPUS),
            "target_pois_20k.parquet": sha256(TRAIN),
            "target_pois_20k_v2_pinned.parquet": sha256(PINNED_TRAIN_V2),
            "target_overrides_v1.json": sha256(OVERRIDES),
        },
        "packet_sha256": sha256(packet_path),
        "audit": audit,
        "target_overrides": override_file["replacements"],
        "brand_lookup_note": "Existing brand lookup may predate corpus v3; verify membership before using brand-group qrels.",
        "excludes_prior_gold_queries_and_model_results": True,
    }
    (OUT / "authoring_packet_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"packet_rows": manifest["packet_rows"], "audit": audit,
                      "packet_sha256": manifest["packet_sha256"]}, ensure_ascii=False))
    if any(audit.values()):
        raise SystemExit("Target audit failed; do not author before adjudication")


if __name__ == "__main__":
    main()
