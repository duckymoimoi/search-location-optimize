# Kế hoạch benchmark và origin-aware dense

Revision 15/09/2026; review repo commit `50394ab374ae1028afa21a47758fadb188d00bd1`. Plan theo ý tưởng đã chốt: **train dense với query+origin, lexical+policy, RRF hai nhánh; Stage 2 time/history sau**. Không thêm RRF3. Không thay serving code hoặc push GitHub trong lượt chỉnh tài liệu.

## 1. Kết luận từ code hiện tại

| Phát hiện | Bằng chứng trong repo | Hệ quả cho vòng thử |
|---|---|---|
| Runtime là geo-v5, chưa phải v6 | `apps/poi-search/api/app.py::versions/rank_candidates`; policy geo_blend=0.35 | Freeze đúng commit/policy trước so sánh; v6 chỉ là challenger |
| Geo nhận điểm dù không khớp chữ nếu query không có số | `compatible=all(...)` trên structured tokens rỗng; không nhân geo bằng text compatibility | POI gần nhưng không liên quan có thể vượt tên exact xa; sửa/đánh giá compatibility trước tăng geo |
| “Protect exact” chỉ nâng text_rel, không bảo vệ hạng | `rank_candidates` vẫn sort điểm blend cuối | Không dùng tên flag để kết luận explicit query được bảo toàn |
| Runtime và evaluator dựng lexical DSL riêng và khác nhau | `api/app.py::lexical_body` có supplementary expansion/cross-fields và fuzzy alpha-only; `training/stage1/evaluate_stage1_branches.py::lexical_body` còn fuzzy cả address | Cùng tên L1/policy chưa đủ tái lập; cần parity hoặc báo rõ hai baseline |
| API quality/load gọi personalized với origin cố định | `apps/poi-search/bench/bench_quality_runtime_load.py::suggest`, ORIGIN và SAMPLE_PER_SLICE=40 | Không dùng kết quả đó như metric Stage 1 query-only hoặc context-gold |
| Training hiện là positive-pair diagonal CE với in-batch negatives | `training/stage1/train_stage1.py` train loop | Chưa có explicit mined hard negatives/multi-positive masked objective |
| Có kiểm soát collision trong batches | `make_unique_batches` loại target/entity/query/compatible-set trùng | Giữ logic hữu ích này, không khẳng định trainer hiện hoàn toàn bỏ qua false negatives |
| Checkpoint v4 dùng dataset/corpus trước stable | `artifacts/models/e5-v4-finetuned/config_resolved.json` và as-built evaluation | Trước retrain phải migrate stable eligibility/passages, không chạy lại config v4 nguyên xi |

Kiểm tra trực tiếp các hàm của `app.py` bằng AST, không load encoder/index: query exact “Trường Tiểu học Đại Mỗ”, candidate exact khoảng 20 km với normalized RRF=1, candidate “Quán cà phê” ngay origin với RRF=0.95. Hàm trả near_unrelated 0.7514 > far_exact 0.6824. Đây là phản ví dụ synthetic ở mức scorer, không chứng minh index thực đã retrieve cặp này. Nó chứng minh exact protection chưa phải invariant.

Báo cáo frozen dev hiện có hybrid Hit@50=0.99724 nhưng autocomplete Hit@5=0.60067 < lexical 0.68792; ANN/exact overlap khoảng 0.99855. Nguồn: `docs/as-built/STAGE1_EVALUATION.md`. Đây là weak-label snapshot cũ: ưu tiên policy/parity/autocomplete và geo trước thay encoder/ANN; không suy khả năng tổng quát từ test gần 1.0.


## 2. P0 — khóa và làm cho benchmark phản ánh runtime

Đầu ra: `run_manifest.json`, shared query builder, parity tests và candidate trace contract.

- Pin git SHA, code/policy/index mapping hashes, checkpoint/tokenizer/passage/vector-ID hashes, corpus/dataset/qrels version, seeds, eligible counts, hardware và runtime precision. Weight files/index chưa khả dụng ở máy chạy thì fail preflight, không dùng mock vectors.
- Tách pure builders/fusion/dedup từ `api/app.py` sang `api/search_core.py` hoặc shared package import được bởi trainer/evaluator mà không instantiate Runtime. API giữ wrappers/HTTP schema. E5 load không nên là điều kiện để import test DSL.
- Sửa `evaluate_stage1_branches.py` và `prepare_stable_branch_cache.py` dùng chung builders hiện hành; giữ artifact old baseline nguyên trạng. Kiểm tra alias/ref/address/IME/typo/số/prefix 1–8. Exact quality phải dùng query encode và POI passage giống runtime.
- Thêm `--endpoint query-only|personalized`, `--origin-fixtures`, `--policy/manifest` vào benchmark API. Query-only origin=null; context endpoint chỉ tính intended accuracy khi có context qrels. Thay observed_at hardcoded bằng request-time hoặc fixture clock rõ ràng.
- Trace nội bộ mỗi query/POI: branch ranks/scores/masks, rank sau RRF, sau entity collapse, sau cap, geo compatibility/reason, distance, final rank; record removed IDs/reasons. Public API không cần thêm fields.
- Empty/error/degraded giữ trong mẫu số end-to-end; rejected/invalid fixture report riêng. “Cold” phải ghi chính xác process/index/query cache nào reset; nếu chỉ first pass thì gọi first-pass.

Pass: same input/config → DSL/candidate order parity; query-only không chịu ảnh hưởng origin; mọi thay đổi ID/rank trace được; schema HTTP giữ nguyên. Chưa tune geo/model ở P0.


## 3. Thứ tự triển khai mới

| Mốc | Công việc | Đầu ra |
|---|---|---|
| P0 | Runtime/eval parity và freeze baseline | Shared builders, trace snapshots, manifest |
| P1 | Context pilot 2k–3k, split/rubric/sampler và baseline replay | Context requests/qrels, origin-sensitive/invariant/null/remote reports |
| P2 | Stable migration, mixed negatives/masks; train O1 query-side adapter trước | Mining manifest, adapter bundle, exact dense/hybrid benchmark |
| P3 | Mở rộng train15k–25k nếu pilot tốt; thử O2 nếu frozen POI space hạn chế | Model/space mới và index rebuild nếu cần |
| P4 | Khóa model, ANN/parity/load/cache tests, explicit/null/cold gates | Release decision hoặc giữ baseline |
| P5 | Time/history ranker trên candidates mới đã khóa | Stage 2 dataset và learned personalization |

Chi tiết kiến trúc O1/O2, quota dataset, loss/dropout, caches, guards và CI: [Origin-aware dense](../specs/ORIGIN_AWARE_DENSE.md). Đây là nguồn chuẩn cho vòng này; không triển khai plan RRF3/rescue/learned-geo bắt buộc trước đó.

## 4. Files dự kiến sửa/tạo khi bắt đầu code

- `apps/poi-search/api/search_core.py`: shared lexical/RRF/dedup; wrappers API giữ schema.
- `training/stage1/evaluate_stage1_branches.py`, `prepare_stable_branch_cache.py`: dùng shared builders, cache có origin hash cho dense mới.
- `apps/poi-search/bench/bench_quality_runtime_load.py`: endpoint/origin fixtures, full dev quality và load mode riêng.
- `training/stage1/prepare_context.py`, `mine_negatives.py`: context sidecars, train-only pools và masks.
- `training/stage1/train_origin_dense.py`: O1 adapter/frozen POI; O2 là arm riêng, không ghi đè baseline trainer/checkpoint.
- Encoder adapter/manifest trong API: nhận resolved_origin, space compatibility; query-only ép null.

Không đổi corpus 18 cột hoặc schema public vì thêm metadata training. Các files trên là đầu việc, chưa được tạo trừ plan/spec. Không cần thêm model serving thứ ba.
