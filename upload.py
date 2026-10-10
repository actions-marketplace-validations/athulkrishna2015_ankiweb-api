#!/usr/bin/env python3
"""Terminal wrapper around the forked upstream uploader (no reinvented wheel).

Upload engine: node dist/index.js from danny900714/upload-anki-addon
(upstream fork remote). This script only maps CLI args -> INPUT_* env vars
(GitHub Actions convention) and execs node. Metadata-only updates:
pass `--addon-file -` for a branch to skip its file (upstream convention).

Download/info engine: terminal_ankiweb.py (new functionality upstream lacks).

Examples:
  export ANKIWEB_USERNAME='you@example.com' ANKIWEB_PASSWORD='...'
  # update file + description for test addon 805854302:
  ./upload.py --addon-id 805854302 --title "my title" \\
      --description-file DESCRIPTION.md \\
      --branches "2.1.1-25.09.4+" --addon-files ./my.ankiaddon
  # metadata-only (description/tags/title, no file):
  ./upload.py --addon-id 805854302 --title "my title" \\
      --description "new text" --branches "2.1.1-25.09.4+" --addon-files -
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def validate_branch(branch: str) -> None:
    """Catch bad notation before spending a network round-trip.

    Mirrors upstream parseBranchNotation rules: exactly MIN-MAX, each side a
    2.1.x patch or major[.minor[.patch]], trailing '+' on max = open-ended.
    """
    parts = branch.strip().split("-")
    if len(parts) != 2:
        raise ValueError(
            f"branch must be MIN-MAX (e.g. '2.1.1-25.09.4+'), got {branch!r}"
        )
    for ver in parts:
        v = ver.strip()
        if v.endswith("+"):
            v = v[:-1]
        if v.startswith("2.1."):
            if not v[4:].isdigit():
                raise ValueError(f"invalid 2.1.x version in branch {branch!r}")
        else:
            segs = v.split(".")
            if len(segs) > 3 or not all(s.isdigit() and int(s) < 100 for s in segs):
                raise ValueError(f"invalid version in branch {branch!r}")


def build_env(args) -> dict:
    load_dotenv(Path(args.env_file).expanduser() if args.env_file else HERE / ".env")
    env = dict(os.environ)
    def inp(name: str, value: str):
        # @actions/core only replaces spaces with underscores, so hyphenated
        # inputs (addon-files, description-file) are read as INPUT_ADDON-FILES.
        # GitHub Actions uses the same hyphenated form. Set both for safety.
        base = name.upper()
        env[f"INPUT_{base}"] = value
        env[f"INPUT_{base.replace('-', '_')}"] = value
    username = args.username or os.environ.get("ANKIWEB_USERNAME", "")
    password = args.password or os.environ.get("ANKIWEB_PASSWORD", "")
    missing = [n for n, v in (("ANKIWEB_USERNAME", username), ("ANKIWEB_PASSWORD", password)) if not v]
    if missing:
        sys.exit(
            f"error: missing {' and '.join(missing)}\n"
            f"       set them in {HERE / '.env'} (copy .env.example), export them, "
            f"or pass --username/--password"
        )
    inp("username", username)
    inp("password", password)
    inp("addon-id", str(args.addon_id or ""))
    inp("title", args.title)
    inp("tags", args.tags or "")
    inp("support-page", args.support_page or "")
    inp("branches", "\n".join(args.branches))
    inp("addon-files", "\n".join(args.addon_files))

    if args.description and args.description_file:
        print("warning: both --description and --description-file given; --description wins (upstream rule)", file=sys.stderr)
    if args.description:
        inp("description", args.description)
        inp("description-file", "")
    elif args.description_file:
        p = Path(args.description_file)
        if not p.is_file():
            sys.exit(f"error: description file not found: {p}")
        inp("description", "")
        inp("description-file", str(p))
    else:
        sys.exit("error: one of --description / --description-file is required")
    out = os.environ.get("GITHUB_OUTPUT", "")
    if out:
        env["GITHUB_OUTPUT"] = out
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload addon via forked upstream action")
    ap.add_argument("--addon-id", default="", help="numeric AnkiWeb id; omit to create new")
    ap.add_argument("--title", required=True, help="<80 chars")
    ap.add_argument("--tags", default="")
    ap.add_argument("--support-page", default="")
    ap.add_argument("--branches", nargs="+", required=True,
                    help='e.g. "2.1.1-2.1.66" "23.10-25.09.4+" (one per branch)')
    ap.add_argument("--addon-files", nargs="+", required=True,
                    help=".ankiaddon paths in branch order; use - to skip a branch file")
    ap.add_argument("--description", default="")
    ap.add_argument("--description-file", default="")
    ap.add_argument("--username", default="", help="default: $ANKIWEB_USERNAME")
    ap.add_argument("--password", default="", help="default: $ANKIWEB_PASSWORD")
    ap.add_argument("--env-file", default="", help="default: ./.env next to this script")
    ap.add_argument("--node", default="node")
    ap.add_argument("--dry-run", action="store_true", help="print INPUT_* mapping, don't run node")
    args = ap.parse_args()

    if len(args.branches) != len(args.addon_files):
        sys.exit("error: --branches and --addon-files must have the same length")
    for b in args.branches:
        try:
            validate_branch(b)
        except ValueError as e:
            sys.exit(f"error: {e}")
    for f in args.addon_files:
        if f != "-" and not Path(f).is_file():
            sys.exit(f"error: addon file not found: {f}")
    if len(args.title) >= 80:
        sys.exit("error: --title must be fewer than 80 characters")
    if args.support_page and not args.support_page.startswith("http"):
        sys.exit("error: --support-page must start with http")

    env = build_env(args)
    if args.dry_run:
        for k in sorted(k for k in env if k.startswith("INPUT_")):
            v = env[k]
            masked = any(s in k for s in ("PASSWORD", "USERNAME"))
            print(f"{k}={'(secret)' if masked else v[:200]}")
        print(f"engine: {HERE/'dist/index.js'}")
        return 0

    entry = HERE / "dist" / "index.js"
    if not entry.is_file():
        sys.exit(f"error: upstream engine missing: {entry} (did the fork merge complete?)")
    r = subprocess.run([args.node, str(entry)], env=env)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
