# W1 — Query/POI taxonomy

Cập nhật 2026-09-28. Taxonomy dùng thống nhất khi authoring, chia tập, phân tích lỗi và báo cáo metric.

| Đơn vị | Ý nghĩa |
|---|---|
| case_id /query_family_id | Nhóm query cùng intent/target; giữ cùng split |
| query_id | Một query đánh giá cụ thể |
| intended_poi_id | Địa điểm chính của query entity |
| acceptable_poi_ids /qrel_set_id | Tập đáp án được chấp nhận cho chính query |
| brand_family_id /namespace | Chuỗi và loại intent như bank/ATM; không đồng nhất family với chi nhánh |
| entity_group_id | Nhóm entity dùng đánh giá/dedup theo evidence |

## Các chiều phải báo cáo

| Chiều | Nhóm cần phân biệt |
|---|---|
| Intent | Exact name, partial, alias, address/street, landmark, brand, category, name+address/area, code |
| Biến thể | Không/sai dấu, Telex/VNI, typo, ghép/tách từ, abbreviation, compound |
| POI stratum | named_clear, brand_branch, address_street_building, building_code, category_local, explicit_area_cross_region, code_transit_landmark |
| Ambiguity | Một entity; nhiều entity-equivalent; nhiều chi nhánh; thiếu thông tin để chọn |
| Độ dài | Số ký tự/token và mốc prefix-ready; khóa bucket trước so sánh |
| Context | Có/thiếu origin; near/far; user mới/cũ khi có log hợp lệ |
| Phân bố | City/region, category, head-tail, language, popularity có nguồn |

Giữ namespace và số/mã làm ràng buộc intent. Cùng tên nhưng khác chi nhánh không tự là equivalent. Không gán popularity hoặc head-tail từ cảm giác; phải công bố nguồn và bucket. Thiếu nhãn được ghi missing, không giả định nhóm mặc định.

Các nhóm chưa có đủ dữ liệu/nhãn trong benchmark phải ghi chưa đo. Thống kê strata hiện tại ở [EDA query](02_EDA_QUERY.md); [chuẩn query](../../specs/SEARCH_2.0_STAGE1_QUERY_VARIANT_STANDARD.md) quy định authoring.
