# Stage 1 — training and evaluation tools

Thư mục này giữ mã train/đánh giá nghiên cứu. Runtime API/FE nằm tại [`apps/poi-search`](../../apps/poi-search/README.md). Với thử nghiệm dense-first hiện tại, optimizer/training nặng chỉ chạy trên Kaggle; GPU local dùng inference/benchmark sau khi tải checkpoint. Xem [báo cáo thực thi](../../docs/operations/DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md).

Các đường dẫn dưới là baseline **Hà Nội lịch sử**, không phải corpus/index của phép đo dense-first 2026-09-28:

- Corpus: `HANOI_POI_STABLE_V1/hanoi_poi_stable_v1/`
- Evaluation dataset: `HANOI_QUERIES_20K/hanoi_queries_20k_stable_v1/`
- Encoder release: `artifacts/models/e5-v4-finetuned/`
- Frozen index vectors: `artifacts/indexes/hanoi-poi-stable-v1-release1/`
- Kết quả đã chốt: `artifacts/evaluations/stage1-stable-v1/`
- Protocol và kết luận: [`docs/as-built/STAGE1_EVALUATION.md`](../../docs/as-built/STAGE1_EVALUATION.md)

Các script được giữ lại theo ba nhóm: train encoder (`train_stage1.py`), chuẩn bị/đánh giá exact–ANN–hybrid, và dựng OpenSearch (`opensearch_index.py`). Mọi tuning phải dùng dev; test frozen không được dùng để chỉnh policy.
