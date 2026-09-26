# Data — corpus & gold (SEARCH 2.0)

GitHub giữ **một bộ hiện hành**. Bản cũ nằm trong git history, không ngồi cạnh nhau trong tree.

| Path | Nội dung |
|---|---|
| `data/vietnam/poi_corpus_v3/` | Active corpus `vn-poi-core-v3-semantic-address-dedup50` — 179,209 POI |
| `data/vietnam/admin_regions_v1/` | Admin polygons + catalog |
| `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/` | Gold POI/entity — 200 POI · 800 session · 820 qrel |
| `data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/` | Gold brand — 70 family · 248 query · 6,610 qrel |
| `data/vietnam/train_stage1_brand_membership_v3/` | Brand membership sidecar trên corpus v3 |
| `data/vietnam/train_stage1_brand_lookup_v3/` | Fast lookup brand v3 |
| `data/vietnam/train_stage1_brand_queries_v3/` | Brand intent / qrels / train-eval view |
| `data/vietnam/train_stage1_brand_splits_v1/` | Family-disjoint train/dev/test |
| `data/vietnam/train_stage1_20k/` | Target pool POI hiện hành |
| `data/vietnam/train_stage1_queries_v6/` | Query POI v6 đã compile (không kèm staging) |
| `data/vietnam/train_stage1_v6_hardneg_5k/` | Train compile hard-neg hiện hành |
| `data/vietnam/train_stage1_poi_brand_views_v1/` | Unified POI+brand views cho E1 |
| `data/vietnam/vietnam_nationwide_poi_count_report.*` | Scan đếm PBF |

Registry: `data/vietnam/stage1_eval_suite_v2/suite_registry.json`.  
Contract: `docs/specs/STAGE1_EVALUATION_SUITE.md`. Address-scope eval vẫn out of scope.

PBF nguồn (nếu có): `vietnam-*.osm.pbf` ở repo root — không commit.

> Đã gỡ khỏi tree hiện hành: corpus v1/v2, Gold v1, Gold v2, brand membership/lookup/query cũ. Khôi phục bằng git history.
