# SEARCH 2.0 — W3 retrieval evidence

| Báo cáo | Nội dung |
|---|---|
| [`01_HARDNEG_6K_KAGGLE_AUDIT.md`](01_HARDNEG_6K_KAGGLE_AUDIT.md) | Kaggle 6k exact-dense result, leakage audit, giới hạn diễn giải và phép đo tiếp theo |
| [`02_DIAGNOSTIC_REGRESSIONS.md`](02_DIAGNOSTIC_REGRESSIONS.md) | 17 query mất rank 1 và 4 q03 miss@20 trên run diagnostic 352867030 |
| [`03_HARDNEG_SAMPLE_AUDIT.md`](03_HARDNEG_SAMPLE_AUDIT.md) | 150 hard negative của pack 6k sạch Gold: 2 false negative, đều dense |
| [`04_PREFIX_READY_DENOMINATOR.md`](04_PREFIX_READY_DENOMINATOR.md) | Mẫu số prefix `entity_ready` trên Gold v2.1, khóa trước điểm model |
| [`05_DEVLOCK_6K.md`](05_DEVLOCK_6K.md) | Train 6k khóa checkpoint bằng dev; Gold chấm một lần sau lock |
| [`06_5K_VS_6K.md`](06_5K_VS_6K.md) | 5k và 6k cùng Gold v2.1, quota và dev-lock |
| [`07_PREFIX_AND_BRAND.md`](07_PREFIX_AND_BRAND.md) | Prefix `entity_ready` và brand group-compatible của checkpoint 6k |
| [`08_HYBRID_DEVLOCK.md`](08_HYBRID_DEVLOCK.md) | Hybrid Gold v2.1 trên index demo và index 6k dev-lock, kèm p50/p95 |
| [`09_BRAND_CONTINUATION.md`](09_BRAND_CONTINUATION.md) | Train tiếp brand nhiều đích; cả hai epoch bị loại vì POI dev tụt |
| [`10_BRAND_POI_MIX.md`](10_BRAND_POI_MIX.md) | Batch 12 POI + 4 brand; epoch 2 được giữ, Gold POI không đổi |
| [`11_APP_BRAND_POI_MIX.md`](11_APP_BRAND_POI_MIX.md) | Cách mở Brand+POI cạnh bản hiện tại trên app |
| [`12_EXACT_DENSE_TOP100.md`](12_EXACT_DENSE_TOP100.md) | Lexical, dense ANN, exact dense và RRF trên GPU, top 100, kèm p50/p95 |

W3 evidence không thay Gold đã khóa hoặc baseline W2. Kết quả train chỉ được
đưa vào lựa chọn model sau khi qua split/leakage và cùng-snapshot serving gates.
