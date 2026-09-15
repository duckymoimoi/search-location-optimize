$ErrorActionPreference = "Stop"

$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ProductRoot "..\..")).Path
$Compose = Join-Path $ProductRoot "docker-compose.yml"
$IndexName = "hanoi-poi-stable-v1-release1"
$LinkModel = Join-Path $PSScriptRoot "link_model.ps1"

& $LinkModel

docker compose -f $Compose up -d opensearch

$ready = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:9200"
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) { throw "OpenSearch did not become ready" }

$count = 0
try {
    $count = (Invoke-RestMethod "http://127.0.0.1:9200/$IndexName/_count").count
} catch {
    $count = 0
}

if ($count -ne 45692) {
    $Dense = Join-Path $RepoRoot "artifacts\indexes\hanoi-poi-stable-v1-release1"
    python (Join-Path $RepoRoot "training\stage1\opensearch_index.py") `
        --bundle (Join-Path $RepoRoot "HANOI_POI_STABLE_V1\hanoi_poi_stable_v1") `
        --artifacts $Dense `
        --output (Join-Path $RepoRoot "training\stage1\benchmark_stable_v1\opensearch_release1") `
        --index $IndexName `
        --stable-corpus `
        --embeddings (Join-Path $Dense "corpus_context_embeddings.npy") `
        --id-map (Join-Path $Dense "corpus_context_ids.parquet") `
        --m 32 --ef-construction 512 --bulk-size 200
}

docker compose -f $Compose up -d api api-dense api-lexical

$Frontend = Join-Path $ProductRoot "web"
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    npm --prefix $Frontend install
}
$ViteLog = Join-Path $Frontend "vite.log"
$env:VITE_USE_MOCK = "0"
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "set VITE_USE_MOCK=0&& npm run dev -- --host 127.0.0.1 > `"$ViteLog`" 2>&1" `
    -WorkingDirectory $Frontend -WindowStyle Hidden

Write-Output "POI Search web:  http://127.0.0.1:5173"
Write-Output "API hybrid:      http://127.0.0.1:8000/health"
Write-Output "API dense-only:  http://127.0.0.1:8001/health"
Write-Output "API lexical:     http://127.0.0.1:8002/health"
Write-Output "Smoke:           python apps/poi-search/bench/smoke_contract.py"
