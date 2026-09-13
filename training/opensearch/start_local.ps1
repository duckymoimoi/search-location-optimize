$ErrorActionPreference = "Stop"

$runtime = (Resolve-Path "$PSScriptRoot\runtime\opensearch-3.8.0").Path
$dataPath = Join-Path $PSScriptRoot "data"
$logPath = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force $dataPath, $logPath | Out-Null

$existing = Get-NetTCPConnection -State Listen -LocalPort 9200 -ErrorAction SilentlyContinue
if ($existing) {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:9200" -TimeoutSec 5
    $health | ConvertTo-Json -Depth 5
    exit 0
}

$env:OPENSEARCH_JAVA_OPTS = "-Xms512m -Xmx512m"
$bat = Join-Path $runtime "bin\opensearch.bat"
$stdout = Join-Path $logPath "launcher.stdout.log"
$stderr = Join-Path $logPath "launcher.stderr.log"
$arguments = @(
    "/c",
    "`"$bat`"",
    "-Ecluster.name=hanoi-poi-local",
    "-Enode.name=hanoi-poi-demo",
    "-Ediscovery.type=single-node",
    "-Enetwork.host=127.0.0.1",
    "-Ehttp.port=9200",
    "-Eplugins.security.disabled=true",
    "-Epath.data=$dataPath",
    "-Epath.logs=$logPath"
)
$process = Start-Process -FilePath "cmd.exe" -ArgumentList $arguments `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$process.Id | Set-Content -Encoding ascii (Join-Path $PSScriptRoot "launcher.pid")

$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:9200" -TimeoutSec 3
        $health | ConvertTo-Json -Depth 5
        exit 0
    } catch {
        if ($process.HasExited) {
            Get-Content -Tail 100 $stderr -ErrorAction SilentlyContinue
            throw "OpenSearch launcher exited with code $($process.ExitCode)"
        }
    }
} while ((Get-Date) -lt $deadline)

Get-Content -Tail 100 $stderr -ErrorAction SilentlyContinue
throw "OpenSearch did not become ready within three minutes"
