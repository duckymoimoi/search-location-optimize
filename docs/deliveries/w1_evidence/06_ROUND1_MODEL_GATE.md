# Gold Stage-1 Round 1 — merged gate report

**Dataset:** `gold_stage1_v1` · 180 `case_id` · 1,080 queries · exact D=1000  
**Sources:** `output_gold_stage1_w1/summary_partial.json` + `output_gold_stage1_w1b/summary.json`  
**Machine JSON:** `apps/poi-search/bench/results/gold_stage1_selection/round1_merged_gate.json`

## Gate (ranked)

| Rank | Profile | R@100 | R@500 | R@1000 | K@95 | K@98 | MRR@10 | q ms | dim | corpus s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **mE5-small** | 0.969 | 0.978 | **0.990** | **23** | 558 | 0.861 | 0.38 | 384 | 174 |
| 2 | BGE-M3 | 0.964 | 0.975 | 0.981 | 43 | 891 | 0.845 | 3.87 | 1024 | 2003 |
| 3 | BM25 Okapi | 0.904 | 0.962 | 0.974 | 313 | — | 0.590 | — | — | — |
| 4 | Bekko A8M | 0.929 | 0.959 | 0.971 | 219 | — | 0.772 | 0.21 | 384 | 105 |
| 5 | Bekko A25M | 0.935 | 0.957 | 0.967 | 214 | — | 0.774 | 0.43 | 384 | 249 |
| 6 | Halong | 0.931 | 0.956 | 0.961 | 265 | — | 0.758 | 1.09 | 768 | 610 |
| — | GTE-mbase | FAIL | CUDA `CUBLAS_STATUS_NOT_SUPPORTED` | | | | | | | |

## Verdict (provisional)

**Winner: `intfloat/multilingual-e5-small`.**

Theo protocol: R@1000 cao nhất + K@95 tốt nhất + dim nhỏ + latency thấp. BGE-M3 không vượt mE5 trên gold này dù nặng hơn nhiều.

### Phân tích ngắn

1. **mE5** — trần recall gần tuyệt đối; ORTHO 0.975 vẫn ổn; chỉ named_clear hơi thấp hơn BM25 ở R@1000.
2. **BGE-M3** — kiểm tra ceiling thất bại tương đối: chậm ~11×, ORTHO/code_transit/explicit_area kém mE5.
3. **BM25** — floor lexical tốt (R@1000 0.974) nhưng K@95=313, MRR thấp → cần Stage-1 dense hoặc hybrid sau.
4. **Bekko** — A8M nhanh nhất; ORTHO ~0.90 là điểm yếu; giữ làm speed diagnostic.
5. **Halong** — không thắng VI slice; ORTHO 0.886 kém nhất trong dense OK.
6. **GTE** — loại khỏi xếp hạng (CUDA); không retry trừ khi cần thêm 1 multilingual medium.

## Shortlist đề xuất

| Role | Model |
|---|---|
| Primary Stage-1 | mE5-small |
| Optional ceiling | BGE-M3 (không bắt buộc deploy) |
| Lexical floor | BM25 Okapi (untuned) |
| Speed floor | Bekko A8M (diagnostic) |

**Next:** prefix-char Round-1b trên shortlist; W2 thử hybrid mE5+BM25 (không đổi winner Round 1).

**SoT đầy đủ (R1 + R1b + catalog):** [`07_MODEL_CATALOG_AND_RESULTS.md`](07_MODEL_CATALOG_AND_RESULTS.md).
