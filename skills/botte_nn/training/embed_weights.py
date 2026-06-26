#!/usr/bin/env python3
"""Convert trained JSON weight files into Rust source modules (include_bytes!).

Generates:
    src/embedded/effort_classifier.rs
    src/embedded/binary_router.rs
    src/embedded/anomaly_detector.rs
    src/embedded/mod.rs

Each file embeds the JSON weights as a static byte slice,
loaded at compile time via include_bytes!().

Usage:
    python skills/botte_nn/training/embed_weights.py
"""

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]  # embed_weights.py → training/ → botte_nn/
MODELS_DIR = REPO_ROOT / "models"
EMBEDDED_DIR = REPO_ROOT / "src" / "embedded"


def _to_rust_byte_array(data: bytes) -> str:
    """Convert bytes to a Rust byte array literal.

    Output format:
        pub const WEIGHTS: &[u8] = &[ 0x7b, 0x0a, 0x20, ... ];
    """
    hex_bytes = ", ".join(f"0x{b:02x}" for b in data)
    return f"pub const WEIGHTS: &[u8] = &[\n    {hex_bytes},\n];"


def _embedded_name(model_name: str) -> str:
    """Convert model filename to valid Rust identifier."""
    return model_name.replace("-", "_").replace(".json", "")


def generate_embedded_module(model_path: Path) -> str:
    """Generate a Rust module file from a JSON weight file."""
    name = _embedded_name(model_path.name)
    data = model_path.read_bytes()

    rust = f"""// Auto-generated from {model_path.name}
// DO NOT EDIT — regenerate with embed_weights.py

{_to_rust_byte_array(data)}

/// Load the embedded weights as a JSON string.
pub fn load() -> Result<String, String> {{
    String::from_utf8(WEIGHTS.to_vec())
        .map_err(|e| format!("UTF-8 error: {{e}}"))
}}

/// Number of input features expected by this model.
pub const INPUT_SIZE: usize = {json.loads(data)['layers'][0]};

/// Number of output classes.
pub const OUTPUT_SIZE: usize = {json.loads(data)['layers'][-1]};
"""
    return rust


def generate_mod_rs(modules: list[str]) -> str:
    """Generate the mod.rs that re-exports all embedded models."""
    lines = ["// Auto-generated — embedded model weights", "// DO NOT EDIT", ""]
    for m in modules:
        lines.append(f"pub mod {m};")
    lines.append("")
    lines.append("/// All available embedded models with their metadata.")
    lines.append("pub const EMBEDDED_MODELS: &[(&str, fn() -> Result<String, String>, usize, usize)] = &[")
    for m in modules:
        lines.append(f"    (\"{m}\", {m}::load, {m}::INPUT_SIZE, {m}::OUTPUT_SIZE),")
    lines.append("];")
    return "\n".join(lines)


def main():
    print("🔨 Generating embedded Rust modules...")

    EMBEDDED_DIR.mkdir(parents=True, exist_ok=True)

    # Also put a copy of the build script in the embedded dir
    build_script_dest = EMBEDDED_DIR / "build.rs"
    if not build_script_dest.exists():
        # We'll create build.rs separately in Cargo.toml
        pass

    json_files = sorted(MODELS_DIR.glob("*.json"))
    if not json_files:
        print("❌ No JSON weight files found in models/")
        return 1

    modules = []
    for jf in json_files:
        name = _embedded_name(jf.name)
        rust = generate_embedded_module(jf)
        out_path = EMBEDDED_DIR / f"{name}.rs"
        out_path.write_text(rust)
        modules.append(name)
        size = jf.stat().st_size
        print(f"  ✅ {jf.name} ({size} bytes) → src/embedded/{name}.rs")

    mod_rs = generate_mod_rs(modules)
    (EMBEDDED_DIR / "mod.rs").write_text(mod_rs)
    print(f"  ✅ mod.rs generated with {len(modules)} embedded models")
    print(f"\n📍 Output: {EMBEDDED_DIR}/")
    print("   Now add 'mod embedded;' to lib.rs and rebuild with 'cargo build --release'")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
