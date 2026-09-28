# W1 — EDA corpus POI

Cập nhật 2026-09-28. Nguồn: [thống kê toàn bảng và hash](eda/dataset_eda.json).

| Chỉ tiêu | Giá trị |
|---|---:|
| Corpus và search documents | 179.209 mỗi bảng; ID set khớp |
| POI ID duy nhất | 179.209 |
| Ranking point thiếu/ngoài miền lat-lon | 0 |
| Địa chỉ direct | 86.039 |
| Address status missing | 93.170 (51,99%) |
| POI thuộc nhóm tên trùng chuẩn hóa | 40.238 (22,45%) |
| TP.HCM / Hà Nội | 50.206 /45.402; tổng 53,35% |
| Brand null | 170.594 |
| Branch ID null | 179.209 |
| Pickup access verified | 0 |
| Admin catalog /geometry | 8.785 /8.632 |

Tên trùng không đồng nghĩa entity trùng; WinMart+, Petrolimex và ngân hàng là các nhóm cần phân biệt chi nhánh. Alias/member sidecar cần được dùng cùng missing flag vì trường brand trong corpus thường thiếu. `address_text` có giá trị không chứng minh có địa chỉ nguồn đầy đủ.

## Chất lượng địa lý và điểm đón

Admin có 153 catalog thiếu geometry; còn polygon partial/outside bbox. Tọa độ hợp lệ chỉ bảo đảm miền giá trị, không bảo đảm đúng entrance hoặc road access. Toàn bộ routing-point enrichment đang unknown. Stage 2 phải giữ missing bucket, không gán khoảng cách 0 khi thiếu origin/geometry.

## Quyết định từ EDA

1. Đo theo địa lý/head-tail/category vì hai thành phố chiếm hơn nửa corpus.
2. Giữ name ambiguity, thiếu địa chỉ và namespace làm slice bắt buộc.
3. Không xóa POI chỉ vì tên trùng; dedup cần entity/geo evidence.
4. Chưa có phép đo freshness/provider coverage và mật độ chi tiết đủ để kết luận chất lượng cập nhật bản đồ; ghi đây là phần EDA còn thiếu.

Chi tiết phân bố top category/province, null và blank nằm trong JSON; [EDA tổng hợp](eda/README.md) cung cấp cách tái lập.
