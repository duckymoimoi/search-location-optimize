# Frozen artifacts

Chỉ giữ artifact cần để chạy hoặc kiểm chứng bản demo hiện tại:

- `models/e5-v4-finetuned/`: encoder được API mount qua junction `apps/poi-search/models/current`.
- `indexes/hanoi-poi-stable-v1-release1/`: embedding context, id-map và metadata để dựng lại OpenSearch index 45.692 POI.
- `evaluations/stage1-stable-v1/`: các JSON tổng hợp dev, test frozen, architecture holdout, typing session, load và so sánh fine-tune/zero-shot.

Checkpoint giữa epoch, per-query cache, query embedding tạm và output Kaggle cũ đã được loại bỏ. Muốn thay model phải tạo release mới, cập nhật `apps/poi-search/models/MODEL_RELEASE.json`, dựng lại vector cùng embedding space rồi chạy lại toàn bộ benchmark.
