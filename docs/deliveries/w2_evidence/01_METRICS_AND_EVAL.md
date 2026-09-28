# W2 — Metric specification và evaluation dataset

## 1. Thứ tự mục tiêu

`Business outcome → Search success → Ranking → Retrieval candidate recall`.
Không dùng một tầng thấp làm bằng chứng trực tiếp cho tầng cao hơn. Ở W2 này
chỉ có nhãn text/query và search output, nên kết luận định lượng giới hạn ở
retrieval/ranking theo qrels. Không có nhãn origin/time/click/booking để suy ra
geo relevance, conversion hay mức hài lòng thực tế.

| Tầng | Metric cần theo dõi | Đã đo trên Gold hiện hành? |
|---|---|---|
| POI candidate | Any-positive Hit@20/50; miss@50 | Có, API top-50; lexical raw riêng |
| POI ranking | Hit@1/5/10, MRR@10 | Có, full query; chỉ là text/query-only baseline |
| POI autocomplete | FHC/SHC(w=3)/PrefixAUC@5/10/50 | Có trên q01, tách raw và `entity_ready` |
| Brand group | Family-weighted AnyCompatibleHit@K, group MRR@10, coverage@20, namespace false-branch | Có, không chấm bare brand bằng exact-branch Hit@1 |
| Geo | distance-to-target, top-1 geo error, within-radius | Chưa có scenario origin-labeled trên hai Gold này |
| Business | search success, Click@1/3, selection, booking, abandonment | Chưa có log/nhãn thật |
| System | p50/p95/p99, QPS, index freshness | Chưa có benchmark tải có kiểm soát; elapsed time batch không thay thế latency percentile |

Yêu cầu W2 trong task có Recall@100, nDCG@5 và SR@1/3/5. Baseline hiện hành
chỉ trả top-50, Gold POI dùng qrels positive không có graded click utility,
nên **không tự tính** Recall@100/nDCG/SR từ Hit@50 hay từ model output. Khi
có protocol tương ứng, báo thêm nhưng giữ cùng qrels/index cho mọi profile.

## 2. Evaluation set khóa trước benchmark

| Suite | Phạm vi, nhãn | Lock |
|---|---|---|
| [Gold POI v2.1](../../../data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/LOCKED.json) | 200 POI · 800 sessions q01–q04 · 820 query-specific qrels · 200 q01 prefix evidence | manifest SHA-256 `965079a861fd19a0209a793ef372bae7a5272c00e69ce7a73b9e1722f7fa012e` |
| [Gold brand v1](../../../data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/LOCKED.json) | 70 brand families · 248 queries · 6.610 group-compatible qrels | manifest SHA-256 `4d3ddb25629108c328eaf33acfddd6c1e8891b4286ea0be6bd6cc68e29a368d8` |

Corpus/index cùng snapshot: `vn-poi-core-v3-semantic-address-dedup50`,
179.209 searchable POI, index `vn-poi-core-v3-me5-small`. Search policy SHA-256
`bab269d3a2b4c0cf44e5016b5289eec2e21c39a536eccb013dca4ddf50722559`.
Không gộp điểm POI và brand. Một query có thể có nhiều positive đã adjudicate;
đơn vị độc lập khi tính khoảng tin cậy là POI case hoặc brand family, **không**
phải mọi query/prefix như các quan sát i.i.d.

Gold POI có shortfall #12 được chấp nhận: 42/80 q01 thật sự bỏ type/context
đầu; Gold brand không có verified-alias row vì nguồn chưa xác minh alias.
Không bịa query/tag để đóng quota. 180/200 q01 POI chỉ `entity_ready` tại
ký tự cuối; sau mốc đó chỉ 20 case đủ ba checkpoint để tính SHC(w=3).

Address-scope Gold nằm ngoài phạm vi hiện hành. Số nhà/đường được xử lý trên
lexical fields riêng; wrong-number/same-street không được làm positive train
cho encoder. Đây không phải tuyên bố rằng mọi address scenario đã được đo.

## 3. Quy tắc chấm và bảo vệ Gold

- POI: lấy rank nhỏ nhất trong `acceptable_poi_ids` của từng query; miss nếu
  không có trong top-K. Tách `q01` traffic-core với `q02–q04` robustness.
- Prefix: raw FHC là diagnostic trước đủ intent; headline exact-POI chỉ từ
  `entity_ready`. SHC yêu cầu ba checkpoint liên tiếp, không rút cửa sổ ở cuối.
- Brand: một query chấp nhận mọi member tương thích trong namespace đã khóa;
  báo family-weighted và group-size slice, không chọn ngẫu nhiên một branch.
- Không sửa query/qrels sau khi thấy baseline miss. Dev và test tách theo
  brand family; POI Gold chỉ làm test, không dùng mining/distillation.
