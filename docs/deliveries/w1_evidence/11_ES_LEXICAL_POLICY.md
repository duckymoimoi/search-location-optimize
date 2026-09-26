# Gold Stage-1 — ES lexical + search_policy

**Policy:** `search-policy-stable-demo-v6` · index `vn-poi-core-v1-me5-small` · n=1080

Production path: `search_policy.json` → `lexical_body` (exact / phrase / prefix / AND / fuzzy / rewrites / MSM).

## Gate (production policy as-is)

| Profile | R@20 | R@50 | R@100 | R@1000 | K@95 | MRR@10 | rescue@100 |
|---|---:|---:|---:|---:|---:|---:|---:|
| es_policy (MSM default) | 0.134 | 0.134 | 0.134 | 0.134 | — | 0.131 | 4 |
| es_policy MSM=1 (ablation) | 0.440 | 0.448 | 0.451 | 0.465 | — | 0.389 | — |
| offline BM25 passage (L1) | 0.807 | 0.873 | 0.906 | 0.974 | 313 | 0.586 | 27 |
| mE5 dense | 0.945 | 0.961 | 0.969 | 0.990 | 23 | 0.861 | — |

## Diagnosis

1. **`minimum_should_match: 2` khi query >2 token** khiến nhiều query không match đủ ≥2 nhánh `should` → hit rỗng (R≈0.13).
2. Ngay cả **MSM=1**, R@1000 chỉ ~0.46 — vẫn kém xa BM25 passage offline, vì nhiều clause dùng `operator: and` trên **một** field (`search_label` không chứa đủ street tokens).
3. Offline fielded BM25 (L1) cũng thua passage; **ES+policy hiện tại chưa phải lexical floor tốt** trên gold này.
4. Hybrid API vẫn sống nhờ **dense mE5** kéo recall; lexical branch đang đóng góp ít trên gold full-query.

## Policy đã gắn lexical sẵn (không cần “thêm” từ đầu)

| Policy key | Vai trò trong `lexical_body` |
|---|---|
| `lexical.exact` / `alias_exact` | `term` trên `label_folded` / `aliases_folded` |
| `lexical.phrase` | `match_phrase` name |
| `lexical.and_match` | `multi_match` best/cross + AND |
| `lexical.prefix_field` / `leading_prefix` | edge-ngram / prefix fold |
| `lexical.fuzzy` | fuzzy AND (typo) — dense đã mạnh hơn trên TYPO |
| `query_rewrites` | bv→bệnh viện, thpt→… |

Chỉnh lexical = chỉnh JSON policy + (nếu cần) mapping analyzer — không train model.

## Related work

| Nguồn | Ý tưởng liên quan |
|---|---|
| [komoot/photon](https://github.com/komoot/photon) | Geocoder ES; boost có cấu trúc (housenumber ≫ street ≫ city); structured query params |
| [LFAS](https://github.com/maikereis/lfas) | BM25F field-aware + two-level retrieval cho địa chỉ |
| [ViDRILL VLSP 2025](https://aclanthology.org/2025.vlsp-1.17.pdf) | BM25 + multilingual dense + cross-encoder rerank (legal VI) |
| BM25F / fielded IR | Trọng số theo field — L1 offline thuần chưa thắng trên gold này |
| RRF hybrid | Đã có trong API; đo marginal gain = Round L2 |
| VN address FTS (PG unaccent + trigram) | Prefix/typo autocomplete — bổ sung analyzer, không thay dense |

## Next (policy tuning, không fielded BM25 thêm)

1. **Hạ / bỏ MSM≥2** trên full-query; giữ MSM chặt chỉ cho query rất ngắn nếu cần chặn noise.
2. Ưu tiên **cross_fields** name+address (Photon-style) thay vì AND trong một field.
3. Boost **housenumber / street / ref** khi parse được (structured clause) — học từ Photon/LFAS.
4. Giữ fuzzy nhẹ; không đầu tư synonym lớn (rescue diagnostic: dense đã cover ALIAS/TYPO).
5. Round L2: RRF(es_lexical_tuned, mE5) — chọn policy bằng **hybrid gain**.

Harness: `apps/poi-search/bench/gold_stage1_es_lexical_policy_bench.py`  
`.\scripts\search-dev.ps1 es-lexical`
