#!/usr/bin/env python3
"""Terminal CLI for public AnkiWeb endpoints: info + download.

  ./ankicli.py info 805854302
  ./ankicli.py download 805854302 -o /tmp/test.ankiaddon

Uploads go through ./upload.py (thin wrapper over the forked upstream action).
"""

from __future__ import annotations

import argparse
import datetime
import sys

from terminal_ankiweb import download_addon, fetch_item_info, AnkiWebError


def cmd_info(args) -> int:
    try:
        info = fetch_item_info(args.addon_id)
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

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
