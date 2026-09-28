# Stage-1 v6 hard-negative views (experimental)

Compiled training views only. Published `train_stage1_queries_v6/query_variants.csv` is not modified.

- `query_train_view.parquet`: same query text, remapped v3 IDs, slot weights, split.
- `query_relation_view.parquet`: authored positives, ignore, same-brand hard-neg candidates.
- `training_pairs.parquet`: written later by `tools/mine_stage1_hardneg_pilot.py`.
- Gold holdout POIs are removed from acceptables, ignore, and hard-neg candidates when `--holdout-gold` is set.
