# Unified POI + brand train views

Experimental compiled views for the gated E1 experiment. Brand Gold is already
locked and does not wait on this folder.

- `query_train_view.parquet` / `query_relation_view.parquet`
- Mix: 85% POI / 15% brand `sample_weight`
- Gold POI IDs are `ignore` on brand-train rows
- Trainer samples 2–4 brand positives per epoch and masks the rest

Do not accept E1 until `e1_experiment_protocol.json` deltas hold on the locked
thresholds. Compare with `python -X utf8 tools/compare_stage1_e0_e1.py`.
