$ErrorActionPreference = "Stop"

$connection = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if (-not $connection) {
    Write-Output "Demo API is not listening on port 8000"
    exit 0
}
$processId = $connection[0].OwningProcess
$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
if (-not $processInfo -or $processInfo.CommandLine -notlike "*uvicorn*demo_api:app*") {
    throw "Refusing to stop PID $processId because it is not the workspace demo API"
}
Stop-Process -Id $processId
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (-not (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)) {
        break
    }
    Start-Sleep -Milliseconds 250
}
Write-Output "Stopped demo API PID $processId"
