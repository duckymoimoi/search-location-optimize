# W2 — Baseline benchmark và error analysis

**So sánh hợp lệ:** hai profile dưới đây chạy trên cùng Gold đã khóa, corpus
v3 và index 179.209 POI. `lexical_raw` là Elasticsearch DSL; `hybrid_api` là
API cuối (lexical + dense mE5-small + RRF và policy). Chênh lệch hai profile
**không** chứng minh riêng hiệu quả của embedding hoặc geo ranker.

## 1. POI/entity — 800 completed queries

| Profile | Hit@1 | Hit@5 | Hit@20 | Hit@50 | MRR@10 | Miss@50 |
|---|---:|---:|---:|---:|---:|---:|
| Lexical raw | 49,88% | 63,12% | 71,75% | 78,75% | 0,5555 | 170 |
| Hybrid API | 82,12% | 88,38% | 91,25% | 92,50% | 0,8478 | 60 |

Hybrid hơn lexical raw 19,50 điểm phần trăm ở Hit@20 trong **phép so sánh
pipeline**, không phải uplift model-only. Theo role, hybrid Hit@20: q01
98,5%; q02 90,0%; q03 87,0%; q04 89,5%. Lexical raw q03 chỉ 49,5%, cho
thấy nhiễu nhiều vị trí là slice cần giữ khi so challenger. Theo stratum,
hybrid Hit@20 thấp nhất trong các nhóm lớn là `building_code` 82,69% và
`brand_branch` 86,84%; `code_transit_landmark` đạt 98,75%. Không dùng mức
khác nhau giữa strata để suy traffic thực vì Gold được chọn có chủ đích.

Miss taxonomy trên hybrid top-20: **0 target absent, 60 candidate miss@50,
10 rank miss (rank 21–50), 730 hit@20**. Vì 60/70 miss@20 vắng khỏi top-50,
ưu tiên kiểm tra candidate generation trên các case đó trước khi chỉ đổi
re-rank top-50. Đây là phân loại theo output đã pin, không được sửa nhãn Gold.

q01 autocomplete hybrid trên 200 case/5.092 checkpoint: raw FHC@10 found
99,5%, SHC(w=3)@10 found 98,0%, PrefixAUC@10 0,6765. Từ
`entity_ready`, FHC@10 found 98,5%, PrefixAUC@10 0,9845; chỉ 20/200 case
có đủ ba checkpoint sau mốc nên SHC sau mốc có denominator 20, không phải
200. Các FHC raw rất sớm không chứng minh model đã hiểu đúng chi nhánh.

## 2. Brand — 70 family/248 query

Headline là family-weighted, không phải query micro-average.

| Profile | AnyCompatibleHit@20 | @50 | Group MRR@10 | Compatible coverage@20 | Wrong namespace@20 |
|---|---:|---:|---:|---:|---:|
| Lexical raw | 78,66% | 80,21% | 0,6099 | 63,78% | 4,88% |
| Hybrid API | 77,59% | 92,38% | 0,5974 | 55,60% | 1,22% |

Hybrid **kém** lexical raw 1,07 điểm phần trăm ở brand Hit@20 và 0,0126
MRR@10, dù @50 cao hơn 12,17 điểm. Đây là vấn đề thứ tự top-20/coverage,
không được che bằng @50. Trên các group từ 80 member trở lên, coverage@20
về mặt dung lượng đã bị giới hạn, nên phải xem cùng group size, không chỉ
aggregate. Alias coverage thiếu evidence đã được ghi trong Gold lock.

Brand prefix hiện chỉ chấm lexical raw: 164 group-ready queries,
2.294 checkpoint, FHC@10 từ `group_ready` 89,63%, PrefixAUC@10 0,5191.
Không có hybrid brand-prefix report tương đương; không suy hybrid prefix
từ full-query.

## 3. Baseline A/B/C/D theo yêu cầu tuần 2

| Baseline | Trạng thái trên Gold v3 hiện hành | Giới hạn |
|---|---|---|
| A — lexical/full-text | Đã chạy `lexical_raw` cho POI và brand | Query-only; không phải phép đo geo-filter |
| B — dense pretrained-only | **Chưa chạy lại trên Gold v3 này** | W1 dense model screen ở snapshot cũ, không so ngang các số ở đây |
| C — lexical+dense hybrid | Đã chạy `hybrid_api` | Bao gồm policy/ranking khác A; cần ablation để quy uplift cho dense |
| D — rank đơn giản text+distance+popularity | **Chưa có ablation riêng trên cùng Gold** | Không có origin/popularity labels phù hợp để nghiệm thu geo/business |

Nguồn machine local: [POI baseline](../../../artifacts/results/gold_stage1_v21_docker_baseline/baseline_report.json)
(SHA-256 `1dd52896500119ab665a02488dab04989e6d1a188d2fab3d9579b09ba61e1d20`),
[POI miss taxonomy](../../../artifacts/results/gold_stage1_v21_docker_baseline/miss_taxonomy.json)
(SHA-256 `4bdc579642c49edd7663c988b35b3d4cb0a0150c0d9d59a9f26bd24d793cdc50`),
[brand baseline](../../../artifacts/results/gold_stage1_brand_v1_docker_baseline/baseline_report.json)
(SHA-256 `07d8e39768d051ae0efaef5e016e9e3d52ac93d5a979b4d9018f3c13a547469d`).
Không dùng 5k/6k train-query baseline làm untouched test.
