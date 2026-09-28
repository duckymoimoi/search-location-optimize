# Biên bản kiểm tra Stage 1 và chuẩn bị bản mã nguồn GitHub

Ngày: 2026-09-28. Nhánh chuẩn bị: `release/stage1-verified-handoff`.

**Cập nhật sau khi người dùng chọn tái phát hành:** Gold POI v2.2 đã build/verify PASS và dựng lại byte-identical ở thư mục khác; registry trỏ v2.2. Historical verifier v2.1 vẫn FAIL như bên dưới, không sửa validator cũ. Đây là regression reissue từ nhãn đã có, không phải holdout mới hoặc independent label review. [EDA mới của 40 bảng](../deliveries/dataset_eda_20260928/README.md) bổ sung inventory, missingness và leakage; clone Git sạch đã chạy 78 tests PASS trước khi thêm reissue, cần kiểm tra lại bản cuối có reissue.

**Trạng thái: bản mã nguồn nghiên cứu để review; chưa sign-off release dữ liệu/sản phẩm.** Stage 2 chưa được train hoặc triển khai. Việc kiểm tra dưới đây xác nhận candidate và serving của Stage 1 có thể tái lập; không chứng minh chất lượng Stage 2 hoặc SLA.

## Kiểm tra thực tế

| Kiểm tra | Kết quả |
|---|---|
| Replay độc lập trên 3.600 POI dev +126 brand dev +660 stress | 4.386 query; metric của cả `gated_candidate` và `hybrid_raw` khớp snapshot; ID duy nhất, thuộc corpus, depth ≤100 |
| S1-A API GPU so với trace offline | 190/190 query khớp count, candidate prefix 80, debug top 10 và serving top 10; toàn bộ 126 brand dev +32 POI dev +32 stress |
| S1-B API GPU so với trace offline | 190/190 query khớp cùng các kiểm tra; policy control chạy hybrid cả query ngắn để đúng phép đo offline |
| Algorithm / evaluator / training-weight / data tools | 78 tests pass sau sửa serializer phụ thuộc Gold v2 đã bỏ |
| API contract + geo smoke | `ALL_SMOKE_PASSED` với hybrid/current/glue trên index devlock; là smoke heuristic hiện có, không phải chứng minh ranker học |
| Smoke geo trên raw profile | Không đạt điều kiện geo vì profile raw cố ý không áp dụng geo; giữ nguyên test và chạy đúng cấu hình current để nghiệm thu phần đó |
| FE | TypeScript + Vite build pass; còn cảnh báo bundle >500 kB |
| Python | Fatal lint và compile pass |
| Gold brand v1 | Locked verifier PASS: 70 family, 248 query, 6.610 qrel |
| Gold POI v2.1 | Full verifier FAIL: README lệch hash; thiếu 4 nguồn provenance. Không đổi validator/manifest/qrels để ép pass |
| SLA | Chưa chạy open-loop/soak; chỉ có characterization lịch sử |

Hai lần kiểm tra live dùng API cách ly 8003, inference trên checkpoint đã tải; không train local. Test sample không phải full live benchmark mọi query hay đánh giá chất lượng độc lập. Debug response cắt stage ở 80 nên kiểm tra prefix 80 + tổng count; không tuyên bố đã so thứ tự toàn bộ 100 ID qua HTTP.

Evidence mới: [verification_summary.json](../deliveries/stage1_handoff_20260928/verification_summary.json). Trace live chi tiết local nằm trong `artifacts/results/dense_first/handoff_verification_s1a_20260928/` và `handoff_verification_s1b_20260928/`. Snapshot lịch sử vẫn giữ nguyên; không ghi đè run cũ.

## Lỗi đã sửa trong vòng kiểm tra

- Compose cách ly dùng đúng S1-A mặc định, branch/candidate depth 100 được đưa vào file policy theo Git. Trước đó default là dense-only và policy cần artifact local.
- Thêm policy S1-B control để tái lập hybrid raw, kể cả query ngắn; không đổi policy demo.
- Serializer draft Gold v2.1 đọc schema từ release v2.1 hiện hành, không phụ thuộc thư mục Gold v2 đã xóa.
- Sửa return annotation không tồn tại trong parser; mô tả API không còn ghi geo heuristic khi raw profile đang tắt geo.
- FE giữ `VITE_API_BASE_URL` khi khởi tạo backend mặc định; khi đổi backend, hủy request cũ và bỏ session cũ trước tạo session mới.

## Giới hạn Gold POI phải giải quyết trước sign-off

`verify_gold_stage1_v21_release.py` vẫn là gate nguyên bản. Những mục chưa khớp:

1. `gold_stage1_v2_1/README.md` khác hash trong manifest.
2. `gold_stage1_v2/manifest.json` thiếu bản đúng hash.
3. `staging/gold_stage1_v2_1/authoring_packet.jsonl` thiếu bản đúng hash.
4. `staging/gold_stage1_v2_1/authoring_packet_manifest.json` thiếu bản đúng hash.
5. `staging/gold_stage1_v2_1/target_overrides_v1.json` thiếu bản đúng hash.

Đã tìm trong lịch sử reachable và 2.859 blob Git dưới 5 MB, thử cả LF/CRLF; chưa có bản khớp hash. Không dựng lại nhãn hay re-lock dataset để thay chứng cứ gốc. Cần bản backup đúng hash, hoặc một quy trình phát hành dataset mới có review độc lập; chưa làm lựa chọn thứ hai.

## Dọn bản mã nguồn

- Giữ mọi file local; chỉ bỏ tracking 13 bản payload CSV/parquet trùng lặp trong `training/kaggle/dataset_*`. Metadata, manifest, recipe và kernel còn trong Git.
- Ignore model/tokenizer, vectors, benchmark traces/results, staging và các view parquet diagnostic mới. Giữ corpus/Gold canonical vốn đã được tracking; không xóa CSV canonical có hash trong Gold manifest.
- `.gitattributes` giữ nguyên byte của data và schema đã khóa qua Windows/Linux. Không rewrite Git history; file lớn đã nằm trong lịch sử vẫn còn trong lịch sử.
- Thêm CPU regression và FE build workflow. Workflow chưa chạy trên GitHub cho đến khi push; kiểm tra local không được mô tả là GitHub CI đã pass.
- Không đổi demo default, không gắn tag production. Bản source có thể review cùng lỗi provenance đã công khai; không gắn nhãn release hoàn chỉnh.

## Tái chạy

Từ root repo, cài CPU deps bằng `python -m pip install -r requirements-dev.txt`. Unit checks không cần checkpoint hoặc GPU; inference live cần Docker GPU, model devlock, brand lookup và index 179.209 POI. Các artifact ngoài Git phải lấy đúng hash trong [snapshot](../deliveries/stage1_handoff_20260928/evidence_snapshot.json), không tự thay bằng checkpoint mới.

```powershell
# S1-A: compose mặc định dùng cấu hình bàn giao, không phụ thuộc DF_* của phiên trước.
Remove-Item Env:DF_RETRIEVAL_PROFILE, Env:DF_RANKING_PROFILE, Env:DF_ENCODER_NORMALIZER, Env:DF_POLICY -ErrorAction SilentlyContinue
docker compose -f apps/poi-search/docker-compose.devlock.yml up -d elasticsearch
docker compose -f apps/poi-search/docker-compose.dense-first.yml up -d --build api
python tools/verify_stage1_handoff.py --api http://127.0.0.1:8003 --out artifacts/results/dense_first/verify_s1a_new

# S1-B: same model/index, hybrid candidate control trước reranking.
$env:DF_RETRIEVAL_PROFILE='hybrid'
$env:DF_POLICY='/repo/apps/poi-search/api/search_policy.stage1-hybrid-control.json'
docker compose -f apps/poi-search/docker-compose.dense-first.yml up -d --no-build api
python tools/verify_stage1_handoff.py --api http://127.0.0.1:8003 --profile s1-b --out artifacts/results/dense_first/verify_s1b_new
```

Đợi `/health` ready trước chạy verifier. Thư mục `--out` phải mới để giữ evidence bất biến. Verifier cần full trace local đã hash trong snapshot; nếu chỉ clone GitHub thì chạy được CPU checks nhưng chưa chạy lại benchmark đầy đủ. Dataset Kaggle là bản sao sinh từ các script `training/kaggle/prepare_*.py`; model/vector lấy từ run đã chọn, không train local để bù artifact thiếu.
