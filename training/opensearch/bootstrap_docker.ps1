$ErrorActionPreference = "Stop"

$runtime = Join-Path $PSScriptRoot "runtime"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$productCompose = Join-Path $repoRoot "apps\poi-search\docker-compose.yml"
New-Item -ItemType Directory -Force $runtime | Out-Null
$ubuntu = Join-Path $runtime "ubuntu-24.04-minimal-root.tar.xz"
$opensearch = Join-Path $runtime "opensearch-3.8.0-linux-x64.tar.gz"
$ubuntuHash = "094dc0afc6ded1c3e5ce71f7d0b48d5db922155097bc8fb1ec19db2ebdd17ece"
$opensearchHash = "cba25b10114e796273fa9399af27fe9c2daaf25a190c37e4b5feb9cfd088e371e0fbd3cddf2bc0fbb753c2e681c0b55f08c0926d11718bf76f77e830017b06ff"

if (-not (Test-Path $ubuntu)) {
    curl.exe --ssl-no-revoke -L -C - --retry 5 --retry-all-errors --fail `
      --output $ubuntu `
      "https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64-root.tar.xz"
}
if (-not (Test-Path $opensearch)) {
    curl.exe --ssl-no-revoke -L -C - --retry 5 --retry-all-errors --fail `
      --output $opensearch `
      "https://artifacts.opensearch.org/releases/bundle/opensearch/3.8.0/opensearch-3.8.0-linux-x64.tar.gz"
}
if ((Get-FileHash $ubuntu -Algorithm SHA256).Hash.ToLower() -ne $ubuntuHash) {
    throw "Ubuntu rootfs checksum mismatch"
}
if ((Get-FileHash $opensearch -Algorithm SHA512).Hash.ToLower() -ne $opensearchHash) {
    throw "OpenSearch checksum mismatch"
}

wsl -d docker-desktop sysctl -w vm.max_map_count=262144
docker image inspect hanoi-opensearch-base:ubuntu24.04 *> $null
if ($LASTEXITCODE -ne 0) {
    docker import $ubuntu hanoi-opensearch-base:ubuntu24.04
}
docker compose -f $productCompose build opensearch api
if ($LASTEXITCODE -ne 0) {
    throw "Docker image build failed"
}
docker volume inspect hanoi-poi-opensearch-data *> $null
if ($LASTEXITCODE -ne 0) {
    docker volume create hanoi-poi-opensearch-data | Out-Null
}
docker run --rm --user root --entrypoint /bin/bash `
  -v hanoi-poi-opensearch-data:/volume `
  hanoi-poi/opensearch:3.8.0-local -lc "chown -R 1000:1000 /volume"
if ($LASTEXITCODE -ne 0) {
    throw "Volume ownership initialization failed"
}
Write-Output "Docker runtime is ready. Run .\apps\poi-search\scripts\start.ps1 from the repository root."
