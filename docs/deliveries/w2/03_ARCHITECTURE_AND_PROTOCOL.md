# W2 — Kiến trúc và quy tắc thí nghiệm

Stage 1 chịu trách nhiệm query text → candidate; Stage 2 nhận đúng pool đó và rerank theo context. Result layer xử lý response/selection/dedup theo contract.

## Cấu hình nghiên cứu hiện tại

- Corpus v3 179.209 POI; checkpoint `me5-6k-devlock-epoch2`, vector 384d, ANN index cùng checkpoint.
- S1-A: dense-first, raw encoder input/raw ranking, budget 100; brand fuzzy/membership bật; name lookup promotion tắt.
- S1-B: hybrid raw budget 100, bao gồm query ngắn trong coverage control. Giữ làm đối chứng pool cho ranking.
- Elasticsearch vẫn cần cho lexical, hydration, map và geo. Exact GPU dùng đối chứng, chưa thay backend mặc định.

Giữ model/normalizer/retrieval/ranking/budget tách được để ablate. Không bật broad heuristics cùng đổi model rồi quy mọi cải thiện cho lexical hoặc embedding.

## Contract candidate cho W3/W4

Query ID/text, route, candidate IDs theo thứ tự, branch rank/score với tên thang điểm, model/index/policy versions và feature snapshot. Qrels nằm trong dataset offline. Stage 2 output phải là permutation của input pool; cắt top 10 sau ranking. Nếu cần thêm POI, tạo Stage 1 version mới.

## Protocol và release gate

Train nặng trên Kaggle; local inference/benchmark model đã tải. Khóa dataset role, split và metric trước đánh giá; dùng dev chọn cấu hình, independent holdout cho sign-off. Mỗi experiment ghi Observation/Hypothesis/Experiment/Result/Decision và rescue/harm theo segment.

Reproducibility cần hash model/vector/ID map/policy và code. Artifact lớn giữ local, [snapshot](../w3/handoff/evidence_snapshot.json) trong Git. Có code/trace đủ chuẩn bị ranker không đồng nghĩa model Stage 2 hay SLA production đã đạt.
