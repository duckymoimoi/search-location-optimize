# Gold Stage-1 — Lexical rescue / overlap diagnostic

**Dataset:** `gold_stage1_v1` · 1080 queries · depth 1000
**Profiles:** dense=`dense_me5_exact` · lexical=`lexical_bm25`
**Sources:** `D:/vsf/training/kaggle/output_gold_stage1_w1/gold_stage1_w1/run_dense_me5_exact.jsonl` · `D:/vsf/training/kaggle/output_gold_stage1_w1/gold_stage1_w1/run_lexical_bm25.jsonl`

## Verdict (actionable)

- Lexical rescue @100: **27** / 1080 queries (oracle Δ vs dense = +0.025).
- Lexical rescue @1000: **9** (Δ = +0.008) — ceiling hybrid từ BM25 hiện tại.
- Trong các hit BM25@1000, **7.2%** có rank >100 (p50=1, p95=155) → ưu tiên kéo rank lên top, không phải R@1000.
- Rescue @100 tập trung family: ORTHOGRAPHIC_IME(27), ALIAS(0), CLEAN(0).
- Rescue @100 tập trung stratum: code_transit_landmark(8), named_clear(7), explicit_area_cross_region(7).
- Rescue @100 tập trung operator: strip_diacritics(27).

## Standalone ranks (context)

| Profile | R@20 | R@50 | R@100 | R@500 | R@1000 | K@95 | K@98 | MRR@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dense_me5 | 0.945 | 0.961 | 0.969 | 0.978 | 0.990 | 23 | 558 | 0.861 |
| lexical_bm25 | 0.809 | 0.870 | 0.904 | 0.962 | 0.974 | 313 | None | 0.590 |
| oracle_union | 0.979 | 0.987 | 0.994 | 0.994 | 0.998 | 6 | 22 | 0.907 |

## Overlap & lexical rescue vs mE5

| K | dense R | lex R | both | dense-only | **lex rescue** | both-miss | oracle R | Δ vs dense |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.945 | 0.809 | 838 | 183 | **36** | 23 | 0.979 | +0.033 |
| 50 | 0.961 | 0.870 | 912 | 126 | **28** | 14 | 0.987 | +0.026 |
| 100 | 0.969 | 0.904 | 949 | 97 | **27** | 7 | 0.994 | +0.025 |
| 500 | 0.978 | 0.962 | 1021 | 35 | **18** | 6 | 0.994 | +0.017 |
| 1000 | 0.990 | 0.974 | 1043 | 26 | **9** | 2 | 0.998 | +0.008 |

Oracle = `min(dense_rank, lex_rank)` (union upper bound, perfect fusion). **Δ vs dense** = oracle − dense recall — ceiling of hybrid gain from this BM25.

## BM25 hit depth (among R@1000 hits)

n=1052 · mean=28.6 · p50=1 · p90=58 · p95=155

| ≤20 | ≤50 | ≤100 | >100 |
|---:|---:|---:|---:|
| 0.831 | 0.894 | 0.928 | 0.072 |

High share of ranks >100 with R@1000 still high ⇒ precision / ranking problem, not coverage.

## Rescue @100 by family

| Family | n | dense R@100 | lex R@100 | rescue | dense-only | both-miss | oracle | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ORTHOGRAPHIC_IME | 316 | 0.911 | 0.949 | **27** | 15 | 1 | 0.997 | +0.085 |
| ALIAS | 273 | 0.993 | 0.872 | **0** | 33 | 2 | 0.993 | +0.000 |
| CLEAN | 180 | 0.994 | 0.967 | **0** | 5 | 1 | 0.994 | +0.000 |
| MECHANICAL_TYPO | 132 | 0.985 | 0.811 | **0** | 23 | 2 | 0.985 | +0.000 |
| PHONOLOGICAL | 103 | 0.990 | 0.893 | **0** | 10 | 1 | 0.990 | +0.000 |
| ADDRESS_VARIANT | 46 | 1.000 | 0.870 | **0** | 6 | 0 | 1.000 | +0.000 |
| TOKEN_EDIT | 18 | 1.000 | 0.778 | **0** | 4 | 0 | 1.000 | +0.000 |
| STRUCTURAL | 12 | 1.000 | 0.917 | **0** | 1 | 0 | 1.000 | +0.000 |

## Rescue @100 by stratum

| Stratum | n | dense R@100 | lex R@100 | rescue | dense-only | both-miss | oracle | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| brand_branch | 216 | 0.981 | 0.810 | **0** | 37 | 4 | 0.981 | +0.000 |
| named_clear | 216 | 0.968 | 0.968 | **7** | 7 | 0 | 1.000 | +0.032 |
| address_street_building | 168 | 0.994 | 0.845 | **1** | 26 | 0 | 1.000 | +0.006 |
| building_code | 132 | 0.985 | 0.939 | **1** | 7 | 1 | 0.992 | +0.008 |
| category_local | 120 | 0.975 | 0.958 | **3** | 5 | 0 | 1.000 | +0.025 |
| explicit_area_cross_region | 120 | 0.933 | 0.933 | **7** | 7 | 1 | 0.992 | +0.058 |
| code_transit_landmark | 108 | 0.917 | 0.917 | **8** | 8 | 1 | 0.991 | +0.074 |

## Rescue @100 by operator (top by rescue count)

| Operator | n | rescue @100 | dense-only | both-miss | Δ |
|---|---:|---:|---:|---:|---:|
| strip_diacritics | 127 | **27** | 3 | 0 | +0.213 |
| canonical | 180 | **0** | 5 | 1 | +0.000 |
| telex_leftover | 138 | **0** | 11 | 0 | +0.000 |
| name_area | 111 | **0** | 13 | 1 | +0.000 |
| phonological_confusion | 103 | **0** | 10 | 1 | +0.000 |
| name_address | 72 | **0** | 3 | 0 | +0.000 |
| adjacent_key | 44 | **0** | 1 | 0 | +0.000 |
| short_name | 39 | **0** | 6 | 0 | +0.000 |
| double_letter | 36 | **0** | 11 | 1 | +0.000 |
| char_delete | 26 | **0** | 4 | 0 | +0.000 |
| tone_confuse | 26 | **0** | 0 | 0 | +0.000 |
| abbreviation | 25 | **0** | 5 | 1 | +0.000 |
| partial_diacritics | 25 | **0** | 1 | 1 | +0.000 |
| char_transpose | 22 | **0** | 7 | 1 | +0.000 |
| address_component_omission | 21 | **0** | 2 | 0 | +0.000 |
| street | 16 | **0** | 1 | 0 | +0.000 |
| category | 15 | **0** | 6 | 0 | +0.000 |
| slash_normalize | 12 | **0** | 3 | 0 | +0.000 |
| token_order_variant | 12 | **0** | 1 | 0 | +0.000 |
| space_merge | 11 | **0** | 2 | 0 | +0.000 |

## Implications for Round L1 / L2

- Round L1: field boost / exact phrase / address+code analyzers nhằm ↓K@95 và ↑R@50/R@100; giữ R@1000 ≥ baseline.
- Bảo toàn ORTHO (đặc biệt strip_diacritics / fold) + brand/street/housenumber/code — nơi lexical bổ sung dense.
- Không đầu tư synonym/fuzzy nặng cho ALIAS/TYPO/PHONO — dense đã mạnh; đo lại rescue sau mỗi thay đổi analyzer.
- Round L2: chọn analyzer winner bằng hybrid (RRF) gain, không bằng BM25 standalone.

Hardness tier: chưa có SoT versioned trong gold — slice theo family/stratum/operator only.

