# W4 — Giả thuyết mở và acceptance

[README](README.md) · Cập nhật: 2026-09-28.

| Observation từ W3 | Hypothesis cần kiểm tra | Experiment dự kiến | Result/Decision hiện tại |
|---|---|---|---|
| S1-B coverage cao nhưng hạng đầu kém | Text reranker khai thác pool tốt hơn RRF raw | Ma trận 2 pool × retrieval-order/text ranker | Chưa chạy; chưa chọn model |
| Tên/brand có nhiều chi nhánh | Geo giúp trong cohort đúng tên/intent | Text-only vs +Geo với origin thật và missing bucket | Chưa có quality evidence W4 |
| Thiếu lịch sử người dùng thật | Behavior demo không chứng minh personalization | Audit log, split thời gian rồi mới +Behavior | G1 còn mở |

Không suy distance=0 khi thiếu origin; không dùng khoảng cách tự tạo nhãn rồi coi là đánh giá độc lập. Không phát sinh candidate mới trong ranker. Mục tiêu SLA E2E 20 QPS/p95 ≤150 ms vẫn là đề xuất chung, không cộng thêm 150 ms riêng cho ranking.
