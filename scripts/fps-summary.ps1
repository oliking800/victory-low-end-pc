# Summarises the 5-second frame lines of a victory log: how long a frame took
# and where the time went. The frames of loading screens and menus are left
# out by the draw count, and the last samples (the window closing) by default.
#
#   .\scripts\fps-summary.ps1 -Log target\bench\base.log
#   .\scripts\fps-summary.ps1 -Log target\bench\base.log -LastSeconds 120
#
# Median and p90 are of the milliseconds per frame: the frame time is what the
# eye feels, and averaging fps hides the long frames.
param(
    [Parameter(Mandatory)][string]$Log,
    # A world frame draws this many or more. Menus 4-30, loading spikes 2000+.
    [int]$MinDraw = 400,
    # Only this many seconds before the last sample (0: every world sample).
    [double]$LastSeconds = 0,
    # Samples at the end to leave out (the window closing is one very long frame).
    [int]$DropLast = 1,
    # Leave out everything up to and including the last sample at least this
    # long (ms): the loading and pipeline stalls are not the world (0: keep all).
    [double]$AfterLastSpike = 100,
    [switch]$PerSample
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Log)) { throw "No $Log" }

$desen = [regex]'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z).*?([\d.]+) fps, ([\d.]+) ms/frame \(([\d.]+) preparing: copies ([\d.]+) ms ([\d.]+) MB, textures ([\d.]+) ms ([\d.]+) MB; ([\d.]+) on the GPU; ([\d.]+) copying back ([\d.]+) MB\), (\d+) draws/frame, dropped (\d+) without a host pipeline \((\d+) being made\) and (\d+) indirect'
$ansi = [regex]'\x1b\[[0-9;]*m'
$kareler = [System.Collections.Generic.List[object]]::new()
$sr = [IO.StreamReader]::new([IO.File]::OpenRead((Resolve-Path -LiteralPath $Log)))
try {
    while ($null -ne ($l = $sr.ReadLine())) {
        $l = $ansi.Replace($l, '')
        $m = $desen.Match($l)
        if (-not $m.Success) { continue }
        if ([int]$m.Groups[12].Value -lt $MinDraw) { continue }
        $kareler.Add([pscustomobject]@{
            T      = [datetime]::Parse($m.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)
            Fps    = [double]$m.Groups[2].Value
            Ms     = [double]$m.Groups[3].Value
            Prep   = [double]$m.Groups[4].Value
            CopyMs = [double]$m.Groups[5].Value
            CopyMb = [double]$m.Groups[6].Value
            TexMs  = [double]$m.Groups[7].Value
            TexMb  = [double]$m.Groups[8].Value
            Gpu    = [double]$m.Groups[9].Value
            BackMs = [double]$m.Groups[10].Value
            BackMb = [double]$m.Groups[11].Value
            Draw   = [int]$m.Groups[12].Value
            Drop   = [int]$m.Groups[13].Value
            Making = [int]$m.Groups[14].Value
            Ind    = [int]$m.Groups[15].Value
        })
    }
} finally { $sr.Dispose() }

if ($DropLast -gt 0) { $kareler.RemoveRange([Math]::Max(0, $kareler.Count - $DropLast), [Math]::Min($DropLast, $kareler.Count)) }
if ($LastSeconds -gt 0 -and $kareler.Count) {
    $son = $kareler[$kareler.Count - 1].T
    $kareler = @($kareler | Where-Object { ($son - $_.T).TotalSeconds -le $LastSeconds })
}
$spike = ''
if ($AfterLastSpike -gt 0 -and $kareler.Count) {
    $cut = -1
    for ($i = 0; $i -lt $kareler.Count; $i++) { if ($kareler[$i].Ms -ge $AfterLastSpike) { $cut = $i } }
    if ($cut -ge 0) {
        $spike = " (settled at $($kareler[$cut].T.ToString('HH:mm:ss')), $($cut + 1) samples left out)"
        $kareler = @($kareler | Select-Object -Skip ($cut + 1))
    }
}
if ($kareler.Count -eq 0) { "no world frames (draw >= $MinDraw)"; exit 1 }

function Get-Medyan([double[]]$x) {
    if (-not $x -or $x.Count -eq 0) { return 0 }
    $s = @($x | Sort-Object); $n = $s.Count
    if ($n % 2) { return $s[[int](($n - 1) / 2)] } else { return ($s[$n / 2 - 1] + $s[$n / 2]) / 2 }
}
function Get-Yuzde([double[]]$x, [double]$p) {
    $s = @($x | Sort-Object); if ($s.Count -eq 0) { return 0 }
    return $s[[Math]::Min($s.Count - 1, [int][Math]::Floor($s.Count * $p))]
}
$ms = [double[]]@($kareler | ForEach-Object { $_.Ms })
$fps = [double[]]@($kareler | ForEach-Object { $_.Fps })
$ad = Split-Path $Log -Leaf
$ilk = $kareler[0]; $sonuncu = $kareler[$kareler.Count - 1]
"=== $ad ==="
"world samples: $($kareler.Count) | $($ilk.T.ToString('HH:mm:ss')) .. $($sonuncu.T.ToString('HH:mm:ss')) | draws $(($kareler | Measure-Object Draw -Minimum).Minimum)-$(($kareler | Measure-Object Draw -Maximum).Maximum)$spike"
"ms/frame: median {0:N1} | p90 {1:N1} | p99 {2:N1} | min {3:N1} | max {4:N1}" -f (Get-Medyan $ms), (Get-Yuzde $ms 0.9), (Get-Yuzde $ms 0.99), ($ms | Measure-Object -Minimum).Minimum, ($ms | Measure-Object -Maximum).Maximum
"fps: median {0:N1} | p10 {1:N1}" -f (Get-Medyan $fps), (Get-Yuzde $fps 0.1)
"per frame medians: preparing {0:N1} ms (copies {1:N1} ms / {2:N0} MB, textures {3:N1} ms / {4:N0} MB) | on the GPU {5:N1} | copying back {6:N1} ms / {7:N0} MB" -f `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.Prep }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.CopyMs }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.CopyMb }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.TexMs }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.TexMb }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.Gpu }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.BackMs }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.BackMb })))
"dropped without a host pipeline: median {0:N0} (making {1:N0}) | indirect {2:N0}" -f `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.Drop }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.Making }))), `
    (Get-Medyan ([double[]]@($kareler | ForEach-Object { $_.Ind })))
if ($PerSample) {
    $kareler | ForEach-Object { "{0} | {1,6:N1} ms | {2,5:N1} fps | prep {3,5:N1} | copy {4,4:N1} | tex {5,4:N1} | back {6,5:N1} | draws {7}" -f $_.T.ToString('HH:mm:ss'), $_.Ms, $_.Fps, $_.Prep, $_.CopyMs, $_.TexMs, $_.BackMs, $_.Draw }
}
