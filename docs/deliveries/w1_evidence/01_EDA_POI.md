> EDA snapshot l?ch s?. Xem [EDA dataset hi?n h?nh 2026-09-28](../dataset_eda_20260928/README.md) cho corpus v3, Gold t?i ph?t h?nh v? training packs.

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

---

## 11. Cleaning audit bổ sung 23/09/2026

Audit mới trên cùng `pois_core.parquet` và cùng SHA-256 nguồn
`e5d75c4783f27d86767ba5d0d46b2449dca19f709377b964672089b5226b658d`.
[Báo cáo đầy đủ](../../../data/vietnam/poi_corpus_v1/eda/poi_cleaning_audit.md)
có code tái lập, JSON và danh sách ứng viên Parquet.

| Dấu hiệu | Quy mô | Diễn giải |
|---|---:|---|
| Tên đúng một ký tự | 1.122 POI | 703 có số nhà + street/place; cần xem vai trò address-only trước khi loại row khỏi index |
| Cùng folded name + full address, ≤50 m | 1.920 cặp / 2.094 POI | 277 cặp node–way; 549 cặp dùng street key 1–2 ký tự nên cần kiểm tra lại khóa địa chỉ |
| Cùng full address, >1 km | 2.044 cặp / 495 POI | 1.966 cặp dùng street key dài 1–2 ký tự; còn 78 cặp cần ưu tiên review địa chỉ/tọa độ |
| Cùng folded name, ≤50 m bất kể địa chỉ | 12.049 cặp | 4.690 cặp có tên chỉ 1–2 ký tự; còn có thể gồm entrance/platform/chi nhánh |
| Trùng ranking point | 40 nhóm | 16 cặp còn trùng tên |

Các flag khác: 14 placeholder name, 766 generic name, 633 alias trùng name
sau fold, 31 tọa độ ngoài bbox Việt Nam và 11.070 row `address_status=direct`
không có đủ cặp số nhà + street/place. Những số này là tập review có thể chồng
lấp, không cộng để suy số POI cần xóa.

Overlay lên target hiện tại: Gold v1 có 5/180 POI thuộc ứng viên trùng gần mạnh;
train 20k có 223/20.000 và checkpoint 500 có 5/500. Chưa thay đổi các target
hoặc qrels đã khóa. Khi xây Gold v2 và corpus sạch mới, kiểm tra entity
equivalence và migration map trước khi dùng những target này.

Theo quyết định clean corpus, bản v2 đã thay 82 tên một ký tự bằng địa chỉ
(74 còn sau dedup), bỏ 1.040 row thiếu địa chỉ dùng được và gộp 1.147 row
trùng gần. Có [migration map](../../../data/vietnam/poi_corpus_v2/poi_id_migration.parquet)
cho mọi ID v1. Trong target đã khóa, Gold v1 có 2 ID bị gộp, train 20k có 46,
checkpoint 500 không có ID bị xóa. Đây là số tác động thực sau clean, khác
số row nằm trong hàng đợi review nêu ở trên.
