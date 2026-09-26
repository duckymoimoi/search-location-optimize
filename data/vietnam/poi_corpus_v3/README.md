# Cleaned POI corpus v3 (Target-Protected)

Version: `vn-poi-core-v3-semantic-address-dedup50`  
Status: built and verified; active in the Docker demo as index
`vn-poi-core-v3-me5-small` (179,209 documents). Embeddings:
`artifacts/embeddings/me5_small_v3/`. The v2 index is retained for rollback.

Source: `data/vietnam/poi_corpus_v2` (184,135 POIs).  
Output: **179,209 POIs** (4,433 duplicates merged within 50 m, 493 junk/foreign dropped).

## Target Protection Policy
To prevent breaking existing benchmarks, evaluation suites, and authored training datasets:
- **Priority 1 (Gold & Eval)**: All POIs in `gold_stage1_v1_corpus_v2`, `stage1_eval_suite_v2`, and `query_sessions_v2.csv` are strictly preserved (**0 Gold POIs merged or dropped**).
- **Priority 2 (Train v6 / Locked Checkpoints)**: All POIs in `train_stage1_queries_v6` (including Locked 500) are strictly preserved (**0 Locked 500 POIs merged or dropped**).
- **Priority 3 (Train 20k Pool)**: Train targets are preserved over unlabeled corpus POIs (38 internal duplicate collisions and 11 foreign/junk POIs in the 20k pool were removed).
- **Priority 4 (Quality Heuristics)**: Preserved access points, named categories, house numbers, streets, direct addresses, aliases, and nodes.

## Impact on Benchmarks & Datasets

| Dataset | Total POIs | Merged / dropped in v3 | Impact |
| :--- | :---: | :---: | :--- |
| **Gold Stage 1 v1 Corpus v2** | 180 | **0** | **100% Intact** |
| **Stage 1 Eval Suite (`query_sessions_v2.csv`)** | 200 | **0** | **100% Intact** |
| **Train v6 Locked 500 (`003_hard_noise_500`)** | 500 | **0** | **100% Intact** |
| **Train Stage 1 20k Pool** | 19,939 | **38 merge + 11 drop** | Internal dups / junk only |

## Files in this Release
- `pois_core.parquet`: 179,209 hot-path retrieval documents.
- `search_documents.parquet`: 179,209 passage texts for embedding and BM25 encoding.
- `pois.parquet`: 179,209 full raw OSM feature records.
- `pois_access_enrichment.parquet`: 179,209 ridehail routing sidecar records.
- `poi_regions.parquet`: Administrative boundary mappings for surviving POIs.
- `poi_id_migration.parquet`: Mapping from all 184,135 v2 POIs to canonical v3 POIs, merges, and drops.
- `schema_core.json`: Core schema specification.
- `manifest.json`: SHA-256 digests and build metadata.
- `cleaning_report.md`: Human-readable summary report.

## Verification

```powershell
python -X utf8 tools/verify_clean_poi_corpus_v3.py
```
