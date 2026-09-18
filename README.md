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
1. Corpus toàn quốc vn-poi-core-v1 (~186k POI)
2. Gold Stage 1 khóa: 180 case × 6 variant = 1,080 query
3. Round 1 — zero-shot screen (BM25 + dense exact) trên Kaggle
4. Round 1b — prefix-char (FHC / SHC / PrefixAUC)
5. VERDICT model Stage 1 → nối lại FE/BE + rebuild index
6. W2+ baseline / train / ranking / E2E demo
```

| Artifact | Path |
|---|---|
| Corpus | `data/vietnam/poi_corpus_v1/` |
| Admin | `data/vietnam/admin_regions_v1/` |
| Gold | `data/vietnam/gold_stage1_v1/` |
| W1 evidence | `docs/deliveries/w1_evidence/` |
| Protocol chọn model | `docs/specs/SEARCH_2.0_STAGE1_MODEL_SELECTION_PROTOCOL.md` |
| App FE + BE | `apps/poi-search/` |

Trạng thái triển khai: [`docs/as-built/CURRENT_STATE.md`](docs/as-built/CURRENT_STATE.md).

---

## Cấu trúc repo

| Thư mục | Vai trò |
|---|---|
| `apps/poi-search/` | FastAPI + React/MapLibre demo, Docker Compose API/OpenSearch |
| `data/vietnam/` | Corpus, admin, gold Stage 1 |
| `docs/` | Specs, W1 evidence, as-built |
| `training/kaggle/` | Package + kernel Round 1 / 1b |
| `training/corpus_audit/` | Script build corpus / admin |
| `tools/` | `validate_gold_variants.py` |
| `.cursor/skills/search20-stage1-query-variants/` | Skill viết query variant |

---

## Cài đặt

### Yêu cầu

- Python 3.11+ (khuyến nghị), `pip`
- Node.js 20+ (cho FE)
- Docker Desktop (cho OpenSearch + API container)
- (Tuỳ chọn) [Kaggle CLI](https://github.com/Kaggle/kaggle-api) + GPU quota để chạy Round 1

### Python deps (bench / gold)

```powershell
python -m pip install pandas pyarrow numpy rank_bm25
# dense local (nếu cần): torch, transformers, sentence-transformers
```

### FE deps

```powershell
cd apps\poi-search\web
npm install
```

### Kiểm tra gold đã khóa

```powershell
python data\vietnam\gold_stage1_v1\verify_gold_lock.py
python tools\validate_gold_variants.py
```

---

## Chạy

### A. Đánh giá Stage 1 (không cần Docker app)

Round 1 / 1b chạy trên **Kaggle GPU** (mạng upload máy yếu → encode trên Kaggle, máy chỉ download):

```powershell
python training\kaggle\prepare_kaggle_gold_stage1_w1.py
python -m kaggle kernels push -p training\kaggle\kernel_gold_stage1_w1
python -m kaggle kernels push -p training\kaggle\kernel_gold_stage1_prefix

# Sau khi xong:
python -m kaggle kernels output hiengchi/vn-poi-gold-stage1-w1-exact-dense-bm25 -p training\kaggle\output_gold_stage1_w1
python -m kaggle kernels output hiengchi/vn-poi-gold-stage1-prefix-char -p training\kaggle\output_gold_stage1_prefix

python apps\poi-search\bench\gold_stage1_selection_report.py
python apps\poi-search\bench\gold_stage1_prefix_char_bench.py --expand-only
```

### B. Demo FE + BE (Docker một phần)

**Trạng thái Docker (quan trọng):**

| Thành phần | Trong Docker? | Ghi chú |
|---|---|---|
| OpenSearch | Có | `docker-compose.yml` · image build từ `training/opensearch` |
| API hybrid `:8000` | Có | `Dockerfile.api` |
| API dense `:8001` | Có | cùng image, profile khác |
| API lexical `:8002` | Có | cùng image, profile khác |
| **Frontend (Vite)** | **Không** | `start.ps1` chạy `npm run dev` trên host `:5173` |

→ **Chưa có thiết kế Docker hoàn chỉnh FE+BE trong một compose.** Stack hiện tại = OpenSearch + 3 API container + FE local.

Ngoài ra (sau cleanup 2026-09-18): corpus/index/model Hanoi đã gỡ; `start.ps1` còn trỏ artifact cũ → **demo E2E sẽ fail** cho đến khi rebuild index + encoder trên `vn-poi-core-v1` và cập nhật `MODEL_RELEASE.json` / `docker-compose.yml`.

Khi đã có model + index nationwide:

```powershell
# Dự kiến (sau migrate):
cd apps\poi-search
.\scripts\link_model.ps1          # junction models/current → encoder
.\scripts\start.ps1               # OpenSearch + 3 API + Vite FE
```

- Web: http://127.0.0.1:5173  
- Hybrid API: http://127.0.0.1:8000/health  
- Dense: http://127.0.0.1:8001/health  
- Lexical: http://127.0.0.1:8002/health  

Smoke (khi API healthy):

```powershell
python apps\poi-search\bench\smoke_contract.py
```

Chi tiết runtime: [`apps/poi-search/README.md`](apps/poi-search/README.md).

---

## Tài liệu

| Mục | Link |
|---|---|
| Mục lục docs | [`docs/README.md`](docs/README.md) |
| Vision / kiến trúc | [`docs/specs/search2.0.md`](docs/specs/search2.0.md) |
| W1 EDA + taxonomy + problem statement | [`docs/deliveries/w1_evidence/`](docs/deliveries/w1_evidence/) |
| Kế hoạch W1–W6 | [`docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md`](docs/deliveries/SEARCH_2.0_TONG_HOP_TASK.md) |

---

## Việc tiếp theo (ngắn)

1. Chốt VERDICT Round 1 / 1b trên gold.  
2. Rebuild OpenSearch + encoder trên `vn-poi-core-v1`; sửa env compose (bỏ hard-code Hanoi).  
3. (Tuỳ chọn) Dockerfile FE + service `web` trong compose để demo one-command.  
4. W2 metric formal + baseline trên gold đã khóa.
