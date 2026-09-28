# SEARCH 2.0 — Bàn giao hiện hành theo tuần

Cập nhật: 2026-09-28. Mỗi thư mục tuần chứa README bàn giao và tài liệu chi tiết đúng output yêu cầu. Tài liệu chỉ mô tả cấu hình, dữ liệu, kết quả và việc còn thiếu hiện tại.

Yêu cầu: [SEARCH 2.0](../specs/search2.0.md), [kế hoạch W1–W6](SEARCH_2.0_TONG_HOP_TASK.md). W3 thực hiện retriever Stage 1; W4 thực hiện ranking Stage 2.

| Tuần | Tài liệu | Trạng thái |
|---|---|---|
| W1 | [Dữ liệu và bài toán](w1/README.md) | EDA, taxonomy, DQ và problem statement đã có; behavior log thật còn thiếu. |
| W2 | [Thiết kế và baseline](w2/README.md) | Baseline text và protocol đã có; chưa đủ geo/popularity/business evaluation. |
| W3 | [Train retrieval Stage 1](w3/README.md) | Candidate/hash/live parity đã kiểm tra; holdout độc lập và các gate còn mở. |
| W4 | [Ranking Stage 2](w4/README.md) | Chưa train/triển khai ranker; cần context audit và feature ablation. |
| W5 | [Service và E2E](w5/README.md) | API/index/FE, smoke và characterization đã có; final ranker/fault/load gates còn thiếu. |
| W6 | [Nghiệm thu cuối](w6/README.md) | Chưa chạy đủ tám scenario trên final bundle; chưa nghiệm thu. |

## Điều kiện nghiệm thu

| Gate | Điều kiện đóng | Vai trò phụ trách |
|---|---|---|
| G1 | Log/context/selection thật có provenance và time split | Data + annotation |
| G2 | Holdout độc lập khóa trước model selection | Evaluation |
| G3 | Baseline/segment đủ chiều, cùng dataset và version | Retrieval + evaluation |
| G4 | Ranking cải thiện cùng candidate pool; có feature ablation | Ranking |
| G5 | Rebuild, fault injection, rollback và tải dài có kết quả | Serving |
| G6 | Tám scenario trên final bundle và biên bản duyệt | Integration + người nghiệm thu |

Người nhận/duyệt chưa xác nhận. Vai trò là trách nhiệm đề xuất, không phải chữ ký nghiệm thu. Thiếu dữ liệu hoặc chưa chạy được ghi `chưa đo`, không thay bằng 0 hoặc claim pass.

## Dữ liệu và cấu hình dùng chung

Corpus v3: 179.209 POI. Gold POI v2.2: 800 query/820 qrel, regression đã phơi nhiễm; Gold brand v1: 248 query/70 family. Checkpoint nghiên cứu: `me5-6k-devlock-epoch2`; Stage 2 chưa train.

[EDA và hashes](w1/eda/dataset_eda.json), [Stage 1 bundle/metric](w3/handoff/evidence_snapshot.json), [verification](w3/handoff/verification_summary.json) là evidence đi kèm. Model/vector/trace lớn ở local; train nặng chỉ chạy Kaggle, GPU local dùng inference/benchmark. Không dùng dev/regression để tuyên bố independent generalization.

Mỗi experiment ghi Observation → Hypothesis → Experiment → Result → Decision, model/index/policy/data hash, denominator và rescue/harm theo slice. Pass test chức năng không thay quality acceptance; SLA đề xuất không thay load test đã đo.
