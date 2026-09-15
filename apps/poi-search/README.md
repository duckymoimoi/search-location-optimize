# Hanoi POI Search (runtime product)

Runtime lives here. Training / eval stay under `training/`.

```text
apps/poi-search/
  api/                 FastAPI + search_policy.json
  web/                 Vite + React + MapLibre demo
  models/              MODEL_RELEASE.json + current/ (junction to encoder)
  bench/               smoke + latency/resource scripts
  docker/              API image build files
  docker-compose.yml   OpenSearch + hybrid/dense/lexical APIs
  scripts/             start.ps1, link_model.ps1
```

## Quick start

```powershell
cd apps\poi-search
.\scripts\link_model.ps1
.\scripts\start.ps1
```

Or:

```powershell
.\apps\poi-search\scripts\start.ps1
```

- Web: http://127.0.0.1:5173
- Hybrid API: http://127.0.0.1:8000
- Dense-only: http://127.0.0.1:8001
- Lexical-only: http://127.0.0.1:8002

## Smoke

```powershell
python apps\poi-search\bench\smoke_contract.py
```

## Model

`models/current` must point at a folder containing `final_model/`. Default junction target is `artifacts/models/e5-v4-finetuned`. See [models/README.md](models/README.md).

## Notes

- API does **not** mount `training/stage1`.
- OpenSearch index build (if missing) uses `training/stage1/opensearch_index.py` and the frozen vectors under `artifacts/indexes/` once; after that runtime only needs the Docker volume.
- Project documentation is indexed from [`../../docs/README.md`](../../docs/README.md).
