#!/usr/bin/env python3
"""Build a tiny synthetic .ankiaddon for upload/download tests.

Never test with a real add-on: an upload REPLACES the file on the target
add-on id, and the old version is not recoverable from AnkiWeb.

Usage:
    python3 make_test_addon.py                 # -> fixtures/test.ankiaddon
    python3 make_test_addon.py -o out.ankiaddon
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MARKER = "ANKIWEB-CLI-TEST-FIXTURE"

# Minimal add-on that loads cleanly in Anki and is obviously not a real add-on.
INIT_PY = '''"""Synthetic fixture add-on for AnkiWeb CLI tests. Not a real add-on."""
from aqt import mw


def _register():
    mw.form.addon_name = addon_name  # harmless attribute; confirms import ran


addon_name = "ankiweb-cli-test-fixture"
'''

MANIFEST = {
    "name": "AnkiWeb CLI Test Fixture",
    "package": "ankiweb_cli_test_fixture",
    "version": "1.0.0",
    "human_version": "1.0.0",
}


def build(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        # Root-level entries only, no wrapping folder, no __pycache__.
        z.writestr("__init__.py", INIT_PY)
        z.writestr("manifest.json", json.dumps(MANIFEST, indent=2) + "\n")
        z.writestr("README.md", f"{MARKER}\n\nSynthetic add-on for upload tests.\n")
        z.writestr("VERSION", "1.0.0\n")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=str(FIXTURE_DIR / "test.ankiaddon"))
    args = ap.parse_args()
    dest = build(Path(args.output))
    print(f"built {dest} ({dest.stat().st_size} bytes)")
    with zipfile.ZipFile(dest) as z:
        for n in z.namelist():
            print(f"  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())