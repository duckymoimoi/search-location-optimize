# Models (runtime release)

`current/` is a Windows junction (or directory symlink) to the encoder release used by the API.

Default target:

`artifacts/models/e5-v4-finetuned`

Create / refresh the link:

```powershell
.\apps\poi-search\scripts\link_model.ps1
```

Manifest: [MODEL_RELEASE.json](MODEL_RELEASE.json).

Do not put training scripts here. Weights stay outside git; only the junction + manifest live under `apps/poi-search/models/`.
