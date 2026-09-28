# W5 — Service và demo end-to-end

Cập nhật: 2026-09-28. **Có scaffold API/index/FE; chưa nghiệm thu service với Stage 2 cuối.** Người nhận/duyệt: chưa xác nhận. Yêu cầu: W5 [kế hoạch](../SEARCH_2.0_TONG_HOP_TASK.md), bước 5 [SEARCH 2.0](../../specs/search2.0.md).

## 1. Mục tiêu và input

Ghép offline indexing và online search thành service tái lập được, đo từng bước và thử lỗi thực tế. Input đã có: Stage 1, index/ID map, API/FE, policies. Input chưa có: ranking candidate W4 đã qua quality gate và feature snapshot phục vụ online.

## 2. Output/evidence hiện có

[Corpus/admin offline pipeline](03_CORPUS_ADMIN_PIPELINE.md): cleaner fixes, artifact verification và full-PBF admin rebuild đã kiểm tra; candidate chưa activate.

| Output | Evidence | Trạng thái |
|---|---|---|
| E2E API + FE | [App README](../../../apps/poi-search/README.md), [biên bản kiểm tra](../../operations/STAGE1_SOURCE_RELEASE_CHECKLIST.md) | Build/contract smoke đạt; chưa final Stage 2 integration |
| Vector index và offline job | [Indexer](../../../apps/poi-search/scripts/index_vn_poi.py), [compose devlock](../../../apps/poi-search/docker-compose.devlock.yml) | Index hiện có và code job; chưa có biên bản rebuild từ zero của final bundle |
| Ranking service | [Pipeline](../../../apps/poi-search/api/pipeline.py) | Raw/heuristic serving; chưa model W4 đã nghiệm thu |
| Fallback | Branch handling trong pipeline | Có code; chưa đủ fault-injection quality/latency từng bậc |
| Latency benchmark | [Execution report](../../operations/DENSE_FIRST_EXECUTION_STATUS_2026_09_28.md) | Closed-loop characterization đã chạy; SLA open-loop/soak chưa chạy |
| Demo v1 | Build FE, suggest/display/select, geo heuristic smoke | Một phần; chưa final bundle đủ 8 tình huống W6 |

## 3. Kết quả và quyết định

[Kết quả và quyết định](01_RUNTIME_AND_LATENCY.md)

## 4. Acceptance còn phải chạy

[Acceptance còn phải chạy](02_VERIFICATION_GATES.md)

## 5. Bàn giao W6

Serving/integration phụ trách G5. W6 nhận deployment bundle, config, start/rebuild commands, measured latency breakdown, fault-injection/rollback logs và demo scenario IDs. Mọi pending ở trên phải được nêu trong biên bản; không đánh dấu “demo đã có” thành “service cuối đã nghiệm thu”.
