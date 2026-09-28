# W2 — Metric specification và evaluation protocol

Cập nhật 2026-09-28. Corpus 179.209 POI; Gold POI active v2.2 (800 query), Gold brand v1 (248 query/70 family). Dev chọn cấu hình: 3.600 POI query và 126 brand query/35 family. Gold POI là regression đã phơi nhiễm; cần holdout mới cho kiểm định độc lập.

| Metric | Định nghĩa và cách dùng |
|---|---|
| Hit@K | Có ít nhất một accepted ID trong K kết quả; primary coverage khi bàn giao pool top 100 |
| Coverage@K | Số accepted ID lấy được /tổng accepted ID; khác Hit với multi-positive |
| MRR@K | Reciprocal rank accepted đầu tiên, bằng 0 nếu không có hit trong K |
| nDCG@K | Cần công bố relevance gain/discount và nguồn graded labels; chưa có ablation ranker Stage 2 |
| FHC/SHC/PrefixAUC | Mẫu số phải ghi theo group-ready/entity-ready và số checkpoint đủ cửa sổ |
| Geo/namespace | Sai loại bank/ATM, distance/error radius trên nhãn context hợp lệ; query-only chưa đủ |
| Business | Click/selection/booking/abandonment cần log thật; hiện chưa đo |
| System | Client p50/p95/p99, arrival rate/QPS, error/timeout, queue và route; không cộng p95 stage |

POI headline theo query, CI theo case; brand headline macro family, CI theo family. Dev/regression/holdout không trộn mẫu số. Timeout/failure phải được báo trên toàn workload, không loại để điểm đẹp.

## Thiết kế phép đo

1. Pin code, model, tokenizer, passage builder, corpus, vectors, ID map, index, normalizer, retrieval/fusion/ranking flags và k.
2. Thay một yếu tố khi quy nguyên nhân. So ranker trên cùng candidate IDs; đổi pool là experiment riêng.
3. Chọn trên dev, giữ related variants trong cùng split. Mở holdout sau lock; dùng lại thì gọi regression.
4. Báo paired rescue/harm, delta và CI cùng slice query type/length, city, head-tail, category, popularity, language, ambiguity. Thiếu nhãn ghi rõ.
5. Response top 10; diagnostic pool 100. Không suy Hit@100 từ response top 10 hoặc budget 50.

Hiện có characterization closed-loop và các ablation top 100; chưa có kiểm định SLA open-loop/soak. [SLA đề xuất](../../operations/RETRIEVAL_DECISIONS_AND_PILOT_SLA_2026_09_28.md) là mục tiêu cần kiểm tra, không phải kết quả đã đạt.
