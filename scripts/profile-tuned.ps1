# The tuned CPU profile plus GPU timestamps: the top pipelines by card time
# and the card's time by command, every five seconds. Use the dense scene
# (5,000+ draws) where the card is 92-95% busy; that is where the next code
# optimization has to come from.
#
#   .\scripts\profile-tuned.ps1
#   .\scripts\profile-tuned.ps1 -Game "D:\path\to\game_scarlett_master.exe"
param(
    [string]$Game = 'D:\my_xbox_game_dump\game_scarlett_master.exe',
    [string]$LogFile
)
$ErrorActionPreference = 'Stop'

if (-not $LogFile) {
    $LogFile = Join-Path $PSScriptRoot ('..\logs\profile-tuned-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

$more = @{
    VICTORY_WIDE_THREADS          = '6'
    VICTORY_WIDE_SPIN             = '50'
    VICTORY_WIDE_MERGE            = '1'
    VICTORY_FAST_CORES            = '6'
    VICTORY_MAP_THREADS           = '6'
    VICTORY_REFRESH_FRONT         = '1'
    VICTORY_GPU_TIMING            = '1'
    VICTORY_PIPELINE_TIMING       = '1'
    VICTORY_PIPELINE_TIMING_EVERY = '30'
}

& (Join-Path $PSScriptRoot 'play-22fps.ps1') -Game $Game -More $more -LogFile $LogFile
