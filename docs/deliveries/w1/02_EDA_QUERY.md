# W1 — EDA query và training views

Cập nhật 2026-09-28. [Nguồn số và hash](eda/dataset_eda.json).

| Dataset | Quy mô | Median/p95 ký tự | Đặc điểm |
|---|---:|---:|---|
| POI v6 | 36.000 query/6.000 case | 27/50 | Family: 6.000 CLEAN, 6.000 ALIAS, 24.000 COMPOUND |
| Gold POI v2.2 | 800 query/200 case | 28/41 | 200 clean, 591 compound, 9 challenge |
| Brand v3 | 1.156 query/320 family | 14/25,25 | Train/dev/test query: 782/126/248 |
| Gold brand v1 | 248 query/70 family | 13/22 | 164 clean, 64 mild, 20 compound |

Không có duplicate query text sau NFKC/casefold/collapse whitespace trong bốn bảng trên. Chuẩn hóa giữ dấu, nên không suy ra không collision theo mọi tokenizer/cách bỏ dấu.

## Phân bố và giới hạn

Gold POI chia đều q01–q04, mỗi role 200 query. Strata: brand_branch 152, named_clear 152, address_street_building 128, building_code 104, category_local 92, explicit_area_cross_region 92, code_transit_landmark 80. Không có mild trong Gold POI; bộ này đo nhiễu có chủ đích, không đại diện traffic thật.

Gold brand: retail 96, hotel 39, fuel 30, bank 22, ATM 19, restaurant 16, supermarket 14, cafe 12. Một số slice nhỏ, cần CI và không suy rộng từ vài query.

## Readiness huấn luyện

- Pack 6k clean: 32.394 train/3.600 dev; intended entity và normalized text không overlap train/dev, Gold positives không xuất hiện trong pairs theo audit.
- POI+brand view có 36.908 query nhưng dev chỉ gồm 126 brand query. Phải bổ sung POI dev theo case/entity trước khi dùng view để chọn model chung.
- POI v6 có 36.000 authored rows; brand v3 còn 2 needs_review. Authored không đồng nghĩa independent review.
- Chưa có nguồn log impression/selection/booking thật được xác nhận cho Stage 2. Không dùng query authored để kết luận click rate hay hành vi người dùng.

W2 nhận strata/query-length distributions để định nghĩa slice. W4 cần bổ sung context và time split, không lấy Gold query-only làm bằng chứng personalization.
