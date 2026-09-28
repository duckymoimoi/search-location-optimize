# Project structure and artifact lifecycle

Updated 2026-09-26. The GitHub tree holds **one current version**. Older
snapshots stay in git history, not as sibling folders.

## Source of truth

| Component | Canonical path | Lifecycle |
|---|---|---|
| Product demo | `apps/poi-search/` | Source code; Elasticsearch 9 + FastAPI + React |
| OSM source snapshot | `vietnam-260910.osm.pbf` | External/raw input; not committed |
| Nationwide POI corpus | `data/vietnam/poi_corpus_v3/` | `vn-poi-core-v3-semantic-address-dedup50`, 179,209 POI; active Docker demo |
| Admin | `data/vietnam/admin_regions_v1/` | Admin polygons + catalog |
| Gold POI/entity | `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/` | Locked 200 POI · 800 session · 820 qrel |
| Gold brand | `data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/` | Locked 70 family · 248 query · 6,610 qrel |
| Brand membership/lookup | `train_stage1_brand_membership_v3/`, `train_stage1_brand_lookup_v3/` | Locked sidecars on corpus v3 |
| Brand queries / splits | `train_stage1_brand_queries_v3/`, `train_stage1_brand_splits_v1/` | Locked authoring + family split |
| Stage 1 train targets | `data/vietnam/train_stage1_20k/` | Selected target pool |
| POI query compile | `data/vietnam/train_stage1_queries_v6/` | Compiled v6 queries; staging stays local |
| Hard-neg train compile | `data/vietnam/train_stage1_v6_hardneg_5k/` | Current POI train pairs |
| Unified POI+brand views | `data/vietnam/train_stage1_poi_brand_views_v1/` | E1 views; trainer gated on multi-positive mask |
| Address membership/fallback | Not built | Target contract in `docs/specs/ADDRESS_NUMERIC_FALLBACK.md` |
| Encoder embeddings | `artifacts/embeddings/me5_small_v3/` | Local/derived; rebuild from corpus + pinned model |
| Elasticsearch index | Docker volume `vn-poi-es-data` | Rebuild with `apps/poi-search/scripts/start.ps1` |
| Evaluation outputs | `artifacts/results/` | Local/derived; do not treat as the GitHub snapshot |

## GitHub vs local

1. Commit the new current set, delete the superseded paths from the tree, push.
2. Previous versions remain reachable by git history / tags, not as parallel folders.
3. After the remote has the new set, delete superseded local data folders and keep only the current paths above.
4. Do not commit embeddings, Kaggle `output_*`, OSM PBF, or query-authoring staging dumps.

## Documentation structure

| Directory | Meaning |
|---|---|
| `docs/as-built/` | Runtime/data state actually implemented at a dated snapshot |
| `docs/specs/` | Target architecture, technical contracts and experiment protocols |
| `docs/specs/schemas/` | Machine-readable extension contracts outside the HTTP app |
| `docs/contract-package-v1/` | Historical baseline package; create a new version for incompatible extensions |
| `docs/deliveries/w1/` | Frozen W1 evidence; do not rewrite old counts to match new data |
| `docs/research/` | Rationale and pilot history; not runtime truth |
| `docs/operations/` | Layout, lifecycle and release rules |

The root documents `docs/specs/search2.0.md` and
`docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md` are retained unchanged. Current
details are layered through the specs and as-built files above.

## Rebuild and release rules

1. Pin source files and SHA-256 hashes.
2. Build a staging artifact with a versioned schema/normalizer/policy.
3. Validate IDs, foreign keys, row counts, duplicate/collision rules and schema.
4. Run dev evaluation; lock configuration before frozen/holdout evaluation.
5. Publish manifest and artifact hashes; never mutate locked outputs in place.
6. Rebuild dependent embeddings/indexes when corpus, passage builder, tokenizer,
   model space or searchable fields change.
7. Activate a release atomically. Keep the predecessor in git history, not as a
   second live folder.

Do not create ambiguous directories such as `v9`, `final2` or `outputs_new` at
workspace root. Temporary batch files belong under the owning staging directory
and may be removed after a final manifest records the retained artifacts.

## Historical removals

- `HANOI_POI_STABLE_V1` and `HANOI_QUERIES_20K` are no longer runtime inputs.
- Pilot-100/110 and old Hanoi OpenSearch volumes are not current dependencies.
- Corpus v1/v2, Gold v1, Gold v2, and pre-v3 brand sidecars were removed from
  the current tree on 2026-09-26; recover them from git history.
- Historical evidence may still mention those snapshots; such statements are
  scoped to their report date and are not instructions for current runs.
