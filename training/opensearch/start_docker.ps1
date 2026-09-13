$ErrorActionPreference = "Stop"

$compose = (Resolve-Path "$PSScriptRoot\docker-compose.yml").Path
docker compose -f $compose up -d
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed"
}

$deadline = (Get-Date).AddMinutes(5)
do {
    Start-Sleep -Seconds 3
    try {
        $searchHealth = Invoke-RestMethod -Uri "http://127.0.0.1:9200/_cluster/health" -TimeoutSec 3
        $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 10
        [ordered]@{
            opensearch = $searchHealth
            api = $apiHealth
        } | ConvertTo-Json -Depth 5
        exit 0
    } catch {
        foreach ($container in @("hanoi-poi-opensearch", "hanoi-poi-stage1-api")) {
            $state = docker inspect --format "{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{end}}" $container 2>$null
            if ($state -match "exited|dead") {
                docker logs --tail 100 $container
                throw "Docker container stopped: $container ($state)"
            }
        }
    }
} while ((Get-Date) -lt $deadline)

docker logs --tail 100 hanoi-poi-opensearch
docker logs --tail 100 hanoi-poi-stage1-api
throw "Docker demo did not become ready within five minutes"
