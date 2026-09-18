# Vietnam admin regions v1 (OSM relations)

Nguồn: `vietnam-260910.osm.pbf` (sha256 `867d3d6d721b5073…`).
Scheme: `vn-osm-pbf-260910-post2025-al4-al6`.
Thời gian extract: **165.1 s**.

## Chính sách

- Primary: `admin_level` **2** (quốc gia), **4** (tỉnh/TP), **6** (xã/phường/đặc khu) — theo tagging OSM VN sau cải cách 2025.
- Khóa vùng: `osm:relation/<id>` (không dùng tên phường làm ID).
- Geometry: lắp từ member ways của relation `boundary=administrative` (không full-area pass).
- `parent_ids`: level-6 ⊂ level-4 theo điểm đại diện (point-in-polygon).

## Kết quả

| Metric | Số |
|---|---:|
| Relations admin có `admin_level` | 8785 |
| Geometry lắp được | 8632 |
| Primary OK (level 2/4/6 trong bbox) | 3359 |
| Level 4 primary OK | 34 |
| Level 6 OK | 3327 |
| Level 6 có parent level-4 | 3322 |
| Relation thiếu `admin_level` (bỏ) | 22 |

### Theo admin_level (tất cả / geometry OK)

| Level | Relations | Geometry OK |
|---|---:|---:|
| 0 | 1 | 1 |
| 2 | 5 | 3 |
| 3 | 1 | 1 |
| 4 | 59 | 36 |
| 5 | 7 | 1 |
| 6 | 3396 | 3327 |
| 8 | 73 | 30 |
| 9 | 5240 | 5233 |
| 10 | 3 | 0 |

### Assemble status

```
{
  "unclosed_rings:1": 149,
  "ok_partial": 16,
  "ok": 8616,
  "unclosed_rings:2": 3,
  "no_outer_ways": 1
}
```

## Admin level 4 (tỉnh/TP) — primary OK

| OSM id | Label | Status | parent_ids |
|---|---|---|---|
| 1903516 | Hà Nội | ok | osm:relation/49915 |
| 1898458 | Hà Tĩnh | ok | osm:relation/49915 |
| 1887959 | Khánh Hòa | ok_partial | osm:relation/49915 |
| 1902690 | Thành phố Bắc Ninh | ok | osm:relation/49915 |
| 1874283 | Thành phố Cần Thơ | ok | osm:relation/49915 |
| 1891483 | Thành phố Huế | ok | osm:relation/49915 |
| 1902682 | Thành phố Hải Phòng | ok | osm:relation/49915 |
| 1973756 | Thành phố Hồ Chí Minh | ok | osm:relation/49915 |
| 1902947 | Thành phố Quảng Ninh | ok | osm:relation/49915 |
| 1891418 | Thành phố Đà Nẵng | ok | osm:relation/49915 |
| 1904421 | Thành phố Đồng Nai | ok | osm:relation/49915 |
| 1875748 | Tỉnh An Giang | ok | osm:relation/49915 |
| 1844412 | Tỉnh Cao Bằng | ok | osm:relation/49915 |
| 1873490 | Tỉnh Cà Mau | ok | osm:relation/49915 |
| 1884018 | Tỉnh Gia Lai | ok | osm:relation/49915 |
| 1901032 | Tỉnh Hưng Yên | ok | osm:relation/49915 |
| 1903322 | Tỉnh Lai Châu | ok | osm:relation/49915 |
| 1903400 | Tỉnh Lào Cai | ok | osm:relation/49915 |
| 1885367 | Tỉnh Lâm Đồng | ok | osm:relation/49915 |
| 5522596 | Tỉnh Lạng Sơn | ok | osm:relation/49915 |
| 1898509 | Tỉnh Nghệ An | ok | osm:relation/49915 |
| 1900963 | Tỉnh Ninh Bình | ok | osm:relation/49915 |
| 1902930 | Tỉnh Phú Thọ | ok | osm:relation/49915 |
| 1890793 | Tỉnh Quảng Ngãi | ok | osm:relation/49915 |
| 1895630 | Tỉnh Quảng Trị | ok | osm:relation/49915 |
| 1903291 | Tỉnh Sơn La | ok | osm:relation/49915 |
| 1898590 | Tỉnh Thanh Hóa | ok | osm:relation/49915 |
| 1902967 | Tỉnh Thái Nguyên | ok | osm:relation/49915 |
| 1903418 | Tỉnh Tuyên Quang | ok | osm:relation/49915 |
| 1898961 | Tỉnh Tây Ninh | ok | osm:relation/49915 |
| 1875887 | Tỉnh Vĩnh Long | ok | osm:relation/49915 |
| 1903340 | Tỉnh Điện Biên | ok | osm:relation/49915 |
| 1884034 | Tỉnh Đắk Lắk | ok | osm:relation/49915 |
| 1875866 | Tỉnh Đồng Tháp | ok | osm:relation/49915 |

## Artifacts

- `region_catalog.parquet` — catalog theo TECHNICAL_SPEC (`region_osm_id`, label, aliases, parent_ids, bbox, geometry_ref, admin_scheme_version, …)
- `region_geometries.parquet` — WKB multipolygon + `boundary_hash`
- `preview_admin_level_4.geojson` — xem nhanh tỉnh/TP
- `manifest.json` — provenance

## Bước tiếp

Dùng catalog + geometries để gắn `poi_regions.parquet` (point-in-polygon). Overlap → nhiều dòng membership; unknown không loại POI khỏi nhánh toàn quốc.
