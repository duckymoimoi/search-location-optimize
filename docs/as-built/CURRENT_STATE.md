# Trạng thái triển khai hiện tại

Cập nhật: **2026-09-26**.

Tree hiện hành chỉ giữ **một bộ**: corpus v3, Gold POI v2.1, Gold brand v1.
Bản cũ (corpus v1/v2, Gold v1/v2, brand sidecar trước v3) nằm trong git history.

## 1. Dữ liệu (SoT)

| Thành phần | Giá trị | Path |
|---|---|---|
| Corpus demo Docker | `vn-poi-core-v3-semantic-address-dedup50`, 179.209 searchable | `data/vietnam/poi_corpus_v3/` |
| Admin | `admin_regions_v1` | `data/vietnam/admin_regions_v1/` |
| Gold POI/entity | `gold_stage1_v2_1` — 200 POI · 800 session · 820 qrel | `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/` |
| Gold brand | `gold_stage1_brand_v1` — 70 family · 248 query · 6.610 qrel | `data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/` |
| Brand membership | v3 locked; 11.124 accepted row, 10.929 unique v3 dest | `data/vietnam/train_stage1_brand_membership_v3/` |
| Brand lookup | v3 locked | `data/vietnam/train_stage1_brand_lookup_v3/` |
| Brand queries / split | queries v3 + family split 215/35/70 | `train_stage1_brand_queries_v3/`, `train_stage1_brand_splits_v1/` |
| Train POI | Pool 20k + query v6 compile + hard-neg 5k | `train_stage1_20k/`, `train_stage1_queries_v6/`, `train_stage1_v6_hardneg_5k/` |
| POI+brand views | 36.000 POI + 908 brand, weight 85/15 | `data/vietnam/train_stage1_poi_brand_views_v1/` |
| Embeddings demo | mE5-small 384d (local) | `artifacts/embeddings/me5_small_v3/` |
| W1 evidence | EDA · taxonomy · DQ · problem statement | `docs/deliveries/w1_evidence/` |

Hướng corpus: [`NATIONWIDE_CORPUS_DIRECTION.md`](NATIONWIDE_CORPUS_DIRECTION.md).

Corpus v3: 179.209 POI sau merge trùng gần trên v2 và drop rác/ngoại ngữ, có bảo vệ Gold/eval. Docker demo dùng embedding `me5_small_v3` và index `vn-poi-core-v3-me5-small`.

## 2. Runtime FE/BE

`apps/poi-search/` chạy trên **Elasticsearch 9.5.3** + **intfloat/multilingual-e5-small**. Search policy hiện là `search-policy-stable-demo-v10`, lexical dùng trường địa chỉ có cấu trúc (`housenumber` / `street` / `place`) và ranker dùng `geo_mode=v6`.

| Service | Compose |
|---|---|
| Elasticsearch | `elasticsearch:9.5.3` |
| Indexer | one-shot bulk → `vn-poi-core-v3-me5-small` |
| API | `:8000` hybrid lexical + knn + RRF |
| Web | `:5173` nginx |

Start: `apps/poi-search/scripts/start.ps1` (cần embeddings trong `artifacts/embeddings/me5_small_v3/`).

### Address/numeric gap

Runtime chưa có address membership snapshot hay address-scope eval. Số nhà/đường vẫn xử lý ở lexical field-level. Thiết kế đích: [`ADDRESS_NUMERIC_FALLBACK.md`](../specs/ADDRESS_NUMERIC_FALLBACK.md).

## 3. Stage 1 evaluation

Hai suite đã lock trên corpus v3 theo [`STAGE1_EVALUATION_SUITE.md`](../specs/STAGE1_EVALUATION_SUITE.md). `address_scope_eval_v1` vẫn out of scope.

| Suite | Trạng thái |
|---|---|
| `gold_stage1_v2_1` | Locked. E0 miss-taxonomy: 0 absent, 60 candidate miss, 10 rank miss, 730 hit@20 |
| `gold_stage1_brand_v1` | Locked. E0 hybrid family AnyCompatibleHit@20 0.776, MRR@10 0.597, Hit@50 0.924 |
| `address_scope_eval_v1` | Out of scope cho drop hiện tại |
| E1 POI+brand train | Views đã compile; trainer có sample/mask; chưa chạy vì gated trên multi-positive mask |

| Việc | Trạng thái |
|---|---|
| Round-1 exact D=1000 (BM25 + dense) | Kaggle; winner **mE5-small** |
| Round-1b prefix-char | Kaggle → `artifacts/results/gold_stage1_prefix_char/` (mE5 dẫn FHC/AUC) |
| Lexical rescue diag | `docs/deliveries/w1_evidence/08_LEXICAL_RESCUE_DIAGNOSTIC.md` |
| Protocol | `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md` |
| Model SoT | `docs/deliveries/w1_evidence/07_MODEL_CATALOG_AND_RESULTS.md` |

Replay: `apps/poi-search/bench/gold_stage1_v21_docker_baseline.py` và
`apps/poi-search/bench/gold_stage1_brand_v1_docker_baseline.py`.

## 4. Đã gỡ khỏi tree hiện hành

- `HANOI_POI_STABLE_V1`, `HANOI_QUERIES_20K`, pilot-100/110 (2026-09-18)
- Corpus v1/v2, Gold v1, Gold v2, brand membership/lookup/query trước v3 (2026-09-26)
- Khôi phục bằng git history, không giữ folder song song trên GitHub hay local

## 5. Việc tiếp theo

1. ANN recall vs exact (optional quality check)
2. Chạy E1 sau khi trainer multi-positive mask đã sẵn
3. Address membership + address-scope eval vẫn tách, không phải gate của drop này
