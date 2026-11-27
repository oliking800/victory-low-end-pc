# One optimisation run: the 22 fps launcher's settings, a log of its own, and
# the frame summary when the window closes. One setting per run, so the log's
# last minute can be compared with the last run's:
#
#   .\scripts\bench-22fps.ps1 -Tag base
#   .\scripts\bench-22fps.ps1 -Tag wide-merge -More @{ VICTORY_WIDE_MERGE = '1' }
#
# The game is not closed for you: play into the world, walk about a little,
# then close the window yourself. The summary prints at the end.
param(
    [Parameter(Mandatory)][string]$Tag,
    [hashtable]$More = @{},
    [string]$Game = 'D:\my_xbox_game_dump\game_scarlett_master.exe'
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$dir = Join-Path $here '..\target\bench'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir "$Tag.log"

"logging to $log"
& (Join-Path $here 'play-22fps.ps1') -Game $Game -More $More -LogFile $log

& (Join-Path $here 'fps-summary.ps1') -Log $log -LastSeconds 60 -DropLast 1
