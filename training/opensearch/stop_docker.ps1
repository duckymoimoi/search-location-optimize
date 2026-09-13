$ErrorActionPreference = "Stop"

$compose = (Resolve-Path "$PSScriptRoot\docker-compose.yml").Path
docker compose -f $compose stop
if ($LASTEXITCODE -ne 0) {
    throw "docker compose stop failed"
}
