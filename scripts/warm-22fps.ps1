# Precompiles the host pipelines earlier book=1 runs drew with.
# Run the game once with play-22fps.ps1 first so the pipeline book exists.
param(
    [int]$Jobs = 4
)
$ErrorActionPreference = 'Stop'
# Same translator switches and target formats as play-22fps.ps1, so the warm
# entries match the game's pipelines.
$env:VICTORY_E5_TARGETS = 'r11g11b10'
$env:VICTORY_HALF_VIEWS = '1'
$env:VICTORY_NAN_GUARD = '0'
$env:VICTORY_PS_QUAD_READS = '0'
$env:VICTORY_BVH_MISS = '1'
$env:VICTORY_GROUP_SYNC = '2'
$exe = Join-Path $PSScriptRoot '..\target\diag\victory.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host "No $exe. Build it first."
    exit 2
}
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $exe warm --used --jobs $Jobs
} finally {
    Pop-Location
}
