# Hướng corpus & DB toàn quốc (SEARCH 2.0)

Ngày: 2026-09-16  
**Sản phẩm dữ liệu = Việt Nam** (ride-hailing). Hà Nội chỉ còn pilot eval / demo runtime cũ.  
**Artifact data** nằm dưới `data/vietnam/` — không để trong `training/`.

## Base

| Lớp | Path | Vai trò |
|---|---|---|
| Retrieval | `data/vietnam/poi_corpus_v1/pois_core.parquet` | Index / suggest |
| Access sidecar | `data/vietnam/poi_corpus_v1/pois_access_enrichment.parquet` | routing / pickup |
| Passages | `data/vietnam/poi_corpus_v1/search_documents.parquet` | Encode / lexical |
| Regions | `data/vietnam/poi_corpus_v1/poi_regions.parquet` | Admin membership |
| Admin | `data/vietnam/admin_regions_v1/` | Polygons + catalog |
| Pilot | `HANOI_POI_STABLE_V1` + `HANOI_QUERIES_20K` | Regression only |

## Schema

**Core (retrieval):** id, name, aliases, category, brand, ref, address lean, province/subdistrict + region ids, `ranking_point`, `destination_searchable`, entity/branch/preserve.

**Sidecar (ride-hail enrichment, join `poi_id`):**
- `routing_point` (+ status) — chưa populate
- `pickup_access_verified` (+ evidence) — hiện false
- Fallback hiển thị: `ranking_point` **không** = verified pickup

**Deferred:** `origin_search_eligible`, container/nearby_street, address 22-field, `complex_id`.

## Lộ trình

1. Dedup ≤50 m trên core  
2. Quarantine nhãn ngắn  
3. Rebuild index từ core + search_documents  
4. Pipeline điền access sidecar  
5. Eval đa tỉnh; giữ HN 20k regression  

## Rủi ro

Chưa dedup; thiếu `addr:*`; same-name; sidecar access đang placeholder.
