# run-perf.ps1 - 8 GB NVIDIA performance profile for the patched runner.
#
# Measured on a newer VIctory tree at 1280x720 with 0.667 render scale:
# median ~45 ms/frame, p90 ~51 ms, no exceptions/device removal, ~6.1/6.9 GB
# of VRAM in use.  The older vendored tree reads most of these; keys marked
# (newer fork) are ignored there.
#
# usage:
#   .\scripts\run-perf.ps1 -Exe .\cool_fox\target\x86_64-pc-windows-msvc\release\victory.exe `
#       -Game "D:\path\to\game_scarlett_master.exe"
#
# For the game-side profile (uncap the title's FPS, turn RT/grass/SSR off,
# restore sharp textures), run once:
#   python tools\tweak_game_settings.py --profile sharp
param(
    [Parameter(Mandatory)][string]$Exe,
    [Parameter(Mandatory)][string]$Game,
    [ValidateSet('series-s', 'series-x')][string]$Console = 'series-s',
    [string]$Log = 'info'
)
$ErrorActionPreference = 'Stop'
$settings = [ordered]@{
    VICTORY_DISPLAY_MODE        = '1280x720'
    VICTORY_WINDOW_MAX          = '1280x720'
    VICTORY_RENDER_SCALE        = '0.667'   # (newer fork)
    VICTORY_OWN_UPSCALER        = '1'       # (newer fork)
    VICTORY_CARD_BUFFERS_MB     = '1536'
    VICTORY_CARD_BUFFERS_MIN_KB = '64'
    VICTORY_CARD_WINDOWS_MB     = '0'
    VICTORY_TEXTURE_BUDGET_MB   = '1536'
    VICTORY_TEXTURE_ROOM_PERCENT = '88'
    VICTORY_WINDOWS_BAR_MB      = '3072'
    VICTORY_WINDOWS_BAR_PERCENT = '88'
    VICTORY_WINDOW_KB           = '256'
    VICTORY_WINDOW_TAILS        = '1'
    VICTORY_SEND_KEPT_MB        = '512'     # (newer fork)
    VICTORY_DYNAMIC_SLOTS       = '524288'
    VICTORY_TEXTURE_MIP_DROP    = '1'
    VICTORY_LEVELS_ON_DEMAND    = '1'
    VICTORY_STAGING_KEPT        = '4'
    VICTORY_MAX_PRELUDES        = '32'
    VICTORY_MAP_THREADS         = '4'
    VICTORY_FAST_CORES          = '3'
    VICTORY_TITLE_PRIORITIES    = '1'
    VICTORY_PANEL               = '0'
    VICTORY_D3D12_DRED          = '0'
    VICTORY_CARD_ACCOUNTING     = '0'
    VICTORY_PIPELINE_BOOK       = '0'
    VICTORY_MEMORY_MAP          = '0'
    VICTORY_AMBIENT             = '1.0'
    VICTORY_AMBIENT_AIR         = '1.5'
    VICTORY_CARD_AWAKE          = '1'
    VICTORY_CARD_REHASH_RUNS    = '1'
    VICTORY_CARD_STEPS          = '2'
    VICTORY_JOIN_COPIES         = '1'
    VICTORY_INDIRECT_BATCH      = '2'
    VICTORY_INDIRECT_WINDOW     = '1'
    VICTORY_RELAY               = '2'
    VICTORY_RELAY_COPY          = '1'
    VICTORY_TEXTURE_NO_WAIT     = '1'
    VICTORY_WIDE_BACK           = '1'
    VICTORY_RAW_VIEWS           = '0'
    VICTORY_GROUP_SYNC          = '2'
    VICTORY_SKIP_PIPELINES      = '02384a60fda6f2d0,731a39171b568298'
    VICTORY_LOG                 = $Log
}
if (-not (Test-Path $Exe))  { Write-Host "No $Exe. Build it first (README.md, Windows)."; exit 2 }
if (-not (Test-Path $Game)) { Write-Host "No $Game. Pass the executable of your own copy of the title."; exit 2 }

# Clear settings left by another launcher, but keep the path variables.
$paths = 'VICTORY_CONFIG', 'VICTORY_GAME_DIR', 'VICTORY_CACHE_DIR', 'VICTORY_DATA_DIR'
Get-ChildItem Env:VICTORY_* | Where-Object { $_.Name -notin $paths } | ForEach-Object { Remove-Item "Env:$($_.Name)" }
Remove-Item Env:VICTORY_WAVE_WIDE -ErrorAction SilentlyContinue
foreach ($k in $settings.Keys) { Set-Item "Env:$k" $settings[$k] }

Write-Host "victory-perf: settings in effect:"
Get-ChildItem Env:VICTORY_* | Sort-Object Name | ForEach-Object { Write-Host "  $($_.Name)=$($_.Value)" }
Write-Host "victory-perf: for the title's own profile, run: python tools\tweak_game_settings.py --profile sharp"

$Exe = (Resolve-Path $Exe).Path
$Game = (Resolve-Path $Game).Path
Push-Location (Split-Path $Exe)
try { & $Exe run $Game --execute --console $Console } finally { Pop-Location }
exit $LASTEXITCODE
