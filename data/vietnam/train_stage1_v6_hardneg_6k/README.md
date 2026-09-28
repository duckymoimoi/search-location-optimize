# Stage-1 v6 hard-negative views (experimental)

Compiled training views only. Published `train_stage1_queries_v6/query_variants.csv` is not modified.

- `query_train_view.parquet`: same query text, remapped v3 IDs, slot weights, split.
- `query_relation_view.parquet`: authored positives, ignore, same-brand hard-neg candidates.
- `training_pairs.parquet`: lexical=1, dense=3, random=2; sibling quota 0.
- Eval gold is `gold_stage1_v2_1` (800 sessions), not Gold v1.
