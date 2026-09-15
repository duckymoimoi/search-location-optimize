$ErrorActionPreference = "Stop"

$ModelsDir = Resolve-Path (Join-Path $PSScriptRoot "..\models")
$LinkPath = Join-Path $ModelsDir "current"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$DefaultTarget = Join-Path $RepoRoot "artifacts\models\e5-v4-finetuned"

$ManifestPath = Join-Path $ModelsDir "MODEL_RELEASE.json"
$Target = $DefaultTarget
if (Test-Path $ManifestPath) {
    $manifest = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.source_path) {
        $candidate = Join-Path $RepoRoot ($manifest.source_path -replace "/", "\")
        if (Test-Path $candidate) { $Target = $candidate }
    }
}

if (-not (Test-Path $Target)) {
    throw "Model source not found: $Target"
}
if (-not (Test-Path (Join-Path $Target "final_model"))) {
    throw "Missing final_model under $Target"
}

if (Test-Path $LinkPath) {
    $item = Get-Item $LinkPath -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        [System.IO.Directory]::Delete($LinkPath)
    } else {
        throw "models/current exists and is not a junction/symlink. Move it aside first: $LinkPath"
    }
}

New-Item -ItemType Junction -Path $LinkPath -Target $Target | Out-Null

Write-Output "Linked $LinkPath -> $Target"
Get-Item $LinkPath | Format-List FullName, LinkType, Target
