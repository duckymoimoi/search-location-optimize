# Rebuild and recreate the self-contained FE image.
# VITE_* values are read by Compose from apps/poi-search/.env at build time.

$ErrorActionPreference = "Stop"
$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Compose = Join-Path $ProductRoot "docker-compose.yml"

docker compose -f $Compose up -d --build --force-recreate web
if ($LASTEXITCODE -ne 0) {
    throw "web image build/recreate failed"
}

Write-Output "Web: http://127.0.0.1:5173"
Write-Output "The image contains the Vite bundle and MapLibre worker; no host web/dist mount is used."
