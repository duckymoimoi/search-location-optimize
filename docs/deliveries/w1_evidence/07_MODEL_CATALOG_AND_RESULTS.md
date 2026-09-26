# SEARCH 2.0 — Catalog model & kết quả Kaggle (Stage 1)

**Ngày:** 2026-09-18  
**Phạm vi:** zero-shot text-only Stage 1 trên `vn-poi-core-v1` + gold `gold_stage1_v1`  
**Protocol:** [`SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md`](../../specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md)

Tài liệu này gom **danh mục model đã screen**, **số liệu Round-1 (exact)** và **Round-1b (prefix-char)**, cùng **model đang deploy**. Không thay protocol; là SoT kết quả sau khi có artifact Kaggle.

---

## 1. Verdict

| Role | Model | HF id |
|---|---|---|
| **Primary Stage-1 (deploy)** | multilingual-e5-small | `intfloat/multilingual-e5-small` |
| Optional ceiling (không deploy) | BGE-M3 | `BAAI/bge-m3` |
| Lexical floor | BM25 Okapi (untuned) | `rank_bm25.BM25Okapi` |
| Speed floor (diagnostic) | Bekko A8M | `hotchpotch/bekko-embedding-v1-a8m` |

**Winner cả hai vòng:** mE5-small — cao nhất R@1000 + K@95 tốt nhất (Round 1), và cao nhất FHC/PrefixAUC (Round 1b). BGE-M3 không vượt mE5 trên gold này dù nặng hơn nhiều. GTE-multilingual-base **loại** (CUDA fail).

Runtime release: `apps/poi-search/models/MODEL_RELEASE.json` · index `vn-poi-core-v1-me5-small` · embeddings `artifacts/embeddings/me5_small/`.

---

## 2. Eval setup (locked)

| Hạng mục | Giá trị |
|---|---|
| Corpus | `vn-poi-core-v1` · 186,322 POI (`search_documents.parquet`) |
| Gold | `gold_stage1_v1` · 180 `case_id` · 1,080 queries |
| Passage | `passage_context` (field đã khóa trong corpus) |
| Retrieval | Exact dense top-1000 (chưa ANN) · BM25 Okapi defaults |
| Qrels | AcceptableHit (`acceptable_poi_ids`) · multi-positive sparse (brand) |
| Đơn vị stats | bootstrap / so sánh theo **`case_id`** |
| Không dùng | origin · distance · time · history · hybrid RRF ở gate |

**Kaggle**

| Vòng | Kernel / output |
|---|---|
| Round 1 exact | `hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25` → `training/kaggle/output_gold_stage1_w1/` |
| Round 1b prefix-char | `hiengchi/vn-poi-gold-stage1-prefix-char` → `artifacts/results/gold_stage1_prefix_char/` |
| Dataset | `hiengchi/vn-poi-gold-stage1-w1` |

**Runtime Kaggle (cả hai vòng):** CUDA · Python 3.12.13 · torch 2.10.0+cu128.

---

## 3. Catalog model

| Profile bench | HF / impl | Dim | Prefix quy ước | Vai trò screen | Trạng thái |
|---|---|---:|---|---|---|
| `lexical_bm25` | `rank_bm25.BM25Okapi` (`k1=1.5`, `b=0.75`) | — | fold + whitespace trên passage | Lexical floor | OK |
| `dense_me5_exact` | `intfloat/multilingual-e5-small` | 384 | `query:` / `passage:` | Compact baseline → **winner** | **Deploy** |
| `dense_bekko_a8m_exact` | `hotchpotch/bekko-embedding-v1-a8m` | 384 | (không prefix E5) | Speed floor | Diagnostic |
| `dense_bekko_a25m_exact` | `hotchpotch/bekko-embedding-v1-a25m` | 384 | (không prefix E5) | Compact challenger | Diagnostic |
| `dense_halong_exact` | `contextboxai/halong_embedding` | 768 | `query:` / `passage:` | VI-focused medium | Không thắng |
| `dense_bge_m3_exact` | `BAAI/bge-m3` (dense-only) | 1024 | (không prefix E5) | Quality ceiling | Không vượt mE5 |
| `dense_gte_mbase_exact` | `Alibaba-NLP/gte-multilingual-base` | 768* | theo model card | Medium multilingual | **FAIL** CUDA `CUBLAS_STATUS_NOT_SUPPORTED` |

\*dim theo config model; run GTE không hoàn thành trên máy Kaggle lần này.

### HF snapshot (prefix-char run)

Từ `artifacts/results/__huggingface_repos__.json`:

| repoId | commitHash (rút) |
|---|---|
| `intfloat/multilingual-e5-small` | `614241f6…` |
| `hotchpotch/bekko-embedding-v1-a8m` | `c721113d…` |
| `hotchpotch/bekko-embedding-v1-a25m` | `44f0b8af…` |

### Deploy note (mE5)

| Khóa | Giá trị |
|---|---|
| `release_id` | `vn-poi-demo-me5-r1` |
| Embedding space | `me5-small-passage-384` |
| Index | `vn-poi-core-v1-me5-small` |
| Expected rows | 186,322 |
| Vectors | L2-normalized float32 · `artifacts/embeddings/me5_small/` |
| Serving | ES 9.5.3 `dense_vector` + knn · hybrid lexical+RRF trong API |

---

## 4. Round 1 — exact Recall@K (primary gate)

**Nguồn:** `training/kaggle/output_gold_stage1_w1/gold_stage1_w1/summary_partial.json`  
**BGE / GTE:** tổng hợp từ gate note `06_ROUND1_MODEL_GATE.md` (run w1b; không còn summary local trong repo).

Thứ tự chọn theo protocol: **R@1000 → K@95/K@98 → family fail → latency → size → dim**.

| Rank | Profile | R@100 | R@500 | R@1000 | K@95 | K@98 | MRR@10 | q ms | dim | corpus s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **mE5-small** | 0.969 | 0.978 | **0.990** | **23** | 558 | 0.861 | 0.38 | 384 | 174 |
| 2 | BGE-M3 | 0.964 | 0.975 | 0.981 | 43 | 891 | 0.845 | 3.87 | 1024 | 2003 |
| 3 | BM25 Okapi | 0.904 | 0.962 | 0.974 | 313 | — | 0.590 | — | — | — |
| 4 | Bekko A8M | 0.929 | 0.959 | 0.971 | 219 | — | 0.772 | 0.21 | 384 | 105 |
| 5 | Bekko A25M | 0.935 | 0.957 | 0.967 | 214 | — | 0.774 | 0.43 | 384 | 249 |
| 6 | Halong | 0.931 | 0.956 | 0.961 | 265 | — | 0.758 | 1.09 | 768 | 610 |
| — | GTE-mbase | FAIL | | | | | | | | |

Số làm tròn 3 chữ số thập phân (R*/MRR); K và latency theo raw summary/gate.

### Slice ORTHOGRAPHIC_IME (R@1000) — điểm yếu hay gặp

| Profile | R@1000 ORTHO |
|---|---:|
| BM25 | 0.984 |
| **mE5** | **0.975** |
| Bekko A8M | 0.908 |
| Bekko A25M | 0.902 |
| Halong | 0.886 |

mE5 giữ ORTHO gần trần BM25; các dense nhỏ/VI-focused tụt rõ. Đây là lý do chính Bekko/Halong không cạnh tranh winner dù encode nhanh hoặc “VI-focused”.

### Đọc nhanh Round 1

1. **mE5** — trần recall gần tuyệt đối; K@95=23 (cần rất ít depth để đạt 95% case); encode query ~0.4 ms mean trên GPU Kaggle.
2. **BGE-M3** — ceiling thất bại tương đối: chậm ~10× encode query vs mE5, dim 1024, không thắng R@1000.
3. **BM25** — floor lexical mạnh (R@1000 0.974) nhưng K@95=313 và MRR thấp → Stage-1 cần dense hoặc hybrid production.
4. **Bekko** — A8M nhanh nhất; ORTHO ~0.90 là điểm yếu cố định.
5. **Halong** — không thắng slice VI; ORTHO kém nhất trong các dense hoàn thành.
6. **GTE** — loại khỏi xếp hạng (CUDA); không retry trừ khi cần thêm 1 multilingual medium.

---

## 5. Round 1b — prefix-char (diagnostic, không đổi winner)

**Nguồn machine:** `artifacts/results/gold_stage1_prefix_char/`  
- `summary.json` · `gate_table_prefix_char.json`  
- ranks: `prefix_ranks_*.jsonl` · `char_prefixes.parquet`

**Cách sinh prefix (bench-time, không ghi vào gold CSV):**

- Đơn vị: NFC grapheme (ký tự nhìn thấy, gồm dấu tiếng Việt)
- Prefixes: `q[:1] … q[:|q|]` (bỏ prefix chỉ whitespace)
- Metrics: FHC-char / SHC-char (window=3) / PrefixAUC @1/5/10
- 1,080 full queries → **34,241** prefixes

Shortlist chạy: BM25 · mE5 · Bekko A8M · Bekko A25M (không BGE/Halong/GTE).

### Gate prefix (overall)

| Rank | Profile | FHC@1 | FHC@5 | FHC@10 | PrefixAUC@1 | @5 | @10 | corpus encode s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | **mE5-small** | **0.878** | **0.928** | **0.950** | **0.423** | **0.542** | **0.585** | 202.5 |
| 2 | Bekko A25M | 0.796 | 0.890 | 0.907 | 0.351 | 0.480 | 0.524 | 293.4 |
| 3 | Bekko A8M | 0.778 | 0.879 | 0.899 | 0.342 | 0.488 | 0.532 | 114.1 |
| 4 | BM25 | 0.627 | 0.783 | 0.840 | 0.249 | 0.362 | 0.421 | — |

### SHC-char@10 (ổn định khi gõ thêm)

| Profile | SHC@1 | SHC@5 | SHC@10 |
|---|---:|---:|---:|
| **mE5** | 0.858 | 0.920 | **0.940** |
| Bekko A25M | 0.746 | 0.876 | 0.896 |
| Bekko A8M | 0.753 | 0.863 | 0.887 |
| BM25 | 0.596 | 0.741 | 0.806 |

### FHC@10 theo family (mE5 vs BM25)

| Family | n | mE5 FHC@10 | BM25 FHC@10 |
|---|---:|---:|---:|
| CLEAN | 180 | 0.989 | 0.922 |
| ORTHOGRAPHIC_IME | 316 | 0.886 | 0.905 |
| ALIAS | 273 | 0.971 | 0.791 |
| MECHANICAL_TYPO | 132 | 0.970 | 0.765 |
| PHONOLOGICAL | 103 | 0.981 | 0.806 |
| ADDRESS_VARIANT | 46 | 0.957 | 0.696 |
| TOKEN_EDIT | 18 | 1.000 | 0.722 |
| STRUCTURAL | 12 | 1.000 | 0.833 |

Đọc nhanh: dense mE5 **kéo mạnh** alias / typo / address khi query còn ngắn; BM25 vẫn cạnh tranh trên ORTHO full-prefix FHC (lexical exact-ish) nhưng thua lớn ở PrefixAUC và đa số family khác.

### Kết luận Round 1b

Prefix-char **xác nhận** winner Round 1: mE5 dẫn mọi cột gate prefix. Bekko nhanh hơn encode corpus nhưng không đóng được khoảng cách FHC/AUC. Không đổi primary deploy.

---

## 6. So sánh hai vòng (shortlist)

| Profile | R@1000 (R1) | K@95 (R1) | FHC@10 (R1b) | PrefixAUC@10 (R1b) | Deploy? |
|---|---:|---:|---:|---:|---|
| **mE5-small** | **0.990** | **23** | **0.950** | **0.585** | **Yes** |
| BM25 | 0.974 | 313 | 0.840 | 0.421 | Lexical branch only |
| Bekko A8M | 0.971 | 219 | 0.899 | 0.532 | No (speed diagnostic) |
| Bekko A25M | 0.967 | 214 | 0.907 | 0.524 | No |
| BGE-M3 | 0.981 | 43 | — (không chạy R1b) | — | No |
| Halong | 0.961 | 265 | — | — | No |
| GTE | FAIL | — | — | — | No |

---

## 7. Artifact map

| Artifact | Path |
|---|---|
| Round-1 summary (partial + Halong) | `training/kaggle/output_gold_stage1_w1/gold_stage1_w1/summary_partial.json` |
| Round-1 gate note | [`06_ROUND1_MODEL_GATE.md`](06_ROUND1_MODEL_GATE.md) |
| Round-1b summary / gate table | `artifacts/results/gold_stage1_prefix_char/summary.json` · `gate_table_prefix_char.json` |
| HF pins (R1b) | `artifacts/results/__huggingface_repos__.json` |
| Corpus embeddings (deploy) | `artifacts/embeddings/me5_small/` (`manifest.json`) |
| Model release | `apps/poi-search/models/MODEL_RELEASE.json` |
| Protocol | `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md` |
| Kernel R1 | `training/kaggle/kernel_gold_stage1_w1/` |
| Kernel R1b | `training/kaggle/kernel_gold_stage1_prefix/` |

---

## 8. Next (không mở lại Round-1 winner)

1. Production lexical (ES analyzer) tối ưu — ticket riêng; BM25 Okapi chỉ là floor screening.  
   Diagnostic trước tune: [`08_LEXICAL_RESCUE_DIAGNOSTIC.md`](08_LEXICAL_RESCUE_DIAGNOSTIC.md) (rescue @100 = **27**, toàn `strip_diacritics` / ORTHO; oracle Δ@100 = +0.025).  
2. Hybrid mE5 + lexical (RRF) trên gold — W2 baseline; chọn lexical variant bằng **hybrid gain**, không BM25 standalone.  
3. ANN vs exact recall check trên index ES.  
4. Fine-tune / distill chỉ sau khi hybrid baseline ổn định.
