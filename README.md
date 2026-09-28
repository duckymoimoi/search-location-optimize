# SEARCH 2.0 — Tìm địa điểm cho ride-hailing (Việt Nam)

Ô tìm điểm đến nằm đầu phễu đặt xe. Người dùng gõ dở / sai dấu / viết tắt; hệ thống phải gợi ý đúng địa điểm đủ nhanh khi đang gõ.

Ba nguồn khó khác gốc (không giải bằng một model duy nhất):

| Nguồn | Ví dụ | Bản chất |
|---|---|---|
| Cách gõ | `vạn hanjh`, `s702`, Telex | Văn bản / nhiễu |
| Cùng tên nhiều chỗ | `vincom`, `sư vạn hạnh` | Không gian–thời gian–hành vi |
| Độ phủ & chất lượng data | thiếu địa chỉ, near-dup OSM | Kho dữ liệu |

**Kiến trúc:** Stage 1 retrieval (text → candidate) tách khỏi Stage 2 ranking (geo / time / thói quen).  
Chi tiết: [`docs/specs/search2.0.md`](docs/specs/search2.0.md).

---

## Quy trình ngắn (hiện tại)

```text
1. Corpus toàn quốc vn-poi-core-v3 (179,209 POI)
2. Gold POI v2.2 reissue: 200 POI · 800 session · 820 qrel
3. Gold brand v1: 70 family · 248 query · 6,610 qrel
4. Docker demo: Elasticsearch 9 + mE5 + FE/BE
5. E0 baseline đã chạy; POI-only hard-neg 6k là diagnostic, E1 POI+brand gated
```

Tree hiện hành chỉ giữ **một bộ** (corpus v3 + Gold v2.1 + brand v1). Bản cũ nằm trong git history.

| Artifact | Path |
|---|---|
| Corpus | `data/vietnam/poi_corpus_v3/` |
| Admin | `data/vietnam/admin_regions_v1/` |
| Gold POI | `data/vietnam/stage1_eval_suite_v2/gold_stage1_v2_2/` |
| Gold brand | `data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1/` |
| Embeddings (mE5, local) | `artifacts/embeddings/me5_small_v3/` |
| W1 evidence | `docs/deliveries/w1/` |
| W2/W3 evidence | `docs/deliveries/w2/`, `docs/deliveries/w3/` |
| Protocol chọn model | `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md` |
| App FE + BE | `apps/poi-search/` |

Trạng thái triển khai: [`docs/as-built/CURRENT_STATE.md`](docs/as-built/CURRENT_STATE.md).

Bàn giao theo yêu cầu SEARCH 2.0: **[hồ sơ W1–W6](docs/deliveries/README.md)** — output, evidence, gate và phần còn thiếu của từng tuần.

Stage 1 hiện có [báo cáo retrieval và candidate bàn giao](docs/deliveries/w3/05_STAGE1_HANDOFF.md).
Trước khi dùng bản này làm release, đọc [biên bản kiểm tra và giới hạn](docs/operations/STAGE1_SOURCE_RELEASE_CHECKLIST.md):
retrieval đã kiểm tra offline/live, Stage 2 chưa train/triển khai, provenance Gold POI v2.1 còn pending.
Model/tokenizer, vectors, trace benchmark và payload Kaggle sinh lại nằm ở local; mã nguồn chứa cấu hình, recipe, manifest và evidence summary.

---

## Cấu trúc repo

| Thư mục | Vai trò |
|---|---|
| `apps/poi-search/` | FastAPI + React/MapLibre + Docker Compose (ES9 / indexer / api / web) |
| `data/vietnam/` | Corpus, admin, gold Stage 1 |
| `docs/` | Specs, W1 evidence, as-built |
| `training/kaggle/` | Package + kernel Round 1 / 1b |
| `training/corpus_audit/` | Script build corpus / admin |
| `tools/` | Build/validate/lock corpus, Gold, brand |
| `.cursor/skills/` | Skill viết query POI và brand |

---

## Cài đặt

### Yêu cầu

- Python 3.11+ (khuyến nghị), `pip`
- Node.js 20+ (chỉ khi build FE ngoài Docker)
- Docker Desktop
- (Tuỳ chọn) [Kaggle CLI](https://github.com/Kaggle/kaggle-api) + GPU quota để encode / Round 1

### Python deps (bench / encode)

```powershell
python -m pip install pandas pyarrow numpy rank_bm25
# encode local: torch, transformers
```

### Kiểm tra gold đã khóa

```powershell
python -X utf8 tools\reissue_gold_stage1_v22.py verify
python -X utf8 tools\validate_gold_stage1_brand_v1.py --release-dir data/vietnam/stage1_eval_suite_v2/gold_stage1_brand_v1 --require-lock --report artifacts/results/brand_validation.json
```

---

## Chạy demo (Docker all-in-one)

1. Chuẩn bị embeddings mE5 (~179k × 384) tại `artifacts/embeddings/me5_small_v3/`:

```powershell
python apps\poi-search\scripts\encode_me5_corpus.py
```

2. Start stack:

```powershell
cd apps\poi-search
.\scripts\start.ps1
```

`start.ps1` sẽ: stage embeddings nếu thiếu (từ Kaggle output), `compose up` Elasticsearch → indexer → api → web.

| URL | Service |
|---|---|
| http://127.0.0.1:5173 | Web (nginx) |
| http://127.0.0.1:8000/health | API hybrid |
| http://127.0.0.1:9200 | Elasticsearch 9.5.3 |

Rebuild index:

```powershell
$env:RECREATE_INDEX = "1"
.\scripts\start.ps1
```

Smoke:

```powershell
python apps\poi-search\bench\smoke_contract.py
```

Chi tiết: [`apps/poi-search/README.md`](apps/poi-search/README.md).

### Đánh giá Stage 1 (không cần Docker app)

```powershell
python training\kaggle\prepare_kaggle_gold_stage1_w1.py
python -m kaggle kernels push -p training\kaggle\kernel_gold_stage1_w1
python apps\poi-search\bench\gold_stage1_selection_report.py
```

---

## Tài liệu

| Mục | Link |
|---|---|
| Mục lục docs | [`docs/README.md`](docs/README.md) |
| Vision / kiến trúc | [`docs/specs/search2.0.md`](docs/specs/search2.0.md) |
| ES baseline method (W2) | [`docs/specs/SEARCH_2.0_W2_ZERO_SHOT_BASELINE_METHOD.md`](docs/specs/SEARCH_2.0_W2_ZERO_SHOT_BASELINE_METHOD.md) |
| W1 evidence | [`docs/deliveries/w1/`](docs/deliveries/w1/) |
| Kế hoạch W1–W6 | [`docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md`](docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md) |

EDA mới nhất: [31 bảng dataset và audit leakage](docs/deliveries/w1/eda/README.md).
