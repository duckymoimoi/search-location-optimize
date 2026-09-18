# SEARCH 2.0 — W1 EDA Query

**SoT đầy đủ (frozen):** [`EDA_GOLD_STAGE1_QUERY_VARIANTS.md`](../../../data/vietnam/gold_stage1_v1/EDA_GOLD_STAGE1_QUERY_VARIANTS.md)  
**Data:** `query_variants_v1.csv` (1,080) · SHA-256 `3703931627d4…`  
**Đơn vị:** `case_id` × 6 variants · Stage 1 text-only

File dưới đây là bản bàn giao W1 (rút gọn + giữ số liệu khóa). Chi tiết operator / hardness / protocol thống kê xem SoT.

---

## 1. Mục tiêu

`query_variants_v1` là **diagnostic gold benchmark** Stage 1: chủ động bao phủ kiểu gõ và ambiguity, **không** mô phỏng tần suất traffic production.

| Chỉ số | Giá trị |
|---|---|
| Queries | **1,080** |
| Target POI / case | **180** |
| Strata | 7 |
| Macro families | 8 |
| Operators | 23 |
| Severity | 499 CLEAN / 581 SINGLE / 0 COMPOUND |
| Multi-positive rows | 17 (1.57%) |
| Review | 100% accepted |

---

## 2. Sampling strata (POI → query)

| Stratum | POI | Query | % |
|---|---:|---:|---:|
| brand_branch | 36 | 216 | 20.0 |
| named_clear | 36 | 216 | 20.0 |
| address_street_building | 28 | 168 | 15.6 |
| building_code | 22 | 132 | 12.2 |
| category_local | 20 | 120 | 11.1 |
| explicit_area_cross_region | 20 | 120 | 11.1 |
| code_transit_landmark | 18 | 108 | 10.0 |

Địa lý: 19 tỉnh · Bắc 35.6% · Nam 33.3% · Trung & TN 31.1%.

---

## 3. Macro families

| Family | N | % | Severity |
|---|---:|---:|---|
| ORTHOGRAPHIC_IME | 316 | 29.3 | SINGLE |
| ALIAS | 273 | 25.3 | CLEAN |
| CLEAN | 180 | 16.7 | CLEAN |
| MECHANICAL_TYPO | 132 | 12.2 | SINGLE |
| PHONOLOGICAL | 103 | 9.5 | SINGLE |
| ADDRESS_VARIANT | 46 | 4.3 | CLEAN/SINGLE |
| TOKEN_EDIT | 18 | 1.7 | SINGLE |
| STRUCTURAL | 12 | 1.1 | CLEAN |

CLEAN/valid : perturbation ≈ **46.2% : 53.8%**.

### Operator headline (N≥20)

`canonical` 180 · `telex_leftover` 138 · `strip_diacritics` 127 · `name_area` 111 · `phonological_confusion` 103 · `name_address` 72 · `adjacent_key` 44 · `short_name` 39 · `double_letter` 36 · …

Operator mỏng (vd `char_insert` N=4): chỉ diagnostic định tính.

---

## 4. Hardness vs corpus

| Tier | POI | Query | % |
|---|---:|---:|---:|
| EASY | 84 | 504 | 46.7 |
| MEDIUM | 11 | 66 | 6.1 |
| HARD | 38 | 228 | 21.1 |
| VERY_HARD | 47 | 282 | 26.1 |

**47.2%** query ở HARD+VERY_HARD → đủ collision để phân biệt retriever.

---

## 5. Qrels

| |acceptable| | N | % |
|---|---:|---:|
| 1 | 1,063 | 98.4 |
| ≥2 | 17 | 1.6 |

Max cardinality 10. Multi-positive: brand_branch 10 + category_local 7.  
Policy: **không** auto-expand building_code.

Report song song **StrictTargetRecall** và **AcceptableRecall**.

---

## 6. Độ dài & ngôn ngữ

- Char length: median 32 · mean 31.7 · max 56  
- Tokens: median 7 · mean 6.85  
- `lang_vi` 66.1% · `lang_mixed` 32.2% · `lang_en` 1.7% (18 query / 3 POI — smoke test only)

Prefix/autocomplete (Round 1b): sinh deterministic NFC-grapheme prefix từ query frozen → FHC-char / SHC-char / PrefixAUC (`gold_stage1_prefix_char_bench.py`). Không lưu full char-prefix trong gold.

---

## 7. Insight cho W2 baseline

1. Slice bắt buộc khi so model: family × stratum × hardness × language.  
2. Primary gate: AcceptableRecall@100/500/1000 + K@95/98 (xem protocol model selection).  
3. Không suy production mix từ tỷ lệ family trên gold.  
4. Bootstrap / CI **cluster theo `case_id`**.

Chi tiết đầy đủ: SoT `EDA_GOLD_STAGE1_QUERY_VARIANTS.md`.
