#!/usr/bin/env python3
"""Terminal CLI for AnkiWeb: info, download, mine.

  ./ankicli.py info 805854302
  ./ankicli.py download 805854302 -o /tmp/test.ankiaddon
  ./ankicli.py mine                 # your shared decks + add-ons (needs login)

Uploads go through ./upload.py (thin wrapper over the forked upstream action).
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

from ankiweb_auth import AuthError, load_dotenv, login
from terminal_ankiweb import (
    AnkiWebError,
    NotFoundError,
    download_addon,
    fetch_item_info,
    fetch_list_mine,
)

HERE = Path(__file__).resolve().parent


def cmd_info(args) -> int:
    try:
        info = fetch_item_info(args.addon_id)
    except NotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except AnkiWebError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"id:           {info['shared_id']}")
    print(f"title:        {info['title']}")
    if info.get("tags"):
        print(f"tags:         {info['tags'].strip()}")
    if info.get("support_url"):
        print(f"support:      {info['support_url']}")
    print(f"size:         {info['size']}")
    if info["last_updated"]:
        dt = datetime.datetime.fromtimestamp(info["last_updated"], datetime.timezone.utc)
        print(f"last_updated: {info['last_updated']} ({dt.isoformat()})")
    else:
        print("last_updated: 0")
    if info["versions"]:
        print(f"versions:     {', '.join(info['versions'])}")
    print("description:")
    print(info["description"] or "(empty)")
    if args.verbose:
        print(f"timestamps_seen: {info['timestamps_seen']}")
    return 0


def cmd_download(args) -> int:
    try:
        meta = download_addon(args.addon_id, dest=args.output, point_version=args.point_version)
    except AnkiWebError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"saved:    {meta['path']}")
    print(f"filename: {meta['filename']}")
    print(f"size:     {meta['size']}")
    print(f"t={meta['t']} minpt={meta['minpt']} maxpt={meta['maxpt']} bidx={meta['bidx']}")
    print(f"via:      {meta['final_url']}")
    return 0


def load_creds(env_file: str = "") -> tuple[str, str]:
    env_path = Path(env_file).expanduser() if env_file else HERE / ".env"
    load_dotenv(env_path)
    u = os.environ.get("ANKIWEB_USERNAME", "")
    p = os.environ.get("ANKIWEB_PASSWORD", "")
    missing = [n for n, v in (("ANKIWEB_USERNAME", u), ("ANKIWEB_PASSWORD", p)) if not v]
    if missing:
        raise AuthError(
            f"missing {' and '.join(missing)} — set them in {env_path} or the environment"
        )
    return u, p


def cmd_mine(args) -> int:
    try:
        user, password = load_creds(args.env_file)
        cookie = login(user, password)
        data = fetch_list_mine(cookie)
    except (AuthError, AnkiWebError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    items = data["items"]
    if not items:
        print("no shared items")
        return 0

    header = f"{'ID':>12}  {'UPD':<10}  {'DL':>6}  {'+':>3} {'-':>3}  TITLE"
    print(f"{len(items)} shared item(s), {data.get('review_count', 0)} review(s):\n")
    print(header)
    print("-" * len(header))
    for it in items:
        mtime = (
            datetime.datetime.fromtimestamp(it["mtime"], datetime.timezone.utc).strftime("%Y-%m-%d")
            if it["mtime"] else "n/a"
        )
        print(
            f"{it['id']:>12}  {mtime:<10}  {it['downloads']:>6}  "
            f"{it['thumbs_up']:>3} {it['thumbs_down']:>3}  {it['title']}"
        )
    if args.json:
        import json as _json

        print("\n" + _json.dumps(items, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AnkiWeb terminal: info + download (no auth)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="fetch public title/description/size via svc/shared/item-info")
    p.add_argument("addon_id", type=int)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("download", help="download .ankiaddon via /shared/download/<id>")
    p.add_argument("addon_id", type=int)
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--point-version", type=int, default=250902,
                   help="Anki int_version, e.g. 250902 for 25.09.02 (default: 250902)")
    p.set_defaults(fn=cmd_download)

    p = sub.add_parser("mine", help="list items shared by your account (needs login)")
    p.add_argument("--env-file", default="", help="default: ./.env")
    p.add_argument("--json", action="store_true", help="also print raw JSON")
    p.set_defaults(fn=cmd_mine)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
