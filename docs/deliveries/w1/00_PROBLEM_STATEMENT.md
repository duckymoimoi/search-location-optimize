# W1 — Định nghĩa bài toán

Cập nhật 2026-09-28. Sản phẩm tìm điểm đến ride-hailing trên corpus 179.209 POI.

## Bài toán cần giải

Stage 1 biến query text thành candidate chứa ít nhất một địa điểm phù hợp accepted set. Stage 2 xếp lại candidate theo context hợp lệ: vị trí, thời điểm, lựa chọn trước đó và chất lượng POI. Tầng kết quả xử lý hiển thị, chọn điểm đến, dedup và fallback. Mỗi tầng được đánh giá riêng để xác định đúng nguồn lỗi.

“Tìm đúng” ở truy vấn một thực thể là tìm được intended POI hoặc entity-equivalent được qrels chấp nhận. Với bare brand, nhiều chi nhánh có thể relevant; không tự chọn một chi nhánh làm đáp án duy nhất. Với số nhà/mã, không bỏ qua phần số làm thay đổi intent. Khả năng đón xe không được suy từ việc POI có tọa độ.

## Phạm vi hiện tại

- Corpus v3, query POI v6, brand v3, Gold POI v2.2 và Gold brand v1 phục vụ nghiên cứu offline.
- Có retriever 6k dev-lock, candidate trace và API thử nghiệm; chưa có ranker Stage 2 đã train/nghiệm thu.
- Gold POI v2.2 là regression đã phơi nhiễm, không phải holdout mới. Không có log hành vi thật đủ bằng chứng để kết luận conversion/personalization.

## Định nghĩa thành công

| Tầng | Thành công cần kiểm tra |
|---|---|
| Dữ liệu | ID/qrels/corpus nhất quán, missingness rõ, không dùng pack có leakage |
| Retrieval | Có accepted POI trong pool, đủ coverage các positives; breakdown theo intent |
| Ranking | Cải thiện thứ tự trên cùng pool và nhãn context; không đánh đổi correctness để ưu tiên khoảng cách |
| Dịch vụ | Trả kết quả/selection hợp lệ, độ trễ và lỗi được đo, fallback có kiểm thử |
| Kinh doanh | Cần log selection/booking và định nghĩa metric trước khi kết luận |

W2 nhận problem statement, taxonomy và các giới hạn dữ liệu này để khóa metric và baseline.
