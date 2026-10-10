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


def build_env(args) -> dict:
    env = dict(os.environ)
    def inp(name: str, value: str):
        env[f"INPUT_{name.upper().replace('-', '_')}"] = value
    username = args.username or os.environ.get("ANKIWEB_USERNAME", "")
    password = args.password or os.environ.get("ANKIWEB_PASSWORD", "")
    if not username or not password:
        sys.exit("error: username/password required via flags or ANKIWEB_USERNAME/ANKIWEB_PASSWORD env")
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
    ap.add_argument("--username", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--node", default="node")
    ap.add_argument("--dry-run", action="store_true", help="print INPUT_* mapping, don't run node")
    args = ap.parse_args()

    if len(args.branches) != len(args.addon_files):
        sys.exit("error: --branches and --addon-files must have the same length")
    for f in args.addon_files:
        if f != "-" and not Path(f).is_file():
            sys.exit(f"error: addon file not found: {f}")

    env = build_env(args)
    if args.dry_run:
        for k in sorted(k for k in env if k.startswith("INPUT_")):
            v = env[k]
            print(f"{k}={'(secret)' if 'PASSWORD' in k else v[:200]}")
        print(f"engine: {HERE/'dist/index.js'}")
        return 0

    entry = HERE / "dist" / "index.js"
    if not entry.is_file():
        sys.exit(f"error: upstream engine missing: {entry} (did the fork merge complete?)")
    r = subprocess.run([args.node, str(entry)], env=env)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
