# victory-agility-patch

Patches any VIctory-derived fork so it works on **Windows 10**. On Windows 11
it is harmless.

## The problem

Windows 10's in-box D3D12 stops at shader model 6.5 and refuses the
heap-indexed root-signature flags that `victory-gpu` puts on every translated
pipeline:

```
root signature: Unsupported bit-flag set (root signature flags c01)
host root signature refused error=The parameter is incorrect. (0x80070057)
```

With no host pipelines the title faults during `Game Init`
(`0xc0000005` reading `[rax+0x68]` in title code), which looks like a game
crash. The fix is the **D3D12 Agility SDK**: export `D3D12SDKPath` and
`D3D12SDKVersion` from `victory.exe` and keep a newer `D3D12Core.dll` in
`D3D12\` beside it.

## Usage

```powershell
# Patch a fork (finds the crate whose package is named `victory`)
python tools\victory_agility_patch.py D:\path\to\fork

# Supply the Microsoft runtime DLL once; it is copied to <fork>\D3D12\
python tools\victory_agility_patch.py D:\path\to\fork --d3d12-core C:\path\D3D12Core.dll

# Preview without writing
python tools\victory_agility_patch.py D:\path\to\fork --dry-run

# Undo
python tools\victory_agility_patch.py D:\path\to\fork --revert

# Check a built executable
python tools\victory_agility_patch.py --verify-exe cool_fox\target\x86_64-pc-windows-msvc\release\victory.exe
```

On Windows, `tools\agility-patch.cmd` is the same tool:

```powershell
.\tools\agility-patch.cmd D:\path\to\fork --d3d12-core C:\path\D3D12Core.dll
```

## What it changes

- `agility.rs` next to the binary root: the two exported statics
  (`D3D12SDKVersion`, `D3D12SDKPath`).
- the binary root (`src/main.rs`): adds `mod agility;`.
- `build.rs` in the `victory` crate:
  - if absent, writes one that finds/copies `D3D12Core.dll` into
    `<target>/<profile>/D3D12/` and passes the `/EXPORT:` link arguments;
  - if present, inserts a `victory_agility_exports();` call into `fn main()`
    and appends the helper;
  - if it already has the Agility `/EXPORT:` lines but no DLL auto-copy
    (the earlier one-line opt-in), adds `victory_agility_copy_d3d12_core()`
    before its existing check. Custom lines such as
    `cargo:rustc-cfg=agility` are preserved.
- optionally `<fork>/D3D12/D3D12Core.dll` when `--d3d12-core` is given.

It is idempotent. Before modifying an existing file it keeps a backup under
`.victory-agility-patch/`, so `--revert` can restore everything.

## Getting D3D12Core.dll

It is a Microsoft redistributable, **not** part of this repository (`.dll`
files are gitignored). Take `D3D12Core.dll` from the
`Microsoft.Direct3D.D3D12` NuGet package, version **1.620.x**, and put it in
`D3D12\` beside `victory.exe` (the tool can copy it for you). The
`D3D12SDKVersion` static defaults to `620`; if you use another package
version, pass `--sdk-version <minor>`.

At build time the generated `build.rs` also looks for the DLL in
`D3D12/D3D12Core.dll`, the repo root, `cool_fox/D3D12/D3D12Core.dll`, and
`VICTORY_D3D12_CORE`, so a fork that already ships the DLL anywhere in its
tree works without extra steps.

## Verifying

After rebuilding:

```powershell
python tools\victory_agility_patch.py --verify-exe <path-to-victory.exe>
```

Both exports must be present. The tool parses the PE export table itself, so
it needs no `dumpbin`/LLVM installation.

## Limits

- It recognises the package by `[package] name = "victory"`, falling back to
  the one `victory*` package with a binary. Pass `--crate-name` for a renamed
  app crate, or `--crate-path` when a fork has several candidates.
- If the crate already has a build script without a top-level `fn main()`,
  the tool stops and leaves manual instructions rather than guessing.
  A custom `[package] build = "…"` path is honoured; `build = false` cannot be
  patched automatically.
- It patches the first binary root (preferring `src/main.rs`). Other `[[bin]]`
  targets share the same build-script exports.

## Local measurement helpers

`bench_victory.py` runs the title for a fixed time, auto-presses Enter via
`VICTORY_KEYS`, and summarises the frame-stat line (median/p90, first-world
time, VRAM/RAM, exceptions, device removal, refused pipelines). Paths come
from the environment or flags, so nothing is machine-specific:

```powershell
$env:VICTORY_EXE  = '.\cool_fox\target\x86_64-pc-windows-msvc\release\victory.exe'
$env:VICTORY_GAME = 'D:\path\to\game_scarlett_master.exe'
python tools\bench_victory.py --tag baseline --seconds 210
python tools\bench_victory.py --tag low --seconds 210 `
    --set VICTORY_DISPLAY_MODE=1280x720 --set VICTORY_RENDER_SCALE=0.667 `
    --set VICTORY_CARD_BUFFERS_MB=1536 --set VICTORY_CARD_BUFFERS_MIN_KB=64
```

`tweak_game_settings.py` applies a profile to the title's own
`settings.xml` (found under `%LOCALAPPDATA%\victory\data\*\storage\settings\`,
or pass `--path`). It always backs the file up first:

```powershell
python tools\tweak_game_settings.py --profile sharp --dry-run
python tools\tweak_game_settings.py --profile sharp
python tools\tweak_game_settings.py --restore
```

Profiles are `maxfps` (640x480 + heavy quality cuts), `balanced`, and
`sharp` (keeps RT/grass/SSR/motion-blur off but restores texture LOD, mip
bias and anisotropic filtering). The game may rewrite its settings on exit;
apply profiles while `victory.exe` is not running.

## Easy launcher

`victory_easy.py` (and `victory-easy.cmd` at the repo root) is the
one-file, one-command entry point: it reads `victory-easy.env`, detects VRAM
and RAM, picks a profile, applies the title's sharp settings, and launches.
See the "Easy mode (Windows)" section of the main README.

```powershell
python tools\victory_easy.py --init
python tools\victory_easy.py --dry-run
python tools\victory_easy.py --show-env
```
