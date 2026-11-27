#!/usr/bin/env python3
"""victory-easy: one friendly config and one command to run the fork.

Edit `victory-easy.env` (copy the example), set GAME, then run:

    victory-easy.cmd
    python tools\\victory_easy.py --dry-run
    python tools\\victory_easy.py --show-env

The utility detects the GPU's VRAM and the system RAM, picks a profile
(performance / balanced / quality), applies the title's own settings profile
(sharp / balanced / maxfps), checks the D3D12 Agility SDK pieces, and starts
the title. Every VICTORY_* line in the env file still overrides the profile.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "victory-easy.env"
EXAMPLE = ROOT / "victory-easy.env.example"
DEFAULT_EXE = ROOT / "cool_fox" / "target" / "x86_64-pc-windows-msvc" / "release" / "victory.exe"
GAME_SETTINGS_TOOL = ROOT / "tools" / "tweak_game_settings.py"

# Per-profile defaults.  All values are the friendly level; build_settings()
# turns them into VICTORY_* variables.
PROFILES = {
    "performance": {
        "resolution": "1280x720",
        "render_scale": "0.5",
        "game_quality": "maxfps",
        "card_buffers_mb": "1024",
        "texture_budget_mb": "1024",
        "texture_room_percent": "85",
        "windows_bar_mb": "2048",
        "window_kb": "256",
        "mip_drop": "1",
        "staging_kept": "4",
        "max_preludes": "32",
        "send_kept_mb": "256",
    },
    "balanced": {
        "resolution": "1280x720",
        "render_scale": "0.667",
        "game_quality": "sharp",
        "card_buffers_mb": "1536",
        "texture_budget_mb": "1536",
        "texture_room_percent": "88",
        "windows_bar_mb": "3072",
        "window_kb": "256",
        "mip_drop": "1",
        "staging_kept": "4",
        "max_preludes": "32",
        "send_kept_mb": "512",
    },
    "quality": {
        "resolution": "1920x1080",
        "render_scale": "1.0",
        "game_quality": "sharp",
        "card_buffers_mb": "2048",
        "texture_budget_mb": "2048",
        "texture_room_percent": "90",
        "windows_bar_mb": "4096",
        "window_kb": "512",
        "mip_drop": "1",
        "staging_kept": "4",
        "max_preludes": "32",
        "send_kept_mb": "512",
    },
}

FRIENDLY = {
    "PROFILE",
    "GAME",
    "EXE",
    "RESOLUTION",
    "RENDER_SCALE",
    "QUALITY",
    "CONSOLE",
    "PANEL",
    "DEBUG_LOG",
    "AUTO_ENTER",
    "SKIP_INTRO",
    "VRAM_GB",
    "RAM_GB",
}

AUTO_ENTER_KEYS = ",".join(
    [f"{t}-{t + 2.5}:Enter" for t in range(20, 149, 3)] + ["149-150:Enter"]
)


class EasyError(RuntimeError):
    pass


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" not in line:
            raise EasyError(f"{path}:{number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip().upper()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def detect_gpu():
    """Return (name, VRAM GB) from nvidia-smi, or (None, None)."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if out.returncode != 0:
            return None, None
        best = (None, 0.0)
        for line in out.stdout.splitlines():
            if not line.strip():
                continue
            name, _, mem = line.rpartition(",")
            try:
                gb = float(mem.strip()) / 1024.0
            except ValueError:
                continue
            if gb > best[1]:
                best = (name.strip() or "NVIDIA GPU", gb)
        return best[0], (best[1] or None)
    except (OSError, subprocess.SubprocessError):
        return None, None


def detect_ram_gb():
    if os.name != "nt":
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
        except (AttributeError, ValueError, OSError):
            return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullTotalPhys / 1024**3


def choose_profile(requested: str, vram: float, ram: float):
    if requested != "auto":
        return requested, requested
    if vram >= 12:
        return "quality", f"auto: {vram:.0f} GB VRAM"
    if vram >= 6:
        return "balanced", f"auto: {vram:.0f} GB VRAM"
    return "performance", f"auto: {vram:.0f} GB VRAM"


def parse_scale(value: str) -> float:
    try:
        scale = float(value)
    except ValueError as exc:
        raise EasyError(f"RENDER_SCALE must be a number, not {value!r}") from exc
    if not 0.2 <= scale <= 1.0:
        raise EasyError("RENDER_SCALE must be between 0.2 and 1.0")
    return scale


def build_settings(profile: str, vram: float, ram: float, config: dict[str, str]):
    defaults = dict(PROFILES[profile])
    if ram < 16:
        defaults["staging_kept"] = "2"
        defaults["max_preludes"] = "16"
        defaults["send_kept_mb"] = "128"
        defaults["texture_budget_mb"] = str(min(int(defaults["texture_budget_mb"]), 1024))
        defaults["windows_bar_mb"] = str(min(int(defaults["windows_bar_mb"]), 2048))
    if vram < 6 and profile == "performance":
        defaults["card_buffers_mb"] = "768"
        defaults["texture_budget_mb"] = "768"
        defaults["windows_bar_mb"] = "1536"
        defaults["mip_drop"] = "2"

    resolution = config.get("RESOLUTION") or defaults["resolution"]
    if not re.fullmatch(r"\d{3,4}x\d{3,4}", resolution):
        raise EasyError(f"RESOLUTION must look like 1280x720, not {resolution!r}")
    scale = parse_scale(config.get("RENDER_SCALE") or defaults["render_scale"])
    quality = (config.get("QUALITY") or defaults["game_quality"]).lower()
    if quality not in {"sharp", "balanced", "maxfps", "off"}:
        raise EasyError("QUALITY must be sharp, balanced, maxfps or off")
    console = (config.get("CONSOLE") or "series-s").lower()
    if console not in {"series-s", "series-x"}:
        raise EasyError("CONSOLE must be series-s or series-x")
    panel = config.get("PANEL", "0") or "0"
    if panel not in {"0", "1"}:
        raise EasyError("PANEL must be 0 or 1")
    debug = (config.get("DEBUG_LOG", "0") or "0") in {"1", "true", "yes", "on"}

    settings = {
        "VICTORY_DISPLAY_MODE": resolution,
        "VICTORY_WINDOW_MAX": resolution,
        "VICTORY_RENDER_SCALE": f"{scale:g}",
        "VICTORY_OWN_UPSCALER": "1" if scale < 1.0 else "0",
        "VICTORY_CARD_BUFFERS_MB": defaults["card_buffers_mb"],
        "VICTORY_CARD_BUFFERS_MIN_KB": "64",
        "VICTORY_CARD_WINDOWS_MB": "0",
        "VICTORY_TEXTURE_BUDGET_MB": defaults["texture_budget_mb"],
        "VICTORY_TEXTURE_ROOM_PERCENT": defaults["texture_room_percent"],
        "VICTORY_WINDOWS_BAR_MB": defaults["windows_bar_mb"],
        "VICTORY_WINDOWS_BAR_PERCENT": "88",
        "VICTORY_WINDOW_KB": defaults["window_kb"],
        "VICTORY_WINDOW_TAILS": "1",
        "VICTORY_SEND_KEPT_MB": defaults["send_kept_mb"],
        "VICTORY_DYNAMIC_SLOTS": "524288",
        "VICTORY_TEXTURE_MIP_DROP": defaults["mip_drop"],
        "VICTORY_LEVELS_ON_DEMAND": "1",
        "VICTORY_STAGING_KEPT": defaults["staging_kept"],
        "VICTORY_MAX_PRELUDES": defaults["max_preludes"],
        "VICTORY_MAP_THREADS": "4",
        "VICTORY_FAST_CORES": "3",
        "VICTORY_TITLE_PRIORITIES": "1",
        "VICTORY_PANEL": panel,
        "VICTORY_D3D12_DRED": "0",
        "VICTORY_CARD_ACCOUNTING": "0",
        "VICTORY_PIPELINE_BOOK": "0",
        "VICTORY_MEMORY_MAP": "0",
        "VICTORY_AMBIENT": "0.8",
        "VICTORY_AMBIENT_AIR": "1.5",
        "VICTORY_CARD_AWAKE": "1",
        "VICTORY_CARD_REHASH_RUNS": "1",
        "VICTORY_CARD_STEPS": "2",
        "VICTORY_JOIN_COPIES": "1",
        "VICTORY_INDIRECT_BATCH": "2",
        "VICTORY_INDIRECT_WINDOW": "1",
        "VICTORY_RELAY": "2",
        "VICTORY_RELAY_COPY": "1",
        "VICTORY_TEXTURE_NO_WAIT": "1",
        "VICTORY_WIDE_BACK": "1",
        "VICTORY_RAW_VIEWS": "0",
        "VICTORY_GROUP_SYNC": "2",
        "VICTORY_WAVE_LOCAL": "idiom",
        "VICTORY_SHOW_AFTER": "1",
        "VICTORY_UPLOAD_AHEAD": "1",
        "VICTORY_THIN": "1",
        "VICTORY_JOIN_PARTS": "8",
        "VICTORY_LOG": "debug" if debug else "info",
    }
    if config.get("AUTO_ENTER", "0").lower() in {"1", "true", "yes", "on"}:
        settings["VICTORY_KEYS"] = AUTO_ENTER_KEYS

    # Keep the user's path variables unless the profile or an override says
    # otherwise.
    for key in ("VICTORY_CONFIG", "VICTORY_GAME_DIR", "VICTORY_CACHE_DIR", "VICTORY_DATA_DIR"):
        if key in os.environ:
            settings.setdefault(key, os.environ[key])

    # Any VICTORY_* line in the env file is an advanced override.
    for key, value in config.items():
        if not key.startswith("VICTORY_"):
            continue
        if value == "":
            settings.pop(key, None)
        else:
            settings[key] = value
    settings.pop("VICTORY_WAVE_WIDE", None)
    return settings, resolution, scale, quality, console


def check_agility(exe: Path):
    warnings = []
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from victory_agility_patch import pe_exports  # type: ignore

        names = pe_exports(exe)
        if "D3D12SDKPath" not in names or "D3D12SDKVersion" not in names:
            warnings.append(
                "this victory.exe has no D3D12 Agility exports; on Windows 10 rebuild with scripts\\build.ps1"
            )
    except Exception:
        pass
    if not (exe.parent / "D3D12" / "D3D12Core.dll").is_file():
        warnings.append(
            "D3D12\\D3D12Core.dll is not beside victory.exe; Windows 10 needs it (scripts\\build.ps1 copies it)"
        )
    return warnings


def apply_game_quality(quality: str, dry: bool):
    if quality == "off" or dry:
        return
    if not GAME_SETTINGS_TOOL.is_file():
        print("warning: tools\\tweak_game_settings.py not found; game settings left as they are")
        return
    result = subprocess.run(
        [sys.executable, str(GAME_SETTINGS_TOOL), "--profile", quality],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"game settings: {quality} applied (backup kept; undo with --restore)")
    else:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = detail[0] if detail else "unknown error"
        print(f"warning: game settings not applied ({reason})")


def format_summary(profile, reason, game, exe, settings, quality, console):
    lines = [
        f"victory-easy: {profile} profile ({reason})",
        f"  game       {game}",
        f"  runner     {exe}",
        f"  display    {settings['VICTORY_DISPLAY_MODE']}, render scale {settings['VICTORY_RENDER_SCALE']}",
        f"  quality    {quality} (title settings)",
        f"  console    {console}",
        f"  card       {settings['VICTORY_CARD_BUFFERS_MB']} MB buffers, "
        f"{settings['VICTORY_TEXTURE_BUDGET_MB']} MB textures, "
        f"{settings['VICTORY_WINDOWS_BAR_MB']} MB BAR",
        f"  RAM        staging {settings['VICTORY_STAGING_KEPT']}, "
        f"preludes {settings['VICTORY_MAX_PRELUDES']}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Easy launcher for this VIctory fork: one env file, one command."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--init", action="store_true", help="create victory-easy.env from the example")
    parser.add_argument("--game", help="title executable (overrides GAME)")
    parser.add_argument("--exe", help="victory.exe (overrides EXE)")
    parser.add_argument("--profile", choices=["auto", "performance", "balanced", "quality"])
    parser.add_argument("--quality", choices=["sharp", "balanced", "maxfps", "off"])
    parser.add_argument("--resolution", help="e.g. 1280x720")
    parser.add_argument("--render-scale", type=str, help="0.2 to 1.0")
    parser.add_argument("--console", choices=["series-s", "series-x"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show-env", action="store_true", help="print the resulting VICTORY_* values")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if args.init:
        if config_path.exists():
            print(f"victory-easy: {config_path} already exists")
            return 0
        if not EXAMPLE.is_file():
            print(f"victory-easy: no {EXAMPLE}", file=sys.stderr)
            return 1
        shutil.copy2(EXAMPLE, config_path)
        print(f"victory-easy: created {config_path}")
        print("Set GAME to your own copy's executable, then run victory-easy.cmd again.")
        return 0

    if not config_path.is_file():
        print(f"victory-easy: no {config_path}", file=sys.stderr)
        print("Run: python tools\\victory_easy.py --init", file=sys.stderr)
        return 2

    try:
        config = read_env(config_path)
        for key in config:
            if key not in FRIENDLY and not key.startswith("VICTORY_"):
                print(f"victory-easy: ignoring unknown setting {key}", file=sys.stderr)

        for key, value in (
            ("PROFILE", args.profile),
            ("QUALITY", args.quality),
            ("RESOLUTION", args.resolution),
            ("RENDER_SCALE", args.render_scale),
            ("CONSOLE", args.console),
            ("GAME", args.game),
            ("EXE", args.exe),
        ):
            if value:
                config[key] = value

        game = Path(config.get("GAME", "")).expanduser()
        if not config.get("GAME"):
            raise EasyError(
                "GAME is not set. Edit victory-easy.env and point GAME at your own "
                "game_scarlett_master.exe."
            )
        game = game if game.is_absolute() else (ROOT / game)
        if not game.is_file():
            raise EasyError(f"GAME does not exist: {game}")

        exe_value = config.get("EXE", "")
        exe = Path(exe_value).expanduser() if exe_value else DEFAULT_EXE
        exe = exe if exe.is_absolute() else (ROOT / exe)
        if not exe.is_file():
            raise EasyError(f"EXE does not exist: {exe} (build it with scripts\\build.ps1)")

        gpu_name, detected_vram = detect_gpu()
        detected_ram = detect_ram_gb()
        vram = float(config.get("VRAM_GB") or 0) or detected_vram or 8.0
        ram = float(config.get("RAM_GB") or 0) or detected_ram or 16.0
        requested = (config.get("PROFILE") or "auto").lower()
        if requested not in {"auto", "performance", "balanced", "quality"}:
            raise EasyError("PROFILE must be auto, performance, balanced or quality")
        profile, reason = choose_profile(requested, vram, ram)

        settings, resolution, scale, quality, console = build_settings(profile, vram, ram, config)
        if args.quality:
            quality = args.quality
        if args.console:
            console = args.console
        skip_intro = config.get("SKIP_INTRO", "0").lower() in {"1", "true", "yes", "on"}

        print(format_summary(profile, reason, game, exe, settings, quality, console))
        if gpu_name:
            print(f"  GPU        {gpu_name} ({vram:.0f} GB)")
        if skip_intro:
            print("  intro      skipped (-skipToIIS, for testing)")
        if args.show_env:
            print()
            for key in sorted(settings):
                print(f"{key}={settings[key]}")
        for warning in check_agility(exe):
            print(f"warning: {warning}", file=sys.stderr)
        try:
            if b"VICTORY_RENDER_SCALE" not in exe.read_bytes():
                print(
                    "note: this build does not read VICTORY_RENDER_SCALE; it "
                    "renders its native resolution (quality is not reduced).",
                    file=sys.stderr,
                )
        except OSError:
            pass

        title_args = ["-skipToIIS"] if skip_intro else []
        if args.dry_run:
            print("\ndry run: would apply the game settings profile and launch:")
            suffix = " -- " + " ".join(title_args) if title_args else ""
            print(
                f'  "{exe}" run "{game}" --execute --console {console}{suffix}'
            )
            return 0

        apply_game_quality(quality, dry=False)
        env = {k: v for k, v in os.environ.items() if not k.startswith("VICTORY_")}
        env.update(settings)
        cmd = [str(exe), "run", str(game), "--execute", "--console", console]
        if title_args:
            cmd += ["--", *title_args]
        print("starting victory...")
        try:
            return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode
        except KeyboardInterrupt:
            return 130
    except EasyError as exc:
        print(f"victory-easy: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
