# GPU profile run: per-command time (`VICTORY_GPU_TIMING`) and the top
# pipelines by GPU time (`VICTORY_PIPELINE_TIMING`). Play for a minute or two
# in the scene you care about; the log gets a summary every five seconds.
#
#   .\scripts\profile-gpu.ps1
#   .\scripts\profile-gpu.ps1 -Game "D:\path\to\game_scarlett_master.exe"
#
# The summaries name the top pipelines by shader hash and role, so the next
# optimization can target the shaders that actually cost the frame.
param(
    [string]$Game = 'D:\my_xbox_game_dump\game_scarlett_master.exe',
    [string]$LogFile
)
$ErrorActionPreference = 'Stop'

if (-not $LogFile) {
    $LogFile = Join-Path $PSScriptRoot ('..\logs\profile-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
}

$more = @{
    VICTORY_GPU_TIMING             = '1'
    VICTORY_PIPELINE_TIMING        = '1'
    VICTORY_PIPELINE_TIMING_EVERY  = '30'
    VICTORY_LOG                    = 'info'
}

& (Join-Path $PSScriptRoot 'play-22fps.ps1') -Game $Game -More $more -LogFile $LogFile
