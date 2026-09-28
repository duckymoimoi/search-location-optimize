# W4 — Ranking Stage 2 và cải tiến theo lỗi

Cập nhật: 2026-09-28. **Chưa có kết quả nghiệm thu Stage 2.** Đây là phiếu đầu vào/công việc bàn giao, không phải báo cáo model đã train. Người nhận/duyệt: chưa xác nhận. Yêu cầu: W4 [kế hoạch](../SEARCH_2.0_TONG_HOP_TASK.md), §4.2/bước 4 [SEARCH 2.0](../../specs/search2.0.md).

## 1. Mục tiêu và input

Xếp lại candidate Stage 1 theo context ride-hailing, chứng minh lợi ích từng nhóm feature. Input hiện có: hai pool S1-A/S1-B đã kiểm tra và qrels query-only. Input còn thiếu: inventory và provenance log impression/selection thật, context tại thời điểm request, split theo thời gian và nhãn context để kiểm định personalization.

## 2. Output phải bàn giao

| Output | Trạng thái | Điều kiện nghiệm thu |
|---|---|---|
| Ranking model hoặc baseline rules có version | Chưa có final candidate W4 | Cùng candidate IDs đầu vào/đầu ra, feature schema và missing policy rõ |
| Feature ablation | Chưa chạy đủ | Retrieval-order → text-only → +Geo → +Time → +Behavior → Full; cùng pool/split |
| Error analysis | Có lỗi từ W3 để khởi động | Mẫu rescue/harm mới theo slice, taxonomy và root cause |
| Improvement experiments | Chưa có kết quả W4 | Mỗi thay đổi có Observation/Hypothesis/Experiment/Result/Decision |
| E2E benchmark/final model candidate | Chưa có | Đo quality + latency trên bundle đóng băng, so retrieval-only và holdout phù hợp |

Heuristic geo/history demo hiện có chỉ là baseline chức năng; không phải learned ranker hoặc chứng cứ train bằng hành vi thật.

## 3. Quy trình thực hiện đã chốt

[Quy trình thực hiện đã chốt](01_IMPLEMENTATION_PROTOCOL.md)

## 4. Giả thuyết mở và acceptance

[Giả thuyết mở và acceptance](02_EXPERIMENTS_AND_ACCEPTANCE.md)

## 5. Bàn giao W5 và việc còn lại

Chỉ bàn giao final ranking candidate khi có model/rules version, feature snapshot, ablation, error report, inference entrypoint, fallback retrieval-only và latency mới. Ranking/evaluation phụ trách G4; data phụ trách G1. W5 có thể phát triển service scaffold bằng baseline, nhưng không gọi scaffold là pipeline Stage 2 đã nghiệm thu.
