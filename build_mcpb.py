#!/usr/bin/env python
"""Build the creative-suite-mcp.mcpb bundle.

Usage:
    python build_mcpb.py

Output:
    dist/creative-suite-mcp.mcpb  (zip archive ready for Claude Desktop)
"""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
MCPB_DIR = ROOT / "mcpb"
DIST = ROOT / "dist"
OUTPUT = DIST / "creative-suite-mcp.mcpb"

def build():
    # Ensure fresh server copy
    shutil.copy2(ROOT / "mcp_server.py", MCPB_DIR / "server" / "mcp_server.py")

    # Copy icon if available
    logo = ROOT / "assets" / "logo.png"
    if logo.exists():
        shutil.copy2(logo, MCPB_DIR / "icon.png")

    # Validate manifest
    manifest_path = MCPB_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    required = ["manifest_version", "name", "version", "description", "server"]
    for key in required:
        assert key in manifest, f"Missing required field: {key}"
    print(f"  Manifest OK: {manifest['name']} v{manifest['version']}")

    # Create .mcpb (zip)
    DIST.mkdir(exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in MCPB_DIR.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(MCPB_DIR)
                zf.write(file, arcname)
                print(f"  + {arcname}")

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"\n  Built: {OUTPUT.name} ({size_kb:.1f} KB)")
    print(f"  Path:  {OUTPUT}")


if __name__ == "__main__":
    print()
    print("  Building creative-suite-mcp.mcpb")
    print("  " + "=" * 40)
    print()
    build()
    print()
