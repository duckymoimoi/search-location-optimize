# SEARCH 2.0 — Evidence tuần 2: Design & Baseline

**Snapshot:** 2026-09-26 · corpus v3 · Stage 1 POI/entity + brand.
**Nguồn yêu cầu:** [`SEARCH_2.0_TONG_HOP_TASK.md`](../SEARCH_2.0_TONG_HOP_TASK.md), hàng W2.
**Kết luận nghiệm thu:** đủ mốc lexical/hybrid và evaluation set đã khóa cho
Stage 1 text; **chưa đủ** để tuyên bố hoàn tất mọi baseline A/B/C/D, geo,
business và system metrics trên cùng Gold.

| Output W2 | Evidence | Trạng thái |
|---|---|---|
| Metric specification | [`01_METRICS_AND_EVAL.md`](01_METRICS_AND_EVAL.md) | Đã định nghĩa; chỉ tiêu cần log thật ghi `chưa đo` |
| Evaluation dataset | Gold POI v2.1 + Gold brand v1, manifest/lock trong `data/vietnam/stage1_eval_suite_v2/` | Đã khóa, không dùng để train |
| Baseline benchmark + error analysis | [`02_BASELINE_AND_FAILURES.md`](02_BASELINE_AND_FAILURES.md) | Lexical raw và hybrid cùng corpus v3; dense-only chưa replay cùng Gold |
| Search architecture + experiment protocol | [`03_ARCHITECTURE_AND_PROTOCOL.md`](03_ARCHITECTURE_AND_PROTOCOL.md) | As-built + quy tắc so sánh W3 |
| Local artifact lifecycle | [`04_LOCAL_CLEANUP.md`](04_LOCAL_CLEANUP.md) | Danh sách giữ/dọn và kiểm tra hồi phục |

Machine evidence ở `artifacts/results/` là **local/derived**, không phải dataset
được commit. Các số chính, SHA-256 và giới hạn diễn giải được ghi ngay trong
package này; không cần chép full corpus, per-query CSV hay embedding vào docs.
W1 evidence là snapshot lịch sử, không sửa số liệu cũ theo corpus v3.

Đây là synthetic/manual evaluation, không phải phân bố traffic thực hoặc kết
quả booking. Không có click/booking log hợp lệ để kết luận business success.
