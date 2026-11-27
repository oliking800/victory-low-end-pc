//! The D3D12 Agility SDK exports (`src/agility.rs`, for Windows 10): D3D12
//! finds them on the executable and then loads the runtime from `D3D12\`
//! beside it. Exported only when `D3D12\D3D12Core.dll` is beside the
//! executable at build time: with the exports but no DLL, device creation
//! fails with `D3D12_ERROR_INVALID_REDIST`. Without them the in-box runtime
//! is used (Windows 11), as before. Only the MSVC linker takes /EXPORT on a
//! binary. After putting the DLL there (or taking it away), build again.

use std::path::PathBuf;

fn main() {
    victory_agility_copy_d3d12_core();
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo::rustc-check-cfg=cfg(agility)");
    // OUT_DIR is <target>/<profile>/build/<package>-<hash>/out; the exe and
    // its D3D12\ folder are in <target>/<profile>/.
    let out = PathBuf::from(std::env::var_os("OUT_DIR").expect("cargo sets OUT_DIR"));
    let Some(profile) = out.ancestors().nth(3) else {
        return;
    };
    let dir = profile.join("D3D12");
    let core = dir.join("D3D12Core.dll");
    // Seen again when the folder or the DLL comes or goes.
    println!("cargo:rerun-if-changed={}", dir.display());
    let msvc = std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc");
    if msvc && core.exists() {
        println!("cargo:rerun-if-changed={}", core.display());
        println!("cargo:rustc-link-arg-bins=/EXPORT:D3D12SDKVersion,DATA");
        println!("cargo:rustc-link-arg-bins=/EXPORT:D3D12SDKPath,DATA");
        println!("cargo:rustc-cfg=agility");
        println!("cargo:warning=D3D12\\D3D12Core.dll found: Agility SDK exports on (Windows 10)");
    }
}


// --- victory-agility-patch (auto-copy) -------------------------------------
// A build.rs that already exports the Agility SDK symbols still needs the
// DLL beside the exe. Find it in the tree and copy it into this profile's
// D3D12\ folder before the existing core.exists() check runs.
fn victory_agility_copy_d3d12_core() {
    let out = std::path::PathBuf::from(
        std::env::var_os("OUT_DIR").expect("cargo sets OUT_DIR"),
    );
    let profile = match out.ancestors().nth(3) {
        Some(profile) => profile,
        None => return,
    };
    let dir = profile.join("D3D12");
    let core = dir.join("D3D12Core.dll");
    if core.is_file() {
        return;
    }
    if let Some(src) = victory_agility_find_d3d12_core(profile) {
        println!("cargo:rerun-if-changed={}", src.display());
        if std::fs::create_dir_all(&dir).is_ok() && std::fs::copy(&src, &core).is_ok() {
            println!(
                "cargo:warning=D3D12Core.dll copied from {} (Windows 10 Agility SDK)",
                src.display()
            );
        }
    }
}

fn victory_agility_find_d3d12_core(profile: &std::path::Path) -> Option<std::path::PathBuf> {
    if let Some(p) = std::env::var_os("VICTORY_D3D12_CORE") {
        let p = std::path::PathBuf::from(p);
        if p.is_file() {
            return Some(p);
        }
    }
    let mut roots = Vec::new();
    if let Some(m) = std::env::var_os("CARGO_MANIFEST_DIR") {
        roots.push(std::path::PathBuf::from(m));
    }
    roots.push(profile.to_path_buf());
    for root in &roots {
        for at in root.ancestors() {
            for rel in [
                "D3D12/D3D12Core.dll",
                "D3D12Core.dll",
                "cool_fox/D3D12/D3D12Core.dll",
                "deps/D3D12Core.dll",
                ".d3d12/D3D12Core.dll",
            ] {
                let p = at.join(rel);
                if p.is_file() {
                    return Some(p);
                }
            }
        }
    }
    None
}
// --- end victory-agility-patch (auto-copy) ---------------------------------

