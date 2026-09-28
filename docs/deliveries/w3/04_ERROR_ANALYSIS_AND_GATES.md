# W3 — Error analysis, per-segment và gate

## Lỗi còn lại

| Quan sát | Nguyên nhân/giả thuyết | Quyết định |
|---|---|---|
| Dense-first thiếu coverage POI lạnh | Candidate generation chưa đủ cho tên hiếm | Giữ lexical/S1-B; nếu target vắng pool phải sửa Stage 1 |
| Hybrid raw có pool tốt nhưng hạng đầu thấp | Fusion chưa phản ánh đúng relevance | Stage 2 thử ranker trên pool cố định |
| ATM/chi nhánh sai namespace | Alias/family chưa đủ xác định intent | Tắt name promotion; test namespace theo qrels |
| Broad name/address rerank hại POI dev | Heuristic đưa tín hiệu yếu lên cao | Raw ranking baseline; thêm feature qua ablation |
| Missing origin/context | Không đủ dữ liệu quyết định chi nhánh | Missing bucket; không gán 0 hoặc invent behavior |

## Coverage của báo cáo segment

| Chiều W3 yêu cầu | Evidence hiện có / giới hạn |
|---|---|
| Query type/role | Có role và strata; regression checkpoint q01/q02/q03/q04 Hit@1: 99,0/95,0/88,5/96,5% |
| Query length/prefix | Có EDA và prefix-ready protocol; cần full bảng đồng nhất final config |
| City, head/tail, category | Có phân bố dataset; chưa đủ quality breakdown cùng final bundle |
| Popularity | Chưa có nguồn hành vi thật đủ tin cậy |
| Language/ambiguity | Có taxonomy, brand/entity stress; chưa đủ mọi nhãn/slice độc lập |
| Geo/time/behavior | Thuộc ranking với context; chưa có quality ablation Stage 2 |

Không dùng EDA distribution thay quality breakdown. Không dùng full-query Hit làm kết luận autocomplete; prefix phải khóa readiness và denominator.

## Điều kiện chốt

Đủ bàn giao baseline nghiên cứu với candidate trace/hash và live parity. Chưa đủ ký toàn bộ TC1/production: independent holdout, negative adjudication, segment đầy đủ và namespace/numeric/geo/load gates còn mở. Gold v2.2 verifier PASS xác nhận reissue integrity, không cấp independent holdout status.
