# Gold Stage 1 v1

**Status:** `queries_and_pois_locked` (2026-09-18)  
**Corpus:** `vn-poi-core-v1`  
**n POI:** **180** · **n queries:** **1,080**  
**Unit:** `case_id` (intent → POI), không origin–POI pair  

**W1 evidence:** `docs/deliveries/w1_evidence/`  
**Query EDA SoT:** `EDA_GOLD_STAGE1_QUERY_VARIANTS.md`  
**Model screen:** `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md`

## Files (SoT only)

| File | Role |
|---|---|
| `target_pois_v1.csv` / `.parquet` | Locked 180 POIs |
| `query_variants_v1.csv` / `.parquet` | Locked 1,080 queries |
| `manifest.json` | Lock + SHA + strata |
| `qrels_policy_v1.json` | Sparse brand multi-positive policy |
| `EDA_GOLD_STAGE1_QUERY_VARIANTS.md` | Full query EDA |
| `verify_gold_lock.py` | `python verify_gold_lock.py` |

## Stratum

| Stratum | n |
|---|---:|
| named_clear | 36 |
| brand_branch | 36 |
| address_street_building | 28 |
| building_code | 22 |
| category_local | 20 |
| explicit_area_cross_region | 20 |
| code_transit_landmark | 18 |

## Gates (mọi case)

`destination_searchable` · province + subdistrict · `address_status=direct` + housenumber + street · không generic junk.

## Round-1 Kaggle

```bash
python data/vietnam/gold_stage1_v1/verify_gold_lock.py
python training/kaggle/prepare_kaggle_gold_stage1_w1.py
python -m kaggle kernels status hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25
```
