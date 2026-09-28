# W2 — Kiểm kê và dọn artifact local

**Kiểm kê:** 2026-09-26. **Trạng thái:** đã dọn lượt ưu tiên (2026-09-26).
Các kích thước dưới đây là xấp xỉ từ file local, không phải dung lượng Git.

## Giữ — nguồn hiện hành hoặc evidence cần replay

| Nhóm | Path | Lý do |
|---|---|---|
| Hai tài liệu gốc | `docs/specs/search2.0.md`, `docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md` | Ràng buộc dự án; không sửa/xóa |
| W1/W2/W3 evidence | `docs/deliveries/w1_evidence/`, `w2_evidence/`, `w3_evidence/` | Bằng chứng bàn giao theo snapshot; W1 là lịch sử |
| Runtime/docs hiện hành | `apps/poi-search/`, `docs/as-built/CURRENT_STATE.md`, `docs/operations/PROJECT_STRUCTURE.md`, specs/schema liên quan | Code, contract và runtime truth |
| Corpus/admin/raw source | `data/vietnam/poi_corpus_v3/`, `admin_regions_v1/`, `vietnam-260910.osm.pbf` | Index/rebuild nguồn v3 |
| Gold đã khóa | `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_1/`, `gold_stage1_brand_v1/`, registry | Test set và hashes; không cắt CSV/Parquet trong release |
| Train hiện hành | `train_stage1_20k/`, `train_stage1_queries_v6/` **bản compile ở root**, brand membership/lookup/query/splits v3, POI+brand views, hardneg 5k | Source train/QA và E0/E1 views |
| Công việc đang làm | `data/vietnam/train_stage1_v6_hardneg_6k/`, `training/kaggle/dataset_stage1_v6_hardneg_6k/`, `kernel_stage1_v6_hardneg_6k/`, `prepare_kaggle_stage1_v6_hardneg_6k.py`, thay đổi ở hai tool hardneg | Đang untracked/modified; không đụng vào |
| Embedding runtime | `artifacts/embeddings/me5_small_v3/` (~264 MB) | Docker index/API hiện hành cần |
| Baseline W2 | `artifacts/results/gold_stage1_v21_docker_baseline/`, `gold_stage1_brand_v1_docker_baseline/` (~0,5 MB) | Machine evidence cho package này |
| Run 6k W3 | `training/kaggle/output_stage1_v6_hardneg_6k/` và `artifacts/results/kaggle_6k_version_352867030/` | Checkpoint, output đầy đủ và bản đối chiếu đúng Kaggle version; chưa là release model |

## Ứng viên dọn sau khi chốt khả năng replay

| Path/nhóm | Dung lượng | Điều kiện trước khi xóa |
|---|---:|---|
| `.pytest_cache/`, `.ruff_cache/`, các `__pycache__/` trong workspace | ~1 MB | Cache tái tạo; có thể xóa ngay khi công cụ cho phép |
| `data/vietnam/train_stage1_queries_v6/staging/` | ~120 MB/1.264 file | Chỉ xóa batch đã có manifest/final compile và không còn script hiện hành cần đọc; hiện ít nhất `audit_gold_stage1_v21_draft.py`, `stage1_v6_500_baseline.py` và `verify_stage1_targets_corpus_v2.py` còn trỏ vào staging |
| `artifacts/results/` ngoài hai baseline Gold v3 | ~88 MB tổng results (trong đó ~29 MB prefix-char W1, ~53 MB pilot400) | Giữ số liệu W1 được dẫn trong docs hoặc xác nhận có thể tái tải; không xóa per-query evidence còn dùng để audit |
| Năm file `embedding_dense_*.npy` trong `training/kaggle/output_gold_stage1_w1/gold_stage1_w1/` (4 file) và `output_gold_stage1_w1b/gold_stage1_w1/` (1 file) | ~2,09 GB | Không có script/docs hiện hành trỏ trực tiếp vào các array; giữ summary/run JSONL và Kaggle source để tái tải; đây là ứng viên giải phóng dung lượng lớn nhất |
| `training/kaggle/output_stage1_v6_e5/` | ~473 MB | Có checkpoint fine-tuned ~449 MB; không coi là cache cho đến khi quyết định giữ/archival checkpoint và đối chiếu W3 |

Không xóa một folder chỉ vì tên `output_` hay `staging`: nhiều file là input
cho audit/script lịch sử. Không xóa phiên bản Gold hoặc membership đã khóa
trong `data/vietnam`; các bản cũ thực sự đã được gỡ khỏi tree hiện hành và
còn trong Git history. Khi dọn material, ghi `path`, kích thước, hash nguồn,
lý do và cách phục hồi (Git/Kaggle/rebuild) trước khi xóa; sau đó chạy lại
manifest/Gold verifier và kiểm tra link của W1/W2 evidence.

### Danh sách file cụ thể ưu tiên dọn

Năm corpus-vector cũ dưới đây là output có thể tái tải từ Kaggle/W1 kernel;
W1 evidence đọc `summary*.json` và `run_*.jsonl`, không đọc trực tiếp chúng:

```text
D:\vsf\training\kaggle\output_gold_stage1_w1\gold_stage1_w1\embedding_dense_bekko_a25m_exact.npy  272,93 MiB
D:\vsf\training\kaggle\output_gold_stage1_w1\gold_stage1_w1\embedding_dense_bekko_a8m_exact.npy   272,93 MiB
D:\vsf\training\kaggle\output_gold_stage1_w1\gold_stage1_w1\embedding_dense_halong_exact.npy      545,87 MiB
D:\vsf\training\kaggle\output_gold_stage1_w1\gold_stage1_w1\embedding_dense_me5_exact.npy         272,93 MiB
D:\vsf\training\kaggle\output_gold_stage1_w1b\gold_stage1_w1\embedding_dense_bge_m3_exact.npy     727,82 MiB
```

Tổng khoảng **2.092,48 MiB**. Có thể dọn tiếp năm
`query_embedding_dense_*.npy` trong đúng hai folder trên (~12 MiB) nếu không
cần replay W1 ngay; giữ `summary*.json`, `gate_table.json`, `run_*.jsonl` và
`poi_ids.parquet` để kiểm toán số liệu. Không xóa nguyên hai folder.
**Lượt 2026-09-26:** đã xóa 5 `embedding_dense_*.npy` và 5
`query_embedding_dense_*.npy`.

Output benchmark cũ có thể tái chạy và không được docs hiện hành tham chiếu:

```text
D:\vsf\artifacts\results\stage1_v6_pilot400_baseline\            52,97 MiB
D:\vsf\artifacts\results\stage1_v6_hard_noise_500_baseline_smoke\  0,06 MiB
```

`stage1_v6_pilot400_baseline/run_lexical_bm25.jsonl` chiếm 52,93 MiB;
muốn giữ `summary_bm25.json`, `summary_docker_serving.json` và
`quality_audit.md` thì chỉ dọn file JSONL này. Cache `__pycache__`,
`.pytest_cache`, `.ruff_cache` tổng khoảng 1 MiB là an toàn tái tạo.
**Lượt 2026-09-26:** đã xóa JSONL pilot400, cả folder smoke, và các cache đó.

**Chưa dọn** `data/vietnam/train_stage1_queries_v6/staging/` (~119,85 MiB):
003–011 là nguồn authoring được manifest train v6 ghi nhận; script audit/benchmark cũ
còn đọc ít nhất batch 003. Batch `001` (~6,09 MiB) bị loại khỏi bản publish,
nhưng chỉ nên dọn khi đã xác nhận không cần nguyên liệu QA đó. Cũng **giữ**
`training/kaggle/output_stage1_v6_e5/` (~472,54 MiB) và output/checkpoint
hardneg 5k/6k để làm đối chứng W3; không coi checkpoint là cache.

## Kết quả lượt này

- Đã kiểm kê nguồn hiện hành và tách rõ 6k đang làm khỏi artifact lịch sử.
- Đã tạo W2 evidence package nhưng không copy corpus, embeddings hay per-query
  output vào docs.
- Đã giữ checkpoint/output 6k và summary lấy lại từ đúng Kaggle version
  `352867030` vì còn cần audit/sửa protocol và đối chứng tiếp.
- **Đã xóa lượt ưu tiên:** 25 path, **2.158,77 MiB** (2.263.637.267 byte).
  Không đụng staging train v6, Gold lock, embedding runtime, baseline W2,
  output/checkpoint e5 và hardneg 5k/6k.

### Đã xóa — vector W1 (tái tải từ Kaggle)

Nguồn: kernel `hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25`, dataset
`hiengchi/vn-poi-gold-stage1-w1`. Giữ `summary*.json`, `run_*.jsonl`,
`gate_table.json`, `poi_ids.parquet`.

| Path | Bytes | Lý do |
|---|---:|---|
| `training/kaggle/output_gold_stage1_w1/gold_stage1_w1/embedding_dense_bekko_a25m_exact.npy` | 286.190.720 | Corpus vector; không script/docs hiện hành đọc |
| `.../embedding_dense_bekko_a8m_exact.npy` | 286.190.720 | như trên |
| `.../embedding_dense_halong_exact.npy` | 572.381.312 | như trên |
| `.../embedding_dense_me5_exact.npy` | 286.190.720 | như trên |
| `training/kaggle/output_gold_stage1_w1b/gold_stage1_w1/embedding_dense_bge_m3_exact.npy` | 763.175.040 | như trên; output W1b |
| `.../query_embedding_dense_*.npy` (5 file, hai folder) | 12.719.720 | Query vector tùy chọn; không replay W1 ngay |

### Đã xóa — benchmark cũ / cache

| Path | Bytes | Lý do / phục hồi |
|---|---:|---|
| `artifacts/results/stage1_v6_pilot400_baseline/run_lexical_bm25.jsonl` | 55.497.049 | Per-query dump cũ; giữ `summary_bm25.json`, `summary_docker_serving.json`, `quality_audit.md`; rerun BM25 nếu cần |
| `artifacts/results/stage1_v6_hard_noise_500_baseline_smoke/` | 66.259 | Smoke không được docs hiện hành dẫn; rerun smoke |
| `.pytest_cache/`, `.ruff_cache/`, 11 `__pycache__/` | ~1,2 MiB | Cache tái tạo |

### Kiểm tra sau dọn

- Train v6 published `query_variants.csv` / `.parquet`: hash khớp manifest.
- W2 baseline SHA-256 khớp `02_BASELINE_AND_FAILURES.md`.
- Link W1 còn đọc được: `summary_partial.json`, `summary.json`,
  `run_dense_me5_exact.jsonl`, `run_lexical_bm25.jsonl` (W1),
  `gold_stage1_prefix_char/summary.json`.
- `python -X utf8 tools/verify_gold_stage1_v21_release.py` **FAIL sẵn** (không
  do lượt dọn): thiếu `gold_stage1_v2/manifest.json` và
  `stage1_eval_suite_v2/staging/gold_stage1_v2_1/{authoring_packet.jsonl,
  authoring_packet_manifest.json, target_overrides_v1.json}`; thêm
  `gold_stage1_v2_1/README.md` lệch hash artifact. Core Gold parquet/CSV/lock
  vẫn còn trên disk.
