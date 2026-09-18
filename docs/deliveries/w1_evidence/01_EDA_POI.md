# SEARCH 2.0 — W1 EDA POI

**Corpus:** `vn-poi-core-v1` · `data/vietnam/poi_corpus_v1/`  
**N:** **186,322** destination-searchable POI (`pois_core` / `search_documents`)  
**Chạy EDA gốc:** `2026-09-16` · sha12 core `e5d75c4783f2`  
**Gold target overlay:** 180 POI trong `gold_stage1_v1/target_pois_v1.csv`

Báo cáo này trả lời: **kho địa điểm có gì, phân bố thế nào, chỗ nào bẩn/mơ hồ** — làm nền cho Stage 1 retrieval trên toàn quốc.

---

## 1. Universe

| Chỉ số | Giá trị |
|---|---:|
| Rows / `poi_id` unique | 186,322 / 186,322 |
| Duplicate `poi_id` | 0 |
| Empty name | 0 |
| Missing ranking point / invalid lat-lon | 0 / 0 |
| Outside VN bbox | 31 (0.017%) |
| OSM node / way | 122,389 / 63,933 |

Universe đánh giá Stage 1 = toàn bộ `search_documents.parquet` (cùng N). Gold 180 là **tập target chấm điểm**, không phải toàn corpus.

---

## 2. Phân bố địa lý (top tỉnh/TP)

| province | n | % |
|---|---:|---:|
| TP. Hồ Chí Minh | 53,186 | 28.5% |
| Hà Nội | 46,692 | 25.1% |
| Đà Nẵng | 14,598 | 7.8% |
| Bắc Ninh | 10,396 | 5.6% |
| Lâm Đồng | 6,751 | 3.6% |
| Cần Thơ | 5,594 | 3.0% |
| Đồng Nai | 5,266 | 2.8% |
| Hải Phòng | 4,555 | 2.4% |
| … | … | … |
| (unknown province) | 333 | 0.18% |

**Insight:** ~54% corpus nằm ở HCM + Hà Nội. Gold cố ý cân 19 tỉnh (~1/3 Bắc–Trung–Nam) để screening model không chỉ “học hai thành phố lớn”.

---

## 3. Category (token đầu, top)

| category | n |
|---|---:|
| `address=` | 51,563 |
| `public_transport=platform` | 15,304 |
| `amenity=restaurant` | 10,704 |
| `amenity=cafe` | 8,255 |
| `amenity=school` | 7,858 |
| `amenity=place_of_worship` | 6,209 |
| `shop=convenience` | 6,128 |
| `tourism=hotel` | 5,664 |
| `building=yes` / apartments | ~6,900 |
| … | … |

**Insight:** lớp `address=` + platform giao thông lớn → lexical/dense dễ “bắt” số nhà/trạm nếu query có tín hiệu địa chỉ; đồng thời tăng collision cho query ngắn.

---

## 4. Ngôn ngữ tên (heuristic)

| bucket | n | % |
|---|---:|---:|
| `vi_diacritic` | 134,129 | 72.0% |
| `latin_no_vi_diacritic` | 48,722 | 26.1% |
| `has_digit` | 3,310 | 1.8% |
| other | 161 | <0.1% |

Tên không dấu / Latin chiếm ~1/4 — khớp nhu cầu slice `strip_diacritics` / brand EN trên gold.

---

## 5. Brand, alias, mã

| metric | n | rate |
|---|---:|---:|
| with_brand | 8,952 | 4.8% |
| with_alias | 14,216 | 7.6% |
| with_ref | 625 | 0.3% |

Brand lớn (folded name) tạo **cụm ambiguity** rất nặng: WinMart+, Petrolimex, BIDV, Agribank, Highlands, Circle K, Bach Hoa Xanh… (xem bảng same-name §6). Đây là lý do gold có stratum `brand_branch` + multi-positive sparse.

---

## 6. Same-name ambiguity

| metric | giá trị |
|---|---|
| Distinct folded names | 147,946 |
| Folded groups size ≥ 2 | 13,312 (9.0% tên) |
| POI nằm trong group ≥ 2 | **51,688 (27.7%)** |
| Folded×province groups ≥ 2 | 11,913 |

**Top ambiguous (global):** WinMart+ (1221), Petrolimex (1119), “a” (664 junk), BIDV (511), Agribank (445), “sua xe” (435), Vietcombank (404), Highlands (258), …

**Hệ quả Stage 1:** query chỉ brand/generic **không** thể unique-target một chi nhánh; qrels phải multi-positive hoặc bắt buộc alias có area/street trong text.

---

## 7. Near-duplicate (heuristic)

| heuristic | count |
|---|---:|
| Same-fold pairs ≤ 80 m (group size ≤ 80) | 8,823 |
| Trong đó node–way | 1,508 |

Near-dup = **ứng viên dedup**, chưa collapse trong corpus hiện tại. Business layer (W5) cần xử lý; Stage 1 gold cố tránh chọn target trong cụm node–way bẩn khi review.

---

## 8. Địa chỉ & hành chính

| metric | n | rate |
|---|---:|---:|
| `address_status=direct` | 88,260 | 47.4% |
| `address_status` missing | 98,062 | 52.6% |
| housenumber ∧ (street∨place) | 77,190 | 41.4% |
| subdistrict missing | 490 | 0.26% |
| province unknown | 333 | 0.18% |

**Gold gate:** mọi target bắt buộc `address_status=direct` + housenumber + street + province + subdistrict — subset “sạch” để canonical/address variants có căn cứ fact.

---

## 9. Gold target overlay (180)

| Stratum | n |
|---|---:|
| named_clear | 36 |
| brand_branch | 36 (gồm 8 Vincom) |
| address_street_building | 28 |
| building_code | 22 |
| category_local | 20 |
| explicit_area_cross_region | 20 |
| code_transit_landmark | 18 |

Địa lý gold: **19** tỉnh/TP · Bắc 64 · Nam 60 · Trung & TN 56.

Chi tiết chọn mẫu: `data/vietnam/gold_stage1_v1/README.md`.

---

## 10. Kết luận EDA POI → ưu tiên W2+

1. **Ambiguity cùng tên** ảnh hưởng >1/4 POI — Stage 1 cần Recall sâu; disambiguation geo thuộc Stage 2.
2. **Address coverage ~47% direct** — trần chất lượng address search; gold chỉ đo trên subset đủ địa chỉ.
3. **Near-dup OSM** — đừng nhầm “model sai” với “hai bản ghi một thực thể”.
4. **Brand mỏng trong field `brand` (4.8%)** nhưng same-name brand rất lớn — dựa folded name + stratum, không chỉ cột brand.
5. Screening model trên gold 180 × corpus 186k là đúng hướng W2; đừng suy production accuracy từ gold alone.
