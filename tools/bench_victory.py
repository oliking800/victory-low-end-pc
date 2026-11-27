#!/usr/bin/env python3
"""Run victory for a fixed time and summarise its frame statistics.

Builds on the laptop fork's baseline settings (calisma/araclar/kosu.ps1) but
keeps every path local.  One run per invocation; use --set for a single
setting change so comparisons stay honest.

Usage:
    python tools/bench_victory.py --tag baseline --seconds 210
    python tools/bench_victory.py --tag card-buffers-1024 --seconds 210 ^
        --set VICTORY_CARD_BUFFERS_MB=1024
    python tools/bench_victory.py --tag smoke --seconds 150 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EXE = os.environ.get(
    "VICTORY_EXE", "cool_fox/target/x86_64-pc-windows-msvc/release/victory.exe"
)
DEFAULT_GAME = os.environ.get("VICTORY_GAME", "")
DEFAULT_CWD = os.environ.get("VICTORY_CWD", ".")
DEFAULT_OUT = os.environ.get("VICTORY_BENCH_OUT", "bench/runs")

# calisma/araclar/kosu.ps1 baseline on 2026-11-26 (B13b / c0 without lto),
# with the later RT/upscaler/clamp additions.
BASE = {
    # From calisma/araclar/olcum_profili.ps1's defaults + kosu.ps1's set.
    "VICTORY_DISPLAY_MODE": "1920x1080",
    "VICTORY_CARD_BUFFERS_MB": "512",
    "VICTORY_TEXTURE_ROOM_PERCENT": "85",
    "VICTORY_RT_RESOLVE": "0",
    "VICTORY_ACTIVATE_RAYS": "0",
    "VICTORY_CARD_ACCOUNTING": "1",
    "VICTORY_AMBIENT": "0.8",
    "VICTORY_BOOK": "0",
    "VICTORY_CARD_AWAKE": "0",
    "VICTORY_CARD_REHASH_RUNS": "1",
    "VICTORY_CARD_STEPS": "2",
    "VICTORY_D3D12_DRED": "light",
    "VICTORY_DYNAMIC_SLOTS": "524288",
    "VICTORY_BVH_MISS": "1",
    "VICTORY_PANEL": "1",
    "VICTORY_CLAMP_WAITS": "0",
    "VICTORY_OWN_UPSCALER": "1",
    "VICTORY_RENDER_SCALE": "0.5",
    "VICTORY_RT_SKIP_RESOLVE": "1",
    "VICTORY_RT_SKIP_ACTIVATE": "1",
    "VICTORY_INDIRECT_BATCH": "2",
    "VICTORY_INDIRECT_WINDOW": "1",
    "VICTORY_JOIN_COPIES": "1",
    "VICTORY_LAND_ECHO": "0",
    "VICTORY_MAP_THREADS": "1",
    "VICTORY_MEMORY_MAP": "1",
    "VICTORY_PIPELINE_BOOK": "1",
    "VICTORY_RELAY": "2",
    "VICTORY_RELAY_COPY": "1",
    "VICTORY_SEND_KEPT_MB": "128",
    "VICTORY_SHOW_AFTER": "1",
    "VICTORY_TEXTURE_BUDGET_MB": "1024",
    "VICTORY_TEXTURE_NO_WAIT": "1",
    "VICTORY_TITLE_PRIORITIES": "0",
    "VICTORY_UNDER_WIDE": "0",
    "VICTORY_WIDE_BACK": "1",
    "VICTORY_WINDOW_KB": "256",
    "VICTORY_WINDOW_TAILS": "1",
    "VICTORY_WINDOWS_BAR_MB": "2048",
    "VICTORY_WINDOWS_BAR_PERCENT": "88",
    "VICTORY_LOG": "info",
}

ANSI = re.compile(r"\x1b\[[0-9;]*m")
FRAME = re.compile(r"([\d.]+) fps, ([\d.]+) ms/frame.*?(\d+) draws/frame")
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z)")
PRIVATE = re.compile(r"memory: (\d+) MB private .*?the PC has (\d+) MB free")
VIDEO = re.compile(r"card's own: budget (\d+) MB, in use (\d+) MB")
SHARED = re.compile(r"shared with the card: budget \d+ MB, in use (\d+) MB")
PRESENT = re.compile(r"frame presented .*?frame=(\d+)")


def keys_pattern() -> str:
    # 20-150 s, Enter held 2.5 s and released 0.5 s, as the laptop harness.
    parts = [f"{t}-{t + 2.5}:Enter" for t in range(20, 149, 3)]
    parts.append("149-150:Enter")
    return ",".join(parts)


def parse_time(line: str):
    m = TS.match(line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )


def parse_log(path: Path, world_draw: int, warmup: int):
    frames = []  # (t, ms, draws)
    first_ts = None
    private = []
    video = []
    shared = []
    last_frame = None
    counts = {
        "unhandled_exception": 0,
        "first_chance_exception": 0,
        "device_removed": 0,
        "oom_8007000e": 0,
        "root_signature_refused": 0,
        "no_frame_presented": 0,
        "dropped_without_pipeline": 0,
        "shader_no_translate": 0,
        "title_exited": 0,
    }
    lines = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = ANSI.sub("", raw.rstrip("\r\n"))
            lines.append(line)
            if TS.match(line) and first_ts is None:
                first_ts = parse_time(line)
            m = FRAME.search(line)
            if m:
                t = parse_time(line)
                if t is not None:
                    frames.append(
                        (t, float(m.group(2)), int(m.group(3)))
                    )
            m = PRIVATE.search(line)
            if m:
                private.append((parse_time(line), int(m.group(1)), int(m.group(2))))
            m = VIDEO.search(line)
            if m:
                video.append((parse_time(line), int(m.group(1)), int(m.group(2))))
            m = SHARED.search(line)
            if m:
                shared.append((parse_time(line), int(m.group(1))))
            m = PRESENT.search(line)
            if m:
                last_frame = int(m.group(1))
            low = line.lower()
            if "unhandled exception" in low:
                counts["unhandled_exception"] += 1
            if "first-chance exception" in low:
                counts["first_chance_exception"] += 1
            if "device removed" in low or "0x887a000" in low:
                counts["device_removed"] += 1
            if "0x8007000e" in low:
                counts["oom_8007000e"] += 1
            if "host root signature refused" in low:
                counts["root_signature_refused"] += 1
            if "no frame presented" in low:
                counts["no_frame_presented"] += 1
            if "a dispatch without a host pipeline" in low:
                counts["dropped_without_pipeline"] += 1
            if "shader does not translate" in low:
                counts["shader_no_translate"] += 1
            if "title exited" in low:
                counts["title_exited"] += 1

    first_world = None
    for t, ms, draws in frames:
        if draws >= world_draw:
            first_world = t
            break
    if first_world is None and frames and first_ts is not None:
        # Fallback: the first frame after two minutes, if the draw threshold
        # is not reached in this scene/quality profile.
        first_world = first_ts.timestamp() + 120
        first_world = next(
            (t for t, _, _ in frames if t.timestamp() >= first_world), None
        )

    world = []
    if first_world is not None:
        start = first_world.timestamp() + warmup
        world = [(t, ms, draws) for t, ms, draws in frames if t.timestamp() >= start]
    if not world:
        world = frames

    values = [ms for _, ms, _ in world]
    median = statistics.median(values) if values else 0.0
    p90 = (
        sorted(values)[min(len(values) - 1, int(len(values) * 0.9))]
        if values
        else 0.0
    )
    first_world_s = (
        int((first_world - first_ts).total_seconds())
        if first_world is not None and first_ts is not None
        else -1
    )

    def last(samples, index):
        return samples[-1][index] if samples else None

    return {
        "lines": len(lines),
        "frames": len(frames),
        "first_world_s": first_world_s,
        "world_frames": len(world),
        "median_ms": round(median, 2),
        "fps": round(1000 / median, 2) if median else 0.0,
        "p90_ms": round(p90, 2),
        "last_presented_frame": last_frame,
        "private_mb": last(private, 1),
        "pc_free_mb": last(private, 2),
        "video_used_mb": last(video, 2),
        "video_budget_mb": last(video, 1),
        "shared_used_mb": last(shared, 1),
        **counts,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=DEFAULT_EXE)
    parser.add_argument("--game", default=DEFAULT_GAME)
    parser.add_argument("--cwd", default=DEFAULT_CWD)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--seconds", type=int, default=210)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--world-draw", type=int, default=2000)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override one setting (repeatable); KEY= (empty) unsets it",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--console", default="series-s")
    parser.add_argument(
        "--title-arg",
        action="append",
        default=[],
        help="argument passed to the title after -- (repeatable), e.g. -skipToIIS",
    )
    parser.add_argument(
        "--no-keys",
        action="store_true",
        help="do not auto-press Enter (for testing -skipToIIS on its own)",
    )
    args = parser.parse_args(argv)
    if not args.game:
        parser.error("--game or VICTORY_GAME must name the title executable")
    if not Path(args.exe).is_file():
        parser.error(f"no victory executable at {args.exe} (use --exe or VICTORY_EXE)")

    env = {k: v for k, v in os.environ.items() if not k.startswith("VICTORY_")}
    settings = dict(BASE)
    for item in args.set:
        key, _, value = item.partition("=")
        if not key:
            parser.error(f"bad --set {item!r}")
        if value == "":
            settings.pop(key, None)
        else:
            settings[key] = value
    settings.setdefault("VICTORY_KEYS", keys_pattern())
    if args.no_keys:
        settings.pop("VICTORY_KEYS", None)
    env.update(settings)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / f"{stamp}_{args.tag}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "run.log"
    (run_dir / "settings.json").write_text(
        json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cmd = [
        args.exe,
        "run",
        args.game,
        "--console",
        args.console,
        "--execute",
    ]
    if args.title_arg:
        cmd.extend(["--", *args.title_arg])
    (run_dir / "command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    print(f"run       {run_dir}")
    print(f"exe       {args.exe}")
    print(f"seconds   {args.seconds}")
    for key in sorted(settings):
        if key.startswith("VICTORY_"):
            print(f"  {key}={settings[key]}")
    if args.dry_run:
        return 0

    existing = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq victory.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    ).stdout
    if "victory.exe" in existing.lower():
        print("warning: a victory.exe is already running; stop it first", file=sys.stderr)
        return 2

    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=args.cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        killed = False
        try:
            while True:
                if proc.poll() is not None:
                    break
                if time.monotonic() - started >= args.seconds:
                    killed = True
                    break
                time.sleep(1)
        finally:
            if proc.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                )
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()

    exit_code = proc.returncode
    summary = parse_log(log_path, args.world_draw, args.warmup)
    summary.update(
        {
            "tag": args.tag,
            "exe": args.exe,
            "game": args.game,
            "seconds": args.seconds,
            "killed": killed,
            "exit_code": exit_code,
            "settings": settings,
            "title_args": args.title_arg,
        }
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    text = [
        f"tag           {args.tag}",
        f"run           {run_dir}",
        f"exit          {exit_code} (killed={killed})",
        f"first world   {summary['first_world_s']} s",
        f"world frames  {summary['world_frames']} (all {summary['frames']})",
        f"median        {summary['median_ms']} ms  ({summary['fps']} fps)",
        f"p90           {summary['p90_ms']} ms",
        f"last frame    {summary['last_presented_frame']}",
        f"video         {summary['video_used_mb']}/{summary['video_budget_mb']} MB",
        f"shared        {summary['shared_used_mb']} MB",
        f"private       {summary['private_mb']} MB (PC free {summary['pc_free_mb']} MB)",
        "stability     "
        + ", ".join(
            f"{k}={summary[k]}"
            for k in (
                "unhandled_exception",
                "first_chance_exception",
                "device_removed",
                "oom_8007000e",
                "root_signature_refused",
                "no_frame_presented",
                "dropped_without_pipeline",
                "shader_no_translate",
            )
        ),
    ]
    (run_dir / "summary.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print()
    print("\n".join(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
