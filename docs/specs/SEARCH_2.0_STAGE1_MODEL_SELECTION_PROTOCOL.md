# SEARCH 2.0 — Stage 1 zero-shot model selection protocol

Ngày: 2026-09-18  
Trạng thái: **active — gold_stage1_v1 Round 1**  
Phạm vi: text-only Stage 1 trên `vn-poi-core-v1` + gold 180 case / 1080 query.  
Không dùng origin/distance/time/history trong Stage 1.

## 1. Dataset (locked)

| Artifact | Path |
|---|---|
| POIs | `data/vietnam/gold_stage1_v1/target_pois_v1.csv` (180) |
| Queries | `data/vietnam/gold_stage1_v1/query_variants_v1.csv` (1080) |
| Qrels policy | `data/vietnam/gold_stage1_v1/qrels_policy_v1.json` |
| Manifest | `data/vietnam/gold_stage1_v1/manifest.json` |

**Multi-positive:** sparse và **chỉ brand** (vài alias brand trong CSV). Không auto-expand `building_code`.

Legacy pilot-110: `data/vietnam/archive/pilot_110_origin_pair_v4/` (không dùng cho Round 1 gold).

## 2. Round 1 profiles

| Profile | Role |
|---|---|
| BM25Okapi default | lexical floor (untuned; **not** OpenSearch `lexical_v1`) |
| `intfloat/multilingual-e5-small` | compact baseline |
| `hotchpotch/bekko-embedding-v1-a8m` | speed floor |
| `hotchpotch/bekko-embedding-v1-a25m` | compact challenger |
| `contextboxai/halong_embedding` | VI-focused medium |
| `Alibaba-NLP/gte-multilingual-base` | medium multilingual |
| `BAAI/bge-m3` | quality ceiling |

Exact dense only (D=1000). Chưa ANN. Chưa hybrid RRF ở gate. Chạy trên **Kaggle GPU**.

## 3. Metric

### Primary (gate)

Recall@100 / @500 / @1000 · K@95 / K@98

### Diagnostic

SR@1/5/10 · MRR@10

### Round 1b — prefix-char (không lưu vào gold)

**Không** ghi mỗi prefix như một row trong `query_variants_v1`.  
Tại bench time, sinh **deterministic** từ `query_text` đã khóa:

- **char unit:** NFC grapheme clusters (ký tự nhìn thấy, gồm dấu tiếng Việt)
- Prefixes: `q[:1], q[:2], …, q[:|q|]` (bỏ prefix chỉ whitespace)
- Metrics: `FHC-char@1/5/10`, `SHC-char@1/5/10` (window=3), `PrefixAUC@5/10`
- Qrels: cùng `acceptable_poi_ids` (AcceptableHit); báo thêm StrictTarget nếu cần
- Đơn vị bootstrap vẫn **`case_id`** (6 full-query × nhiều prefix/case — cluster theo case)

Harness: `apps/poi-search/bench/gold_stage1_prefix_char_bench.py`  
(Kaggle: encode prefix trên corpus embedding đã có của shortlist sau gate.)

Chạy **sau** khi có shortlist từ gate Recall@K — không thay primary winner order.

### Slices

`query_variant_family` · `primary_sampling_stratum`  
Bootstrap / CI theo **`case_id`**.

## 4. Winner order

1. Recall@1000  
2. K@95 / K@98  
3. Không failure family tụt mạnh  
4. encode latency  
5. RAM / size  
6. dim nhỏ nếu quality tương đương  

Không chọn theo MRR@10.

## 5. Harness

| Step | Command / path |
|---|---|
| Lock / verify | `python data/vietnam/gold_stage1_v1/verify_gold_lock.py` |
| Prep Kaggle | `python training/kaggle/prepare_kaggle_gold_stage1_w1.py` |
| Kernel | `training/kaggle/kernel_gold_stage1_w1/run_gold_stage1_exact.py` → `hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25` |
| Aggregate | `python apps/poi-search/bench/gold_stage1_selection_report.py --runs-dir …` |

## 6. BM25 note

Screening BM25 = `rank_bm25.BM25Okapi` defaults (`k1=1.5`, `b=0.75`), whitespace+fold tokenize trên `passage_context`. Diagnostic floor only — production lexical tối ưu là ticket riêng.
