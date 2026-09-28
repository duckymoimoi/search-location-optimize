# W2 — Search architecture và experiment protocol

## 1. Kiến trúc as-built

Corpus v3 → search documents/embedding offline → Elasticsearch 9.5.3 index
`vn-poi-core-v3-me5-small` → FastAPI `/v1/suggest` → kết quả POI. Lexical
dùng BM25 trên name/alias và trường địa chỉ tách `housenumber`, `street`,
`place`; dense dùng pretrained `intfloat/multilingual-e5-small` 384d. API
trộn candidate bằng RRF rồi áp policy/ranking/dedup. Policy hiện tại:
`search-policy-stable-demo-v10`, branch depth 50, candidate budget 50,
ANN candidates 200, RRF constant 60, geo mode v6. Đường tìm kiếm số nhà/đường
đã chuyển sang field-level lexical; không huấn luyện encoder coi số sai là
đúng POI gần đó.

SoT runtime: [`CURRENT_STATE.md`](../../as-built/CURRENT_STATE.md),
[`search_policy.json`](../../../apps/poi-search/api/search_policy.json).
Baseline runner:
[`gold_stage1_v21_docker_baseline.py`](../../../apps/poi-search/bench/gold_stage1_v21_docker_baseline.py)
và [`gold_stage1_brand_v1_docker_baseline.py`](../../../apps/poi-search/bench/gold_stage1_brand_v1_docker_baseline.py).
Không gọi `hybrid_api` là pure Stage-1 encoder score; nó đã qua nhiều bước
policy. Không gọi profile lexical raw là baseline A+geo khi không cấp origin.

## 2. Hypothesis → experiment → lỗi → quyết định

| Giả thuyết W2 | Thí nghiệm đã có | Nhận định hợp lệ | Handoff W3 |
|---|---|---|---|
| Lexical yếu khi query nhiễu nhiều vị trí | So A/C trên q01–q04 | q03 Hit@20: lexical 49,5% vs hybrid 87,0%; chỉ chứng minh pipeline hybrid tốt hơn trên slice | So model-only/dense-only cùng candidates và policy |
| Brand bare-text cần group semantics | Brand Gold family-weighted | Hybrid @50 cao, nhưng @20/MRR thấp hơn lexical | E1 brand train phải cải thiện @20 mà không hại POI; kiểm tra ordering và namespace |
| Miss W2 chủ yếu do candidate hay rank? | POI miss taxonomy | 60 candidate miss@50, 10 rank miss 21–50 | Audit candidate pool trước thử reranker |

## 3. Protocol tái lập và gate vòng train

1. Giữ nguyên Gold POI v2.1 và Gold brand v1; pin manifest hashes trong
   [`01_METRICS_AND_EVAL.md`](01_METRICS_AND_EVAL.md), corpus v3, index và
   policy. Train/dev/test brand theo family; không đưa Gold query/qrels vào
   training, mining hoặc chọn checkpoint.
2. E0 = POI-only; E1 = cùng budget/seed/corpus/policy + brand train với
   positive pool và mask. Trainer E1 chỉ chạy sau khi multi-positive/ignore
   mask có test; không biến bare brand thành một branch hidden positive.
3. E1 acceptance đã pin trước test ở
   `data/vietnam/train_stage1_poi_brand_views_v1/e1_experiment_protocol.json`:
   brand family AnyCompatibleHit@20 tăng ít nhất 1 điểm phần trăm; POI
   Hit@1, Hit@20, Hit@50 và q01 Hit@1 không giảm quá 1 điểm. Đây là ngưỡng
   thí nghiệm, không phải kết quả đã đạt. E1 **chưa train/chưa benchmark**.
4. Khi so encoder, chạy dense-only và lexical/hybrid trên cùng Gold, cùng
   candidate budget và index snapshot; tách candidate recall khỏi final rank.
   Không dùng train 5k/6k query làm test. CI/bootstrap theo POI case/brand
   family. Công bố cả thất bại, không chỉ overall win.

## 4. Chưa thể nghiệm thu đầy đủ từ evidence hiện tại

- Dense-only B và ranker D chưa có cùng-snapshot ablation trên hai Gold.
- Không có query/click/booking log thật để tính business conversion hoặc
  traffic-weighted success; không suy từ synthetic Gold.
- Không có origin/time-labeled scenarios trên Gold này để đo geo distance,
  top-1 geo error hay personalization; các mục đó thuộc vòng sau.
- Chưa có p50/p95/p99/QPS/index-freshness benchmark chuẩn; elapsed time của
  batch script không phải latency của một request ở tải xác định.

Vì vậy W2 đã tạo mốc so sánh Stage-1 text cho W3, nhưng bảng A/B/C/D và
toàn bộ metric hierarchy chỉ **đạt một phần**. Không tô trạng thái `PASS`
toàn bộ cho đến khi các phép đo thiếu thực sự được chạy hoặc phạm vi nghiệm
thu được chốt lại bằng văn bản.
