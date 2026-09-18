# Vietnam POI core v1 (lean serving)

Version `vn-poi-core-v1` · policy `nationwide-core-v1-no-dedup` · admin `vn-osm-pbf-260910-post2025-al4-al6`  
PBF `vietnam-260910.osm.pbf` · **316.3 s** · rows **186,322**

## Schema quyết định

**Giữ (core):** id, name, aliases, category, brand, ref, address lean + `address_text`, province/subdistrict + region ids, `ranking_point`, `destination_searchable`, entity/branch/preserve.

**Sidecar access (không nằm retrieval):** `routing_point`, `pickup_access_verified` (+ status/evidence) — snapshot hiện **null/false toàn bộ**; **không** assume verified pickup.

**Bỏ khỏi core:** `origin_search_eligible`, `context.container_*`, `nearby_street_*`, address 22 field.

## Số liệu

| Metric | Số |
|---|---:|
| pois_core | 186,322 |
| nodes / ways | 122,389 / 63,933 |
| admin đủ province+subdistrict | 185,812 |
| chỉ province | 177 |
| không admin | 313 |

## Province

| Province | POI |
|---|---:|
| Thành phố Hồ Chí Minh | 53186 |
| Hà Nội | 46692 |
| Thành phố Đà Nẵng | 14598 |
| Thành phố Bắc Ninh | 10396 |
| Tỉnh Lâm Đồng | 6751 |
| Thành phố Cần Thơ | 5594 |
| Thành phố Đồng Nai | 5266 |
| Thành phố Hải Phòng | 4555 |
| Khánh Hòa | 4344 |
| Tỉnh An Giang | 4123 |
| Thành phố Huế | 2390 |
| Tỉnh Ninh Bình | 2286 |
| Tỉnh Hưng Yên | 2133 |
| Tỉnh Tây Ninh | 2132 |
| Tỉnh Đắk Lắk | 2099 |
| Tỉnh Gia Lai | 2074 |
| Tỉnh Đồng Tháp | 1900 |
| Tỉnh Quảng Trị | 1756 |
| Tỉnh Lào Cai | 1623 |
| Tỉnh Vĩnh Long | 1540 |
| Tỉnh Tuyên Quang | 1409 |
| Tỉnh Quảng Ngãi | 1272 |
| Thành phố Quảng Ninh | 1244 |
| Tỉnh Phú Thọ | 1137 |
| Tỉnh Nghệ An | 840 |
| Hà Tĩnh | 807 |
| Tỉnh Thanh Hóa | 766 |
| Tỉnh Thái Nguyên | 754 |
| Tỉnh Cao Bằng | 525 |
| Tỉnh Lạng Sơn | 402 |
| Tỉnh Cà Mau | 382 |
| Tỉnh Lai Châu | 363 |
| Tỉnh Sơn La | 347 |
| (unknown) | 333 |
| Tỉnh Điện Biên | 303 |

## Files

- `pois_core.parquet` — retrieval
- `pois_access_enrichment.parquet` — `routing_point` / `pickup_access_verified` (placeholder)
- `search_documents.parquet`
- `poi_regions.parquet`
- `schema_core.json` / `manifest.json`

## POI EDA

Báo cáo đầy đủ W1-02: [`eda/poi_eda_summary.md`](eda/poi_eda_summary.md) (JSON: `eda/poi_eda_summary.json`).
