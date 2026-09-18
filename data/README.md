# Data — corpus & gold (SEARCH 2.0)

| Path | Nội dung |
|---|---|
| `data/vietnam/poi_corpus_v1/` | `vn-poi-core-v1` — `pois_core`, `search_documents`, `poi_regions`, … (~186k) |
| `data/vietnam/admin_regions_v1/` | Admin polygons + catalog |
| `data/vietnam/gold_stage1_v1/` | **Gold Stage 1 locked** — 180 POI · 1,080 queries |
| `data/vietnam/vietnam_nationwide_poi_count_report.*` | Scan đếm PBF |

Build scripts: `training/corpus_audit/` (`build_vietnam_poi_corpus.py`, `extract_vietnam_admin_regions.py`, …).

PBF nguồn (nếu có): `vietnam-*.osm.pbf` ở repo root.

> Đã gỡ: `HANOI_*`, `pilot_100`, `archive/pilot_110_*` (2026-09-18).
