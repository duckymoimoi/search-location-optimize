# Exact dense, dense ANN và lexical — top 100

Nguồn: `artifacts/results/stage1_v6_6k_devlock_top100/summary.json`.
Bench: `apps/poi-search/bench/stage1_three_way_top100.py`.

800 query Gold v2.1. Index `vn-poi-core-v3-me5-6k-devlock`, 179.209 passage, checkpoint 6k dev-lock, `device=cuda`. Mỗi query lấy top 100. Lexical và dense ANN dùng đúng thân query Elasticsearch mà hybrid gọi (`k=100`, `num_candidates` 200). Exact dense dùng cùng vector câu đó và so với mọi passage. Chưa gộp, chưa xếp lại theo địa lý.

| | Hit@1 | Hit@20 | Hit@50 | Hit@100 | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|
| Lexical | 0.5288 | 0.7513 | 0.8100 | 0.8625 | 13.7 | 30.6 |
| Dense ANN | 0.9413 | 0.9875 | 0.9900 | 0.9913 | 22.6 | 57.4 |
| Exact dense | 0.9463 | 0.9925 | 0.9950 | 0.9988 | 10.4 | 20.6 |

Encode câu hỏi p50 8,4 ms, dùng chung cho hai đường dense. Phần tìm: exact dense p50 1,9 ms / p95 3,0 ms; ANN trên Elasticsearch p50 13,1 ms / p95 48,8 ms.

Trên 800 query: lexical đúng hạng 1 ở 9 query mà exact dense trượt hạng 1, và chỉ cứu 1 query ngoài top 20 và ngoài top 100. Exact dense đúng hạng 1 ở 343 query mà lexical trượt. ANN trượt hạng 1 ở 4 query mà exact dense bắt được.

Gộp exact dense với lexical bằng RRF, hằng số 60, trên hai danh sách top 100:

| | Hit@1 | Hit@20 | Hit@100 | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|
| Exact dense | 0.9463 | 0.9925 | 0.9988 | 10.4 | 20.6 |
| Exact dense + lexical | 0.7788 | 0.9875 | 0.9950 | 24.8 | 45.4 |

Gộp cứu hạng 1 cho 19 query exact dense trượt, và làm mất hạng 1 của 153 query exact dense đã đúng. Phần cộng điểm RRF p50 0,2 ms. Phần chậm thêm là chờ lexical.

Số hybrid đã gộp và đã xếp hạng nằm ở [`08_HYBRID_DEVLOCK.md`](08_HYBRID_DEVLOCK.md), top 50, không phải bảng này.
