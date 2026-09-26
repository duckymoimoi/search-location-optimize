# POI Search web demo

Vite + React + MapLibre. Lives under the runtime product `apps/poi-search`.

Docker Compose builds this as a self-contained nginx image. The Goong map-tiles
key is a public browser key and is injected at build time from
`apps/poi-search/.env`; the MapLibre worker is copied into the same image.

```powershell
../scripts/start.ps1
```

Or from this folder:

```powershell
npm install
npm run dev -- --host 127.0.0.1
```

Search calls the real POI API via the Vite proxy or `VITE_API_BASE_URL`. Demo users and history are fixtures on that API, not a fake POI corpus. See `.env.example`.

For Docker FE refresh, run `../scripts/refresh-web.ps1` from this directory's parent.
