# W2 — Baseline và bottleneck

Các baseline A–D cần cùng dataset/context và version để so sánh. Bảng dưới ghi đúng phạm vi đã có; không quy chênh lệch cả pipeline cho riêng embedding.

| Baseline | Trạng thái |
|---|---|
| A lexical/full-text + geo | Lexical query-only đã đo; geo-quality chưa có đầy đủ nhãn context |
| B pretrained dense | Có đối chứng model trong train evaluation; chưa đủ ma trận A–D cùng context |
| C lexical+dense | Có benchmark hybrid và ablation fusion/ranking |
| D text+distance+popularity | Có heuristic runtime và smoke; chưa có quality ablation đầy đủ |

## Mốc POI regression 800 query, corpus v3

| Profile | Hit@1 | Hit@20 | Hit@50 | MRR@10 |
|---|---:|---:|---:|---:|
| Lexical raw | 49,88% | 71,75% | 78,75% | 0,5555 |
| Hybrid API | 82,12% | 91,25% | 92,50% | 0,8478 |

Mốc này dùng index mE5-small và pipeline baseline, không phải kết quả mới của candidate dev-lock. Run ID: `gold_stage1_v21_docker_baseline`. Gold v2.2 giữ cùng payload; không gọi đây là một lần chấm mới. Nguồn local: `artifacts/results/gold_stage1_v21_docker_baseline/baseline_report.json`, SHA-256 `1dd52896500119ab665a02488dab04989e6d1a188d2fab3d9579b09ba61e1d20`.

## Error analysis và quyết định

Hybrid có 730 hit@20, 60 target vắng pool top 50 và 10 target rank 21–50. Observation: phần lớn miss là candidate miss. Hypothesis: chỉ rerank top 50 sẽ không đủ. Experiment: kiểm qrels theo stage. Result: 60/70 miss@20 vắng pool. Decision: W3 phải đo coverage và retained candidates.

Brand macro-family Hit@20 lexical 78,66%, hybrid 77,59%; hybrid @50 cao hơn không bù được thứ tự top 20. Run `gold_stage1_brand_v1_docker_baseline`; SHA-256 summary `07d8e39768d051ae0efaef5e016e9e3d52ac93d5a979b4d9018f3c13a547469d`.

Các phép đo cùng checkpoint dev-lock hiện tại được báo riêng ở [benchmark W3](../w3/03_RETRIEVAL_BENCHMARK.md), không tính uplift trực tiếp từ bảng regression này sang dev khác mẫu số.
