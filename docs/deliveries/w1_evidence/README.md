# SEARCH 2.0 — W1 Evidence Package

**Theme:** Understand the Problem  
**Acceptance output:** EDA (POI + Query) · Query/POI taxonomy · Error taxonomy · Data quality · Problem statement

## Deliverables

| # | File | Nội dung |
|---|---|---|
| 0 | [`00_PROBLEM_STATEMENT.md`](00_PROBLEM_STATEMENT.md) | “Tìm đúng” = gì; ranh giới Stage 1/2; câu hỏi W1 |
| 1 | [`01_EDA_POI.md`](01_EDA_POI.md) | Corpus 186,322 POI — phân bố, ambiguity, address |
| 2 | [`02_EDA_QUERY.md`](02_EDA_QUERY.md) | Gold 1,080 queries (rút gọn) |
| 3 | [`03_QUERY_POI_TAXONOMY.md`](03_QUERY_POI_TAXONOMY.md) | Strata · families · operators · tags |
| 4 | [`04_ERROR_TAXONOMY.md`](04_ERROR_TAXONOMY.md) | E0–E4 map sang metric |
| 5 | [`05_DATA_QUALITY_REPORT.md`](05_DATA_QUALITY_REPORT.md) | DQ gates + issue register |

**Query EDA đầy đủ (SoT):** [`data/vietnam/gold_stage1_v1/EDA_GOLD_STAGE1_QUERY_VARIANTS.md`](../../../data/vietnam/gold_stage1_v1/EDA_GOLD_STAGE1_QUERY_VARIANTS.md)  
**Vision / kiến trúc:** [`docs/specs/search2.0.md`](../../specs/search2.0.md)

## Locked data (SoT)

```text
data/vietnam/gold_stage1_v1/
  target_pois_v1.csv | .parquet
  query_variants_v1.csv | .parquet
  manifest.json
  qrels_policy_v1.json
  EDA_GOLD_STAGE1_QUERY_VARIANTS.md
  README.md
  verify_gold_lock.py

data/vietnam/poi_corpus_v1/
  search_documents.parquet   # index universe Stage 1
  pois_core.parquet
  eda/poi_eda_summary.md
```

Không nhân bản corpus vào thư mục w1_evidence.  
Kaggle: `training/kaggle/dataset_gold_stage1_w1/` · kernel `hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25`.
