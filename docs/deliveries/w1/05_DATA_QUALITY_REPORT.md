# W1 — Data quality và readiness

Cập nhật 2026-09-28. Nguồn: [EDA](eda/dataset_eda.json), [Gold POI validation](../../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_2/validation_report.json).

| Kiểm tra | Kết quả | Hành động |
|---|---|---|
| Corpus ID/search documents | 179.209 ID duy nhất, khớp set | Pin hash cùng checkpoint/vector |
| Gold POI v2.2 | 200 target/800 query/820 qrel/200 prefix; verifier PASS, tái dựng giống byte | Dùng regression; không coi là fresh holdout |
| Gold brand v1 | 70 family/248 query/6.610 qrel; verifier PASS | Chấm macro family và namespace |
| 6k clean train/dev | Intended entity/text overlap 0 | Giữ split theo case và pin pack |
| 6k clean pairs/Gold positives | Overlap 0; pair IDs trong corpus | Không suy từ audit file sang checkpoint nếu thiếu run manifest |
| Address direct/access | 51,99% thiếu direct address; pickup access chưa xác minh | Missing feature/slice riêng |
| Brand authoring | 2 query needs_review | Review trước sử dụng có yêu cầu accepted labels |
| Mixed training view | Dev chỉ 126 brand query | Thêm POI dev trước model selection chung |
| Independent holdout/context logs | Chưa đủ | Chặn claim generalization/personalization |

Gold v2.2 giữ nguyên nhãn từ dữ liệu đã có; kiểm tra cấu trúc và qrel consistency không thay cho đánh giá factuality độc lập. EDA không chứng minh false-negative rate toàn bộ train pack; audit mẫu thuộc W3.

## Điều kiện sẵn sàng

Đủ nghiên cứu retrieval offline khi source/payload hash, split, qrels và corpus nhất quán. Chưa đủ nghiệm thu Stage 2 khi thiếu context/selection thật và time split. Chưa đủ production khi holdout, namespace/numeric/geo và load/fallback chưa qua gate.

Tái kiểm tra: `python tools/reissue_gold_stage1_v22.py verify`; EDA chạy `python tools/report_current_datasets.py --out artifacts/results/dataset_eda_new`. Phải dùng đủ artifact và báo scope nếu thiếu pack local.
