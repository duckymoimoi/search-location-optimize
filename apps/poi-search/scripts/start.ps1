$ErrorActionPreference = "Stop"

$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ProductRoot "..\..")).Path
$Compose = Join-Path $ProductRoot "docker-compose.yml"
$IndexName = "vn-poi-core-v3-me5-small"
$ExpectedRows = 179209
$EmbDir = Join-Path $RepoRoot "artifacts\embeddings\me5_small_v3"
$EmbNpy = Join-Path $EmbDir "corpus_embeddings.npy"
$EmbIds = Join-Path $EmbDir "poi_ids.parquet"

if (-not (Test-Path $EmbNpy) -or -not (Test-Path $EmbIds) -or -not (Test-Path (Join-Path $EmbDir "manifest.json"))) {
    throw "Missing v3 embeddings; run python apps/poi-search/scripts/migrate_me5_embeddings_v3.py"
}

Push-Location $ProductRoot
try {
    # Reuse images — do not rebuild API/ES (torch/HF pulls are huge).
    docker compose -f $Compose up -d --no-build elasticsearch
} finally {
    Pop-Location
}

$ready = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:9200"
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) { throw "Elasticsearch did not become ready on :9200" }

$env:RECREATE_INDEX = if ($env:RECREATE_INDEX) { $env:RECREATE_INDEX } else { "0" }
Push-Location $ProductRoot
try {
    docker compose -f $Compose run --rm indexer
    if ($LASTEXITCODE -ne 0) { throw "indexer failed (build once: docker compose build indexer)" }
    docker compose -f $Compose up -d --no-build --force-recreate api
    if ($LASTEXITCODE -ne 0) { throw "api failed (build once: docker compose build api)" }
} finally {
    Pop-Location
}

# FE: build and recreate the self-contained nginx image.
& (Join-Path $PSScriptRoot "refresh-web.ps1")

$apiReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:8000/health"
        if ($health.status -eq "ok") {
            $apiReady = $true
            break
        }
    } catch {
    }
    Start-Sleep -Seconds 5
}
if (-not $apiReady) { Write-Warning "API not healthy yet — check docker logs vn-poi-stage1-api" }

Write-Output "POI Search web:  http://127.0.0.1:5173"
Write-Output "API hybrid:      http://127.0.0.1:8000/health"
Write-Output "Elasticsearch:   http://127.0.0.1:9200/$IndexName/_count"
Write-Output "Smoke:           python apps/poi-search/bench/smoke_contract.py"
Write-Output "FE refresh: .\scripts\refresh-web.ps1"
Write-Output "Rebuild index:   `$env:RECREATE_INDEX=1; .\scripts\start.ps1"
