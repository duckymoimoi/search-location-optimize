$ErrorActionPreference = "Stop"

$existing = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($existing) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5 | ConvertTo-Json -Depth 5
        exit 0
    } catch {
        Start-Sleep -Seconds 2
    }
}

$logDir = Join-Path $PSScriptRoot "demo_logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$stdout = Join-Path $logDir "api.stdout.log"
$stderr = Join-Path $logDir "api.stderr.log"
$process = Start-Process -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "demo_api:app", "--app-dir", $PSScriptRoot,
    "--host", "127.0.0.1", "--port", "8000", "--workers", "1"
) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
  -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$process.Id | Set-Content -Encoding ascii (Join-Path $PSScriptRoot "demo_api.pid")

$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 2
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 3 | ConvertTo-Json -Depth 5
        exit 0
    } catch {
        if ($process.HasExited) {
            Get-Content -Tail 100 $stderr -ErrorAction SilentlyContinue
            throw "Demo API exited with code $($process.ExitCode)"
        }
    }
} while ((Get-Date) -lt $deadline)

Get-Content -Tail 100 $stderr -ErrorAction SilentlyContinue
throw "Demo API did not become ready within three minutes"
