# The profile measured on the RTX 4060 / 8 GB machine on 2026-11-26:
# 1280x720, 0.667 render scale, 45.3 ms median, 50.9 ms p90, 22 fps,
# 0 failed shaders. This is the best real 3D result across the builds we
# benchmarked (the 30 fps numbers were menus/loading screens).
#
#   .\scripts\play-22fps.ps1 -Game "D:\path\to\game_scarlett_master.exe"
#
# Use -More @{ VICTORY_AMBIENT='1.0' } for one-setting experiments.
param(
    [Parameter(Mandatory)][string]$Game,
    [hashtable]$More = @{}
)
$ErrorActionPreference = 'Stop'

$settings = [ordered]@{
    VICTORY_DISPLAY_MODE         = '1280x720'
    VICTORY_WINDOW_MAX           = '1280x720'
    VICTORY_RENDER_SCALE         = '0.667'
    VICTORY_OWN_UPSCALER         = '1'
    VICTORY_CARD_BUFFERS_MB      = '1536'
    VICTORY_CARD_BUFFERS_MIN_KB  = '64'
    VICTORY_TEXTURE_BUDGET_MB    = '1536'
    VICTORY_TEXTURE_ROOM_PERCENT = '88'
    VICTORY_WINDOWS_BAR_MB       = '3072'
    VICTORY_WINDOWS_BAR_PERCENT  = '88'
    VICTORY_WINDOW_KB            = '256'
    VICTORY_WINDOW_TAILS         = '1'
    VICTORY_SEND_KEPT_MB         = '512'
    VICTORY_CARD_AWAKE           = '0'
    VICTORY_CARD_REHASH_RUNS     = '1'
    VICTORY_CARD_STEPS           = '2'
    VICTORY_MAP_THREADS          = '4'
    VICTORY_FAST_CORES           = '3'
    VICTORY_TITLE_PRIORITIES     = '1'
    VICTORY_AMBIENT              = '1.0'
    VICTORY_RELAY                = '2'
    VICTORY_RELAY_COPY           = '1'
    VICTORY_JOIN_COPIES          = '1'
    VICTORY_INDIRECT_BATCH       = '2'
    VICTORY_INDIRECT_WINDOW      = '1'
    VICTORY_BVH_MISS             = '1'
    VICTORY_ACTIVATE_RAYS        = '0'
    VICTORY_RT_RESOLVE           = '0'
    VICTORY_RT_SKIP_ACTIVATE     = '1'
    VICTORY_RT_SKIP_RESOLVE      = '1'
    VICTORY_MEMORY_MAP           = '0'
    VICTORY_PIPELINE_BOOK        = '0'
    VICTORY_CARD_ACCOUNTING      = '0'
    VICTORY_D3D12_DRED           = '0'
    VICTORY_PANEL                = '0'
    VICTORY_SHOW_AFTER           = '1'
    VICTORY_UNDER_WIDE           = '0'
    VICTORY_WIDE_BACK            = '1'
    VICTORY_TEXTURE_NO_WAIT      = '1'
    VICTORY_CLAMP_WAITS          = '0'
    VICTORY_LAND_ECHO            = '0'
    VICTORY_DYNAMIC_SLOTS        = '524288'
    VICTORY_LOG                  = 'info'
}
foreach ($k in $More.Keys) { $settings[$k] = $More[$k] }

$victory = Join-Path $PSScriptRoot '..\target\diag\victory.exe'
if (-not (Test-Path -LiteralPath $victory)) {
    Write-Host "No $victory. Build it first (README.md)."
    exit 2
}
if (-not (Test-Path -LiteralPath $Game)) {
    Write-Host "No $Game."
    exit 2
}

# Other settings left over in this window go; where your files are stays.
$paths = 'VICTORY_CONFIG', 'VICTORY_GAME_DIR', 'VICTORY_CACHE_DIR', 'VICTORY_DATA_DIR'
Get-ChildItem Env:VICTORY_* -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin $paths } |
    ForEach-Object { Remove-Item "Env:$($_.Name)" }
foreach ($k in $settings.Keys) { Set-Item "Env:$k" $settings[$k] }

$Game = (Resolve-Path -LiteralPath $Game).Path
Push-Location (Join-Path $PSScriptRoot '..')
try {
    & $victory run $Game --execute --console series-s
} finally {
    Pop-Location
}
