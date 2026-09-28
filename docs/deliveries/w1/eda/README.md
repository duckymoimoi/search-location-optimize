# EDA dataset hiện hành — 2026-09-28

EDA mới được tính trực tiếp trên **40 bảng Parquet** trong `data/vietnam`, bỏ staging; bao gồm nguồn hiện hành, view huấn luyện và các pack diagnostic để so sánh. Không cộng tổng số dòng giữa các bảng vì nhiều bảng là view hoặc phiên bản của cùng dữ liệu. Gold v2.1/v2.2 có cùng payload, không phải hai tập độc lập.

Nguồn số đầy đủ: [dataset_eda.json](dataset_eda.json), gồm path, SHA-256, số dòng, cột, null/blank, cardinality, phân bố và audit. Runner: [report_current_datasets.py](../../../../tools/report_current_datasets.py). Báo cáo thống kê corpus v3, Gold hiện hành và các view dùng cho nghiên cứu; không cộng các view cùng nguồn thành số query độc lập.

## 1. Inventory và vai trò

| Bộ | Quy mô hiện tại | Vai trò / lưu ý |
|---|---:|---|
| Corpus v3 | 179.209 POI, 179.209 search documents | Cùng ID set; không có POI ID trùng |
| Admin v1 | 8.785 catalog, 8.632 geometry | 153 catalog thiếu geometry; không coi mọi polygon đều hợp lệ |
| Target pool “20k” | 19.891 POI/case | Tên thư mục là nhãn lịch sử, không phải số dòng thực tế |
| Query POI v6 | 36.000 query / 6.000 case | 6.000 CLEAN +6.000 ALIAS +24.000 COMPOUND theo family |
| Gold POI v2.2 | 200 POI, 800 query, 820 qrel, 200 prefix | Tái phát hành từ payload v2.1; regression đã phơi nhiễm, không phải holdout mới |
| Gold brand v1 | 70 family, 248 query, 6.610 qrel | Family test; verifier locked PASS |
| Brand query v3 | 1.156 query / 320 family | Train 782, dev 126, test 248 query; family 215/35/70 |
| Brand membership v3 | 12.714 rows; 11.124 accepted | 10.929 accepted destination IDs duy nhất, đều trong corpus |
| Brand lookup v3 | 5.268 match rows; 921 group summaries | Lookup là alias/group metadata, không phải qrel theo context |
| POI+brand view v1 | 36.908 query | 36.000 POI +908 brand; train 36.782, dev 126 |
| Hardneg 6k clean | 35.994 query; 231.608 pairs | Train 32.394 / dev 3.600, dùng cho audit baseline dev-lock |

Số dòng view relation có thể hàng triệu vì một query có nhiều relation; không diễn giải thành hàng triệu query độc lập. Chi tiết từng bảng nằm trong JSON.

## 2. Corpus, địa lý và độ đầy đủ

- Corpus và search documents khớp ID set 179.209; tất cả destination searchable. Ranking point không thiếu và nằm trong miền lat/lon hợp lệ. Kiểm tra này không chứng minh tọa độ là lối vào đón khách chính xác.
- 93.170 POI có `address_status=missing` (51,99%), 86.039 có địa chỉ direct. `address_text` không rỗng không đồng nghĩa địa chỉ nguồn đầy đủ: context/fallback có thể tạo text.
- 40.238 POI thuộc nhóm tên trùng sau NFKC/casefold/chuẩn hóa khoảng trắng (22,45%). Đây là ambiguity, không phải kết luận duplicate cần xóa. Các tên phổ biến gồm WinMart+, Petrolimex và ngân hàng; ranking theo chi nhánh/context có giá trị thực tế.
- TP.HCM 50.206 POI, Hà Nội 45.402; cộng 53,35% corpus. Báo cáo segment thành phố/head-tail trước khi suy rộng kết quả toàn quốc. Các tên tỉnh/thành giữ nguyên nhãn trong snapshot, không phải xác nhận đơn vị hành chính hiện nay.
- `brand` thiếu ở 170.594 POI; `branch_id` null toàn bộ corpus. Không dùng null brand như negative brand membership; dùng sidecar đã review và ghi missing feature.
- Access enrichment có `routing_point_status=unknown` và `pickup_access_verified=False` ở toàn bộ 179.209 POI. Stage 2 có thể thử khoảng cách hình học nhưng chưa có nhãn xác nhận khả năng đón khách/road access.
- Admin catalog: 8.616 `ok`, 149 `unclosed_rings:1`, 3 `unclosed_rings:2`, 1 `no_outer_ways`, 9 `ok_outside_vn_bbox`, 7 `ok_partial`. 153 thiếu geometry; không biến missing geometry thành distance=0.

## 3. Query và representativeness

| Bộ query | Median / p95 ký tự | Median / p95 token | Trùng text chuẩn hóa |
|---|---:|---:|---:|
| POI v6 | 27 / 50 | 6 / 11 | 0 |
| Gold POI v2.2 | 28 / 41 | 6 / 9 | 0 |
| Brand v3 | 14 / 25,25 | 3 / 5 | 0 |
| Gold brand v1 | 13 / 22 | 3 / 4 | 0 |

Chuẩn hóa dùng NFKC + casefold + collapse whitespace, giữ dấu; không suy ra không collision theo mọi tokenizer hoặc cách bỏ dấu. Gold POI có 200 clean, 591 compound, 9 challenge; không có mild. Đây là bộ đánh giá nhiễu có chủ đích, không phải phân bố traffic thật. Strata Gold: brand_branch 152, named_clear 152, address_street_building 128, building_code 104, category_local 92, explicit_area_cross_region 92, code_transit_landmark 80 query.

Gold brand gồm 164 clean, 64 mild, 20 compound; namespace retail 96, hotel 39, fuel 30, bank 22, ATM 19, restaurant 16, supermarket 14, cafe 12. Tập nhỏ ở một số namespace nên metric theo slice có độ bất định lớn. Query-only không đủ nhãn lựa chọn chi nhánh theo vị trí/người dùng/thời gian.

POI v6 có `review_status=authored` toàn bộ 36.000 dòng; không đổi nghĩa thành đã được người độc lập duyệt. Brand v3 có 1.154 authored và 2 needs_review. Gold POI/brand giữ inherited accepted labels; bản tái phát hành không tạo thêm independent review.

## 4. Split và chất lượng training pack hiện hành

Pack 6k clean: 32.394 train /3.600 dev query; 37.446 positive, 194.060 negative và 102 ignore pairs. Intended POI và normalized text không overlap train/dev. Gold positive IDs không xuất hiện trong pairs; pair IDs ngoài corpus và pair query ngoài train split đều bằng 0. Các kiểm tra này áp dụng file được hash trong JSON; khi chọn checkpoint phải đối chiếu đúng manifest run.

Brand chia 215/35/70 family train/dev/test, không lặp assignment; toàn bộ 70 Gold family thuộc test. POI+brand view có 36.000 POI query ở train và chỉ 126 brand query ở dev. Cần POI dev riêng theo case/entity trước khi model selection chung.

## 5. Evaluation dataset hiện hành

[Gold POI v2.2](../../../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_2/README.md) có 200 POI/800 query/820 qrel/200 prefix. Validation PASS cho schema, cardinality, searchable membership, qrel consistency, prefix bounds và train-target overlap 0; tái dựng ở hai thư mục cho file giống từng byte.

Đây là tập regression đã phơi nhiễm, không phải holdout mới hoặc bộ nhãn vừa được review độc lập. Verifier tính toàn vẹn không thay thế kiểm chứng factuality. Gold brand v1 có 70 family/248 query/6.610 qrel và locked verifier PASS.

## 6. Quyết định từ EDA

1. Dùng v2.2 làm regression POI hiện hành; không tăng sample size bằng các bản sao cùng payload.
2. Dùng pack clean và manifest đúng run cho thử nghiệm tiếp theo. Chưa train mới trong đợt này.
3. Trước Stage 2, đóng băng candidate pool và audit context/impression/selection thật; dữ liệu đang EDA chưa chứng minh có log hành vi thật đủ train personalization.
4. Xử lý nhánh tên trùng và brand namespace; không xóa lexical. Đo thêm thiếu địa chỉ, head/tail, province, query length và category để tránh điểm overall che lỗi.
5. Giữ missing feature rõ ràng cho geo/access/time/behavior; không suy diễn feature không có từ nhãn query-only.
6. Holdout độc lập và load SLA dài hạn vẫn còn pending trước release sản phẩm. Structural EDA không thay thế factuality review, false-negative audit thủ công hoặc thử nghiệm E2E.

## Tái lập

```powershell
python tools/report_current_datasets.py --out artifacts/results/dataset_eda_new
python tools/reissue_gold_stage1_v22.py verify
```

Runner EDA dùng toàn bộ rows, stream bảng lớn; categorical JSON chỉ giữ top 20 nhưng lưu distinct count. SHA-256 khóa từng file và runner. Một số pack diagnostic được giữ local/ignore khỏi Git: fresh clone phải khôi phục đúng artifact để tái tạo đủ 40 bảng; nếu thiếu thì báo cáo mới sẽ có scope nhỏ hơn, không được gọi là cùng snapshot.
