# SEARCH 2.0 — Data Quality Report (W1)

**Corpus:** `vn-poi-core-v1` (186,322 POI)  
**Gold:** `gold_stage1_v1` (180 POI · 1,080 queries)  
**Ngày khóa query:** 2026-09-18

---

## 1. Phạm vi kiểm tra

| Lớp | Artifact | Kiểm tra |
|---|---|---|
| Corpus core | `pois_core.parquet` / `search_documents.parquet` | Completeness, geo, ambiguity, near-dup |
| Admin | `admin_regions_v1` | Province/subdistrict attach |
| Gold POI | `target_pois_v1.csv` | Gate chọn mẫu |
| Gold query | `query_variants_v1.csv` | Schema, severity, qrels, lock hash |
| Eval hygiene | splits / leakage | Gold targets ∈ corpus; không dùng origin |

---

## 2. Corpus — chất lượng trường

| Check | Kết quả | Mức |
|---|---|---|
| `poi_id` unique | 186,322 / 186,322 | PASS |
| Empty name | 0 | PASS |
| Lat/lon missing or invalid | 0 | PASS |
| Outside VN bbox | 31 (0.017%) | WARN |
| Province unknown | 333 (0.18%) | WARN |
| Subdistrict missing | 490 (0.26%) | WARN |
| `address_status=direct` | 47.4% | WARN (coverage) |
| housenumber ∧ street/place | 41.4% | WARN (coverage) |
| `brand` populated | 4.8% | INFO |
| `alias` populated | 7.6% | INFO |

**Kết luận:** identity + geo điểm **ổn** cho retrieval index; **địa chỉ đầy đủ chỉ ~40–47%** — mọi claim “address search production” phải điều kiện hóa.

---

## 3. Ambiguity & duplication

| Check | Kết quả | Mức |
|---|---|---|
| POI in folded-name groups ≥2 | 27.7% | FAIL-risk cho unique-name assumption |
| Near-dup same-fold ≤80m | 8,823 pairs | WARN |
| Node–way same-fold ≤80m | 1,508 pairs | WARN — cần dedup business |
| Junk folded names (`a`, …) | có trong top list | WARN |

**Action:** Stage 1 metric dùng multi-positive khi text mơ hồ; Stage 5 dedup; không collapse nhầm hai thực thể thật sự khác nhau chỉ vì cùng fold.

---

## 4. Gold POI gates (180) — PASS

Mọi case thỏa:

1. `destination_searchable`
2. province + subdistrict
3. `address_status=direct` + housenumber + street
4. Không generic junk tên
5. Loại intended trùng pilot-110 legacy archive

Stratum counts khóa trong `manifest.json`. SHA-256 `target_pois_v1.csv`: `b0ffa06253f6…`.

---

## 5. Gold query — PASS (frozen)

| Check | Kết quả |
|---|---|
| Rows | 1,080 = 180 × 6 |
| Severity | CLEAN 499 · SINGLE 581 · COMPOUND 0 |
| Review | 100% accepted |
| Fold-distinct per case | enforced at lock |
| Multi-positive | 17 rows · policy brand-sparse |
| SHA-256 CSV | `3703931627d410f5fbda6540c89783e71bac4f1da4bdbb21c76188547961e5a4` |

**Giới hạn diễn giải (không phải defect):** phân bố family là design diagnostic, không phải production mix; `lang_en` quá mỏng cho benchmark EN độc lập.

---

## 6. Qrels policy

| Rule | Status |
|---|---|
| Acceptable từ file đã khóa | YES |
| Auto-expand building_code | **NO** |
| Brand multi-positive | sparse, as authored |
| Dual metrics Strict / Acceptable | required in W2+ |

File: `qrels_policy_v1.json`.

---

## 7. Leakage & đánh giá sạch

| Risk | Mitigation |
|---|---|
| Train/eval cùng query string | Gold tách; training augmentation sau không copy nguyên văn gold |
| Origin leakage vào Stage 1 | `origin_used=false` trong manifest |
| Click PII | Không đưa PII vào báo cáo / checkpoint |
| ANN vs exact | Model screen Round 1 = exact D=1000; ANN benchmark riêng |

---

## 8. Issue register (rút gọn)

| ID | Severity | Mô tả | Ảnh hưởng | Hướng xử lý |
|---|---|---|---|---|
| DQ-01 | High | 52.6% thiếu address_status | Address recall trần thấp | Enrich / filter serving; gold chỉ subset direct |
| DQ-02 | High | 27.7% POI same-name group | E1.D / E2.A | Multi-positive + Stage 2 geo |
| DQ-03 | Medium | Near-dup node–way | Double results / qrel nhiễu | Dedup business layer |
| DQ-04 | Medium | Junk generic names trong corpus | Noise retrieval | Filter index / downrank |
| DQ-05 | Low | 31 ngoài bbox · 333 province unknown | Edge geo | Clean attach admin |
| DQ-06 | Info | Brand field sparse vs same-name brand lớn | Stratum/brand detect | Dùng folded name + manual gold |
| DQ-07 | Info | Gold ≠ traffic distribution | Sai diễn giải % family | Giữ diagnostic; thêm naturalistic set sau |

---

## 9. Files giữ lại (SoT data)

### `data/vietnam/gold_stage1_v1/`

| File | Role |
|---|---|
| `target_pois_v1.csv` / `.parquet` | Locked POIs |
| `query_variants_v1.csv` / `.parquet` | Locked queries |
| `manifest.json` | Lock metadata + SHA |
| `qrels_policy_v1.json` | MP policy |
| `EDA_GOLD_STAGE1_QUERY_VARIANTS.md` | Query EDA SoT |
| `README.md` | Hướng dẫn |

### Corpus (không nhân bản vào w1_evidence)

`data/vietnam/poi_corpus_v1/search_documents.parquet` (+ core/eda tại chỗ).

---

## 10. Verdict W1 data

| Hạng mục | Verdict |
|---|---|
| Corpus usable for Stage 1 index | **YES** (với cảnh báo address/ambiguity) |
| Gold usable for model screening | **YES — frozen** |
| Production-representative query mix | **NO** (không tuyên bố) |
| Ready for W2 baselines | **YES** |
