# POI Search — runtime (FE + BE)

Demo tìm địa điểm: **Elasticsearch 9.5.3** + FastAPI (mE5-small) + React/MapLibre.
Docker demo corpus: **`vn-poi-core-v3-semantic-address-dedup50`** (179.209 POI).
Gold v1 replay và search-dev vẫn có thể dùng corpus v1 riêng.

```text
apps/poi-search/
  api/                 FastAPI (ES knn + lexical + RRF)
  web/                 Vite + React + MapLibre
  models/              MODEL_RELEASE.json
  bench/               gold Stage-1 harness + smoke
  docker/              Dockerfile.api / indexer / web + nginx.conf
  docker-compose.yml   elasticsearch + indexer + api + web
  scripts/             encode_me5_corpus.py, index_vn_poi.py, start.ps1
```

## Docker services

| Stack | File | Khi nào |
|---|---|---|
| **Search-dev (core)** | `docker-compose.search-dev.yml` | Kiểm thử / tối ưu retrieval, lexical L1, smoke — **khuyến nghị hàng ngày** |
| Demo full | `docker-compose.yml` | ES + API + web MapLibre |

Chi tiết search-dev: [`docker/SEARCH_DEV.md`](docker/SEARCH_DEV.md)

```powershell
cd apps\poi-search
.\scripts\search-dev.ps1 build   # lần đầu
.\scripts\search-dev.ps1 index
.\scripts\search-dev.ps1 up
.\scripts\search-dev.ps1 smoke
.\scripts\search-dev.ps1 lexical-l1
```

| Service (search-dev) | Port | Vai trò |
|---|---|---|
| `elasticsearch` | 9200 | ES 9.5.3 (volume chung `vn-poi-es-data`) |
| `api` | 8000 | hybrid suggest + **hot-reload** |
| `bench` | — | gold / lexical / smoke trong container |
| `indexer` | — | profile `index` — one-shot bulk |

Eval chạy **local** (host hoặc `search-dev` bench). Kaggle chỉ khi train model.

## Goong (map + directions)

| Key | Where | Role |
|---|---|---|
| `GOONG_API_KEY` | `apps/poi-search/.env` → API container | Directions REST (`/v1/route-preview` road) |
| `GOONG_MAP_API_KEY` | `apps/poi-search/.env` | MapLibre Goong basemap (baked into the Docker FE bundle) |
| `VITE_GOONG_MAPTILES_KEY` | `web/.env` | Same key for `npm run dev` |

### Refresh FE Docker

```powershell
cd apps\poi-search
.\scripts\refresh-web.ps1
```

Script build/recreate `Dockerfile.web`. FE image tự chứa Vite bundle và MapLibre worker; không mount `web/dist` từ host.

API/ES images giữ nguyên. Chỉ khi đổi Dockerfile API/indexer mới cần build service tương ứng.

## Gold bench (local — host hoặc search-dev)

```powershell
# Trong search-dev container (khuyến nghị):
.\scripts\search-dev.ps1 lexical-l1
.\scripts\search-dev.ps1 rescue
.\scripts\search-dev.ps1 smoke

# Hoặc trên host (cần deps Python):
python bench\gold_stage1_selection_report.py
python bench\gold_stage1_lexical_l1.py
python bench\gold_stage1_prefix_char_bench.py --expand-only
```

Không cần Kaggle cho eval. Kaggle chỉ khi train encoder.
