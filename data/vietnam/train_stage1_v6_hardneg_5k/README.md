# Stage-1 v6 hard-negative views (experimental)

Compiled training views only. Published `train_stage1_queries_v6/query_variants.csv` is not modified.

- `query_train_view.parquet`: same query text, remapped v3 IDs, slot weights, split.
- `query_relation_view.parquet`: authored positives, ignore, same-brand hard-neg candidates.
- `training_pairs.parquet`: 2 random + 3 lexical + 3 dense; sibling quota 0.
- Slot weights: v01/v02=1.0, SINGLE v03/v05=0.5, COMPOUND v04/v06=0.25.
