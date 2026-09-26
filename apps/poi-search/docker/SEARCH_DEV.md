# Search-dev Docker — core tìm kiếm (local)

Stack **chỉ** cho kiểm thử / phát triển retrieval: Elasticsearch + API (hot-reload) + bench.
Không gồm web/MapLibre. **Không dùng Kaggle** cho eval — chỉ đẩy Kaggle khi train encoder.

## Services

| Service | Port | Vai trò |
|---|---|---|
| `elasticsearch` | 9200 | ES 9.5.3 · volume `vn-poi-es-data` (chung với demo compose) |
| `api` | 8000 | FastAPI + mE5 · `uvicorn --reload` · mount repo |
| `bench` | — | Cùng image · chạy gold/lexical/smoke |
| `indexer` | — | Profile `index` · one-shot bulk |

Image: `vn-poi/search-dev:0.1.0-local`  
HF cache: volume `vn-poi-hf-cache` (tải model **một lần** lúc API boot — không bake vào image).

## Nhanh

```powershell
cd apps\poi-search

# Lần đầu (hoặc khi đổi search-dev-requirements.txt)
.\scripts\search-dev.ps1 build
.\scripts\search-dev.ps1 index          # cần artifacts/embeddings/me5_small/
.\scripts\search-dev.ps1 up

# Hàng ngày — không rebuild
.\scripts\search-dev.ps1 up
.\scripts\search-dev.ps1 smoke
.\scripts\search-dev.ps1 lexical-l1
.\scripts\search-dev.ps1 shell
```

Sửa `api/*.py` → API reload tự. Sửa analyzer/boost trong `search_policy.json` → reload.

## Bench trong container

```powershell
.\scripts\search-dev.ps1 shell
# bên trong:
python apps/poi-search/bench/gold_stage1_lexical_l1.py
python apps/poi-search/bench/gold_stage1_lexical_rescue_report.py
python apps/poi-search/bench/smoke_contract.py
```

Repo được mount tại `/repo` → path script giữ nguyên như trên host.

## Tránh tốn mạng / rebuild lâu

| Việc | Làm |
|---|---|
| Đổi code API / bench / policy | Chỉ save file (bind mount) — **0 download** |
| Build search-dev | `FROM vn-poi/stage1-api` + thêm pandas/pyarrow/rank_bm25 thôi |
| Đổi deps bench | BuildKit pip cache mount (`/root/.cache/pip`) |
| Đổi model HF lúc chạy | Volume `vn-poi-hf-cache` (hoặc model đã bake trong stage1-api) |
| `up` hàng ngày | `--no-build` — không đụng registry |

`search-dev.ps1 build` bật `DOCKER_BUILDKIT=1` và tái dùng image API local nếu có.
## Profiles retrieval

```powershell
$env:POI_RETRIEVAL_PROFILE="lexical_only"; .\scripts\search-dev.ps1 up
$env:POI_RETRIEVAL_PROFILE="dense_only";   .\scripts\search-dev.ps1 up
$env:POI_RETRIEVAL_PROFILE="hybrid";       .\scripts\search-dev.ps1 up
```

## Files

```text
docker-compose.search-dev.yml
docker/Dockerfile.search-dev
docker/search-dev-requirements.txt
scripts/search-dev.ps1
```
