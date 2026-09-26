# Gold Stage-1 — Lexical structure iteration (ES) + hybrid RRF

n=1080 · index=`vn-poi-core-v1-me5-small` · RRF k=60 · dense=frozen mE5 top-1000

Mỗi bước đo **lexical riêng** và **hybrid = RRF(lexical, mE5)**.

## Gate

| Variant | lex R@100 | lex R@1000 | lex K@95 | lex MRR@10 | hyb R@100 | hyb R@1000 | hyb K@95 | hyb MRR@10 | rescue@100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `v0_current` | 0.134 | 0.134 | None | 0.131 | 0.972 | 0.992 | 20 | 0.871 | 4 |
| `v1_msm1` | 0.451 | 0.465 | None | 0.389 | 0.981 | 0.992 | 12 | 0.805 | 15 |
| `v2_cross_or` | 0.890 | 0.945 | None | 0.646 | 0.987 | 0.994 | 25 | 0.757 | 25 |
| `v3_context_or` | 0.898 | 0.948 | None | 0.659 | 0.987 | 0.994 | 25 | 0.764 | 26 |
| `v4_photonish` | 0.946 | 0.981 | 126 | 0.727 | 0.990 | 0.999 | 15 | 0.810 | 28 |

## Winner

- **Winner:** `v4_photonish` — hybrid R@100=0.990 R@1000=0.999 K@95=15 MRR@10=0.810.
- Lexical riêng: R@100=0.946 R@1000=0.981 K@95=126.
- Vs v0: hyb R@100 0.972→0.990, lex R@100 0.134→0.946.

## Variant notes

- `v0_current` — production policy body (MSM≥2, field AND)
- `v1_msm1` — same clauses, MSM=1
- `v2_cross_or` — cross/best OR, no field AND, MSM=1
- `v3_context_or` — v2 + `context_text` match (passage-like)
- `v4_photonish` — stronger exact/phrase/cross + context, no fuzzy

