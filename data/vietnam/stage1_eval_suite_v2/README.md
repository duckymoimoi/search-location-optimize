# Stage-1 evaluation suite releases

The active POI/entity Gold release is [`gold_stage1_v2_1/`](gold_stage1_v2_1/README.md).
It is locked on corpus v3 with 200 targets, 800 completed sessions, 820
query-specific positive qrels and 200 q01 prefix-evidence records.

`suite_registry.json` identifies the active release. The logical `suite_id` is
`gold_stage1_v2`. The earlier v2 snapshot is in git history, not a sibling folder.

Verify v2.1 from the repository root with
`python -X utf8 tools/verify_gold_stage1_v21_release.py`. Read its signed
coverage shortfall and name-plus-street exception records before interpreting
aggregate metrics. [`gold_stage1_brand_v1/`](gold_stage1_brand_v1/README.md) is locked on corpus v3
with 70 families, 248 queries and 6610 compatible qrels. Replay it with
`python -X utf8 apps/poi-search/bench/gold_stage1_brand_v1_docker_baseline.py`.
`address_scope_eval_v1` is a separate lexical/address suite and is not a
completion gate for this drop.
