# CPU-side tuning for heavy scenes (6,000+ draws): the fork's submitter is
# the wall there, while the GPU waits 13-22 ms a frame. These use the 14
# logical CPUs this machine has instead of the laptop-safe defaults:
#   - six wide-refresh workers instead of three;
#   - a short spin before sleeping, so a worker is not woken 50 us late;
#   - shader writes merged into title memory on several threads;
#   - six fast cores and six map threads for the helpers.
#
#   .\scripts\play-tuned.ps1
#   .\scripts\play-tuned.ps1 -Game "D:\path\to\game_scarlett_master.exe"
param(
    [string]$Game = 'D:\my_xbox_game_dump\game_scarlett_master.exe',
    [string]$LogFile
)
$ErrorActionPreference = 'Stop'

$more = @{
    VICTORY_WIDE_THREADS  = '6'
    VICTORY_WIDE_SPIN     = '50'
    VICTORY_WIDE_MERGE    = '1'
    VICTORY_FAST_CORES    = '6'
    VICTORY_MAP_THREADS   = '6'
    VICTORY_REFRESH_FRONT = '1'
}

& (Join-Path $PSScriptRoot 'play-22fps.ps1') -Game $Game -More $more -LogFile $LogFile
