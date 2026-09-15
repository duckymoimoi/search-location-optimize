# Bench / smoke (runtime checks)

Scripts hit the local APIs. Results go to `results/` (gitignored).

```powershell
cd apps\poi-search
python bench\smoke_contract.py
python bench\bench_api_runtime.py
python bench\bench_quality_runtime_load.py
```

Full report: `bench/results/QUALITY_RUNTIME_LOAD.md`

Env:

- `POI_API_BASE_URL` (default `http://127.0.0.1:8000`) for smoke
