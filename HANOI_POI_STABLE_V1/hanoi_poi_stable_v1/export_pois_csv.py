"""Export flattened hn-poi-stable-v1 POI list to CSV for browsing."""
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "pois.parquet"
OUT = ROOT / "pois_stable_v1.csv"

ADDR_KEYS = [
    "housenumber",
    "street",
    "place",
    "unit",
    "floor",
    "block",
    "building",
    "housename",
    "quarter",
    "hamlet",
    "subdistrict",
    "district",
    "city",
    "province",
    "postcode",
    "country",
    "full",
    "suburb",
    "ward",
    "neighborhood",
    "neighbourhood",
    "state",
]
CTX_KEYS = [
    "container_name",
    "container_osm_id",
    "nearby_street",
    "nearby_street_osm_id",
    "nearby_street_distance_m_approx",
]


def _admin_to_str(admin) -> str:
    if not admin:
        return ""
    if isinstance(admin, list):
        parts = []
        for item in admin:
            if isinstance(item, dict):
                parts.append(f"{item.get('key')}={item.get('value')}")
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                parts.append(f"{item[0]}={item[1]}")
        return "|".join(parts)
    if isinstance(admin, dict):
        return "|".join(f"{k}={v}" for k, v in admin.items())
    return str(admin)


def main() -> None:
    rows = pq.read_table(SRC).to_pylist()
    flat = []
    for p in rows:
        addr = p.get("address") or {}
        ctx = p.get("context") or {}
        rp = p.get("ranking_point") or {}
        rtp = p.get("routing_point") or {}
        aliases = p.get("aliases") or []
        row = {
            "poi_id": p.get("poi_id"),
            "name": p.get("name"),
            "aliases": " | ".join(aliases) if aliases else "",
            "category": p.get("category"),
            "brand": p.get("brand"),
            "ref": p.get("ref"),
            "address_status": p.get("address_status"),
            "destination_searchable": p.get("destination_searchable"),
            "origin_search_eligible": p.get("origin_search_eligible"),
            "pickup_access_verified": p.get("pickup_access_verified"),
            "entity_group_id": p.get("entity_group_id"),
            "branch_id": p.get("branch_id"),
            "complex_id": p.get("complex_id"),
            "preserve_individual_access_point": p.get("preserve_individual_access_point"),
            "ranking_lat": rp.get("lat"),
            "ranking_lon": rp.get("lon"),
            "ranking_quality": rp.get("quality"),
            "routing_lat": rtp.get("lat") if rtp else None,
            "routing_lon": rtp.get("lon") if rtp else None,
            "routing_quality": rtp.get("quality") if rtp else None,
        }
        for k in ADDR_KEYS:
            row[f"address_{k}"] = addr.get(k)
        for k in CTX_KEYS:
            row[f"context_{k}"] = ctx.get(k)
        row["context_admin"] = _admin_to_str(ctx.get("admin"))
        flat.append(row)

    df = pd.DataFrame(flat)
    df = df.sort_values(
        by=["destination_searchable", "origin_search_eligible", "name", "poi_id"],
        ascending=[False, False, True, True],
        kind="mergesort",
    )
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Wrote {OUT}")
    print(f"Rows={len(df)}, cols={len(df.columns)}")
    print(f"Size_MB={OUT.stat().st_size / 1e6:.2f}")
    print(f"destination_searchable={int(df['destination_searchable'].sum())}")


if __name__ == "__main__":
    main()
