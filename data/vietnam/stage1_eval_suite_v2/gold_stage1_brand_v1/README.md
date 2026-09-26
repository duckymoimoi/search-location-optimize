# gold_stage1_brand_v1

Locked brand-group evaluation release for Stage 1. It is separate from
`gold_stage1_v2_1` and must not be scored as exact-branch Hit@1.

- 70 test families, 248 queries, 6610 compatible qrels
- Corpus: `vn-poi-core-v3-semantic-address-dedup50`
- Membership sidecar: `train_stage1_brand_membership_v3`
- Family split: `train_stage1_brand_splits_v1`
- Verified-alias shortfall is adjudicated; no aliases were invented

Headline metrics are family-weighted AnyCompatibleHit@K, group MRR, and
compatible coverage@K. Replay with
`python -X utf8 apps/poi-search/bench/gold_stage1_brand_v1_docker_baseline.py`.
