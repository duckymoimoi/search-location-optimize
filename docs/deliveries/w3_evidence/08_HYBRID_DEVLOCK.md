# Hybrid Gold v2.1 — demo và index 6k dev-lock

Cùng 800 query Gold v2.1, cùng `search_policy.json`, request tuần tự `/v1/suggest`, `top_k` 50. Cả hai API báo `device=cuda`. Index demo `vn-poi-core-v3-me5-small` trên cổng 8000 không bị ghi đè. Index mới `vn-poi-core-v3-me5-6k-devlock` nằm trên Elasticsearch riêng cổng 9201, API cổng 8001, embedding `artifacts/embeddings/me5_small_v3_6k_devlock`.

Số hybrid này không so với Hit@1 exact-dense trên Kaggle (6k Gold 0.9475).

| | Hit@1 | Hit@20 | Hit@50 | server p50 ms | server p95 ms |
|---|---:|---:|---:|---:|---:|
| demo, zero-shot index | 0.83125 | 0.9275 | 0.9400 | 222 | 495 |
| 6k dev-lock | 0.87625 | 0.9800 | 0.99125 | 80 | 267 |

Latency đo lúc hai API cùng lên GPU, nên p50/p95 không phải một benchmark máy trống. Checkpoint 6k vẫn không được gắn vào API demo.
