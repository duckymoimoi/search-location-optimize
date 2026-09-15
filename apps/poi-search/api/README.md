# POI Search API (runtime)

Serving only. Policy: `search_policy.json`. Model weights come from `../models/current`.

```powershell
cd apps\poi-search
.\scripts\link_model.ps1
docker compose up -d
```

- Hybrid: http://127.0.0.1:8000
- Dense-only: http://127.0.0.1:8001
- Lexical-only: http://127.0.0.1:8002

Checks live under `../bench/`, not here.
