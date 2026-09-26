# Gold Stage-1 — Lexical L1 local experiments

**Mode:** local CPU · no Kaggle · n=1080 · depth=1000
**Corpus:** `/repo/data/vietnam/poi_corpus_v1/search_documents.parquet` (186322 docs)

Objective L1: ↑ R@20/50/100 · ↓ K@95 · ↑ MRR@10 · giữ R@1000 ≥ baseline · bảo toàn rescue ORTHO.

## Gate

| Variant | R@20 | R@50 | R@100 | R@1000 | K@95 | MRR@10 | rescue@100 | ortho@100 | Δoracle@100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline_passage` | 0.807 | 0.873 | 0.906 | 0.974 | 313 | 0.586 | 27 | 27 | +0.025 |
| `fielded_v1` | 0.775 | 0.857 | 0.891 | 0.956 | 673 | 0.555 | 26 | 25 | +0.024 |
| `fielded_shortnorm` | 0.762 | 0.840 | 0.881 | 0.956 | 842 | 0.541 | 26 | 25 | +0.024 |
| `fielded_exact` | 0.762 | 0.852 | 0.890 | 0.956 | 676 | 0.549 | 26 | 25 | +0.024 |
| `name_addr_heavy` | 0.761 | 0.840 | 0.878 | 0.956 | 622 | 0.540 | 26 | 25 | +0.024 |

## Verdict

- **L1 winner (local):** `baseline_passage` — R@100=0.906, K@95=313, MRR@10=0.586, R@1000=0.974, rescue@100=27.
- Chưa phải winner production — cần Round L2 hybrid với mE5 trước khi khóa analyzer/ES boosts.
- Baseline R@1000 = 0.974 (floor screening Round-1).

## ORTHOGRAPHIC_IME R@100 (preserve advantage)

| Variant | R@100 ORTHO |
|---|---:|
| `baseline_passage` | 0.953 |
| `fielded_v1` | 0.937 |
| `fielded_shortnorm` | 0.927 |
| `fielded_exact` | 0.930 |
| `name_addr_heavy` | 0.927 |

## Next

- Chọn winner L1 theo gate trên (ưu tiên R@100 + K@95 + rescue, không chỉ R@1000).
- Round L2: đo hybrid RRF với mE5 trên máy local (ES hoặc fusion offline) — winner cuối = hybrid gain.
- Kaggle chỉ khi train/fine-tune encoder.

