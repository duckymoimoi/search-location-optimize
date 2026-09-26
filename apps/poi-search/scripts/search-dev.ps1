# Search-core Docker helper (local test and develop; no web, no Kaggle).
# Usage:
#   .\scripts\search-dev.ps1 up
#   .\scripts\search-dev.ps1 index
#   .\scripts\search-dev.ps1 reindex
#   .\scripts\search-dev.ps1 smoke
#   .\scripts\search-dev.ps1 lexical-l1
#   .\scripts\search-dev.ps1 shell
#   .\scripts\search-dev.ps1 down
#   .\scripts\search-dev.ps1 build

$ErrorActionPreference = "Stop"
$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ProductRoot "..\..")).Path
$Compose = Join-Path $ProductRoot "docker-compose.search-dev.yml"
$Action = if ($args.Count -ge 1) { $args[0].ToLowerInvariant() } else { "up" }

function Invoke-Compose {
    param(
        [switch]$AllowFail,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$ComposeArgs
    )
    Push-Location $ProductRoot
    try {
        docker compose -f $Compose @ComposeArgs
        if ($LASTEXITCODE -ne 0 -and -not $AllowFail) {
            throw "docker compose failed: $($ComposeArgs -join ' ')"
        }
        return $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

function Ensure-Embeddings {
    $EmbDir = Join-Path $RepoRoot "artifacts\embeddings\me5_small"
    $EmbNpy = Join-Path $EmbDir "corpus_embeddings.npy"
    $EmbIds = Join-Path $EmbDir "poi_ids.parquet"
    if ((Test-Path $EmbNpy) -and (Test-Path $EmbIds)) { return }
    $Kaggle = Join-Path $RepoRoot "training\kaggle\output_gold_stage1_w1\gold_stage1_w1"
    $KaggleNpy = Join-Path $Kaggle "embedding_dense_me5_exact.npy"
    $KaggleIds = Join-Path $Kaggle "poi_ids.parquet"
    if ((Test-Path $KaggleNpy) -and (Test-Path $KaggleIds)) {
        New-Item -ItemType Directory -Force -Path $EmbDir | Out-Null
        Copy-Item $KaggleNpy $EmbNpy -Force
        Copy-Item $KaggleIds $EmbIds -Force
        Write-Output "Staged embeddings from Kaggle output -> $EmbDir"
        return
    }
    throw "Missing embeddings under $EmbDir. Run encode_me5_corpus.py or stage Round-1 npy."
}

function Wait-Api {
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $h = Invoke-RestMethod "http://127.0.0.1:8000/health"
            if ($h.status -eq "ok") { $ok = $true; break }
        } catch { }
        Start-Sleep -Seconds 5
    }
    if (-not $ok) { Write-Warning "API not healthy yet - check: docker logs vn-poi-searchdev-api" }
}

switch ($Action) {
    "build" {
        $env:DOCKER_BUILDKIT = "1"
        $env:COMPOSE_DOCKER_CLI_BUILD = "1"
        $apiImg = docker images -q "vn-poi/stage1-api:0.1.0-local"
        if (-not $apiImg) {
            Write-Warning "vn-poi/stage1-api missing - build API once from main compose (needs network for torch)."
            Push-Location $ProductRoot
            try {
                docker compose -f docker-compose.yml build api
                if ($LASTEXITCODE -ne 0) { throw "docker compose build api failed" }
            } finally {
                Pop-Location
            }
        } else {
            Write-Output "Reusing local vn-poi/stage1-api:0.1.0-local (no torch re-download)."
        }
        Invoke-Compose build api bench
        Write-Output "Built vn-poi/search-dev (extras only). HF runtime cache volume: vn-poi-hf-cache."
    }
    "up" {
        $code = Invoke-Compose -AllowFail up -d --no-build elasticsearch api bench
        if ($code -ne 0) {
            Write-Warning "Images missing or compose failed - building search-dev once..."
            Invoke-Compose build api bench
            Invoke-Compose up -d --no-build elasticsearch api bench
        }
        Write-Output "ES  http://127.0.0.1:9200"
        Write-Output "API http://127.0.0.1:8000/health  (uvicorn reload)"
        Write-Output "Bench shell: .\scripts\search-dev.ps1 shell"
        Wait-Api
    }
    "index" {
        Ensure-Embeddings
        $env:RECREATE_INDEX = "0"
        Invoke-Compose --profile index run --rm --no-build indexer
    }
    "reindex" {
        Ensure-Embeddings
        $env:RECREATE_INDEX = "1"
        Invoke-Compose --profile index run --rm --no-build indexer
    }
    "smoke" {
        Invoke-Compose exec -T bench python apps/poi-search/bench/smoke_contract.py
    }
    "lexical-l1" {
        $extra = @()
        if ($args.Count -gt 1) { $extra = $args[1..($args.Count - 1)] }
        # --no-deps: lexical L1 reads parquet only (no ES/API required)
        Invoke-Compose run --rm --no-deps -T bench python apps/poi-search/bench/gold_stage1_lexical_l1.py @extra
    }
    "es-lexical" {
        # Host ES :9200 — policy-driven lexical_body (same as API)
        $env:PYTHONUNBUFFERED = "1"
        Push-Location $ProductRoot
        try {
            python -u bench/gold_stage1_es_lexical_policy_bench.py --es-url http://127.0.0.1:9200
            if ($LASTEXITCODE -ne 0) { throw "es-lexical bench failed" }
        } finally {
            Pop-Location
        }
    }
    "iterate" {
        $env:PYTHONUNBUFFERED = "1"
        Push-Location $ProductRoot
        try {
            python -u bench/gold_stage1_lexical_iterate.py --es-url http://127.0.0.1:9200
            if ($LASTEXITCODE -ne 0) { throw "lexical iterate failed" }
        } finally {
            Pop-Location
        }
    }
    "rescue" {
        Invoke-Compose run --rm --no-deps -T bench python apps/poi-search/bench/gold_stage1_lexical_rescue_report.py
    }
    "shell" {
        Invoke-Compose exec bench bash
    }
    "logs" {
        Invoke-Compose logs -f --tail=100 api
    }
    "down" {
        Invoke-Compose down
    }
    "ps" {
        Invoke-Compose ps
    }
    default {
        Write-Output "Unknown action: $Action"
        Write-Output ""
        Write-Output "  up          Start ES + API (reload) + bench (no image rebuild)"
        Write-Output "  build       Build search-dev image once (torch/deps)"
        Write-Output "  index       Bulk load index (needs embeddings)"
        Write-Output "  reindex     Recreate index + bulk"
        Write-Output "  smoke       API contract smoke inside bench container"
        Write-Output "  lexical-l1  Run local lexical L1 gate"
        Write-Output "  es-lexical  ES+policy lexical gold bench"
        Write-Output "  iterate     Lexical structure A/B + hybrid RRF"
        Write-Output "  rescue      mE5 vs BM25 rescue diagnostic"
        Write-Output "  shell       Interactive bash in bench container"
        Write-Output "  logs        Follow API logs"
        Write-Output "  down        Stop stack"
        Write-Output "  ps          Status"
    }
}
