# W3 — Quyết định Stage 1 và bàn giao W4

## Cấu hình chốt cho nghiên cứu

Checkpoint `me5-6k-devlock-epoch2`, ANN index `vn-poi-core-v3-me5-6k-devlock`, raw encoder input, candidate budget 100. S1-A dense-first có brand fuzzy/membership; name lookup promotion tắt. S1-B hybrid raw giữ làm coverage control. Giữ Elasticsearch/lexical; chưa đổi demo production mặc định hoặc train model mới.

## Gói bàn giao

- [Training/checkpoint](01_TRAINING_AND_CHECKPOINT.md), [negative audit](02_MINING_AND_NEGATIVE_AUDIT.md), [benchmark](03_RETRIEVAL_BENCHMARK.md), [error/gates](04_ERROR_ANALYSIS_AND_GATES.md).
- [Model/vector/policy/trace hashes](handoff/evidence_snapshot.json) và [kết quả kiểm tra](handoff/verification_summary.json).
- Query, candidate IDs, branch scores/ranks, route và source versions; context/feature snapshot cần chuẩn bị riêng cho W4.
- Model/vector/trace lớn ở local; Git chứa code/config/recipe/summary. Khôi phục đúng hash trước replay.

## Trách nhiệm tuần sau

W4 xây evaluator trên cùng pool, so retrieval-order/text-only rồi thêm geo/time/behavior khi nguồn hợp lệ. Không thêm/mất ID trong ranker; cắt response top 10 sau ranking. Khi đổi retrieval phải version pool và làm thí nghiệm riêng.

Stage 2 chưa train/triển khai. Thiếu log thật không ngăn xây evaluator/baseline heuristic có giới hạn, nhưng ngăn tuyên bố personalization được chứng minh. [Kế hoạch đầu ra W4](../w4/README.md).

Tái kiểm tra retrieval: `python tools/verify_stage1_handoff.py --api http://127.0.0.1:8003 --out artifacts/results/dense_first/verify_new`; cần API ready và artifact source đầy đủ. Train nặng chỉ trên Kaggle.
