# POI Search — runtime (FE + BE)

App demo tìm địa điểm: FastAPI + React/MapLibre.  
Corpus đánh giá hiện tại là **toàn quốc** (`vn-poi-core-v1`); stack Docker/index vẫn cần migrate (xem README gốc).

```text
apps/poi-search/
  api/                 FastAPI + search_policy.json
  web/                 Vite + React + MapLibre
  models/              MODEL_RELEASE.json + current/ (junction encoder)
  bench/               gold Stage-1 harness + smoke
  docker/              Dockerfile.api
  docker-compose.yml   OpenSearch + hybrid/dense/lexical APIs
  scripts/             start.ps1, link_model.ps1
```

## Docker — phạm vi thực tế

| Service | Docker? |
|---|---|
| OpenSearch | Yes |
| API ×3 (hybrid / dense / lexical) | Yes |
| Frontend | **No** — `npm run dev` trên host |

Không có compose “all-in-one” FE+BE. Chi tiết + lệnh: [`../../README.md`](../../README.md).

## Ports (khi chạy được)

- Web: http://127.0.0.1:5173  
- Hybrid: http://127.0.0.1:8000  
- Dense: http://127.0.0.1:8001  
- Lexical: http://127.0.0.1:8002  

## Gold bench (không cần API)

```powershell
python bench\gold_stage1_selection_report.py
python bench\gold_stage1_prefix_char_bench.py --expand-only
```
