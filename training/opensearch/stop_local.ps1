$ErrorActionPreference = "Stop"

$runtime = (Resolve-Path "$PSScriptRoot\runtime\opensearch-3.8.0").Path
$connection = Get-NetTCPConnection -State Listen -LocalPort 9200 -ErrorAction SilentlyContinue
if (-not $connection) {
    Write-Output "OpenSearch is not listening on port 9200"
    exit 0
}

$processId = $connection[0].OwningProcess
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
if (-not $processInfo -or $processInfo.CommandLine -notlike "*$runtime*") {
    throw "Refusing to stop PID $processId because it is not the workspace OpenSearch runtime"
}
Stop-Process -Id $processId
Write-Output "Stopped workspace OpenSearch PID $processId"
