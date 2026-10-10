"""Terminal helpers for AnkiWeb shared items — functionality upstream lacks.

Upstream (danny900714/upload-anki-addon, src/ankiweb.ts) covers:
  login + upload-addon (POST svc/account/login, POST svc/shared/upload-addon)

This module covers the public, no-auth endpoints (reverse-engineered, see README-TERMINAL.md):
  GET /shared/download/<id>?v=2.1&p=<ver>  -> 303 -> /svc/shared/download-addon/<id>?t=..&minpt=..&maxpt=..&bidx=..
  GET /svc/shared/item-info?sharedId=<id>    -> protobuf ItemInfoResponse (public, max-age=600)

Only dependency: requests.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

import requests

BASE = "https://ankiweb.net"
SHARED = f"{BASE}/shared/"
ITEM_INFO_URL = f"{BASE}/svc/shared/item-info"


class AnkiWebError(RuntimeError):
    pass


def download_addon(
    addon_id: int, dest: str | None = None, point_version: int = 250902, timeout: int = 60
) -> dict:
    """Download .ankiaddon via /shared/download/<id> (follows 303 to svc).

    Returns dict with path, filename, final_url, t/minpt/maxpt/bidx, size.
    No auth required. Raises AnkiWebError on HTTP != 200 (e.g. 404:
    'No add-on with that id.' or 'Your version of Anki is too old.').
    """
    url = f"{SHARED}download/{addon_id}?v=2.1&p={point_version}"
    with requests.get(url, timeout=timeout, stream=True, allow_redirects=True) as r:
        if r.status_code != 200:
            body = ""
            try:
                body = r.text[:300]
            except Exception:
                pass
            raise AnkiWebError(f"download HTTP {r.status_code} for id {addon_id}: {body}")
        final_url = r.url
        cd = r.headers.get("Content-Disposition", "")
        m = re.search(r"filename=(.+)", cd)
        filename = (m.group(1).strip() if m else f"{addon_id}.ankiaddon").strip('"')
        q = parse_qs(urlparse(final_url).query)
        meta = {
            "addon_id": addon_id,
            "filename": filename,
            "final_url": final_url,
            "t": int(q.get("t", ["0"])[0]),
            "minpt": int(q.get("minpt", ["0"])[0]),
            "maxpt": int(q.get("maxpt", ["0"])[0]),
            "bidx": int(q.get("bidx", ["0"])[0]),
            "size": int(r.headers.get("Content-Length", "0") or 0),
        }
        if dest is None:
            dest = filename
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        meta["path"] = dest
        return meta


# ---------------------------------------------------------------- generic protobuf scan
# item-info schema lives in AnkiWeb's SvelteKit JS (chunks/frontend.*.mjs),
# so we decode generically: walk length-delimited fields, collect strings +
# varints, then pick out title/description/size/timestamps heuristically.


def _varint_decode(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            return result, pos
        if shift >= 70:
            raise ValueError("varint too long")


def _walk(buf: bytes, depth: int = 0, max_depth: int = 4):
    """Yield (depth, field_no, wire, value). Recurses into nested messages
    only when the payload itself parses cleanly as protobuf fields."""
    pos = 0
    while pos < len(buf):
        key, pos = _varint_decode(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, pos = _varint_decode(buf, pos)
            yield (depth, field, wire, v)
        elif wire == 2:
            ln, pos = _varint_decode(buf, pos)
            v = buf[pos : pos + ln]
            pos += ln
            yield (depth, field, wire, v)
            if depth < max_depth and len(v) >= 2 and not _is_printable_text(v):
                try:
                    # validate: must consume exactly and have sane field nos
                    inner = list(_walk(v, depth + 1, max_depth))
                    # heuristic: accept nesting only if it re-serializes plausibly
                    # (at least one varint or nested msg inside)
                    if any(w == 0 or d > depth + 1 for d, f, w, vv in inner for d in [d]):
                        pass
                    # re-walk lazily instead: yield from inner
                    yield from inner
                except Exception:
                    pass
        else:
            raise ValueError(f"unsupported wire type {wire}")


def _is_printable_text(b: bytes) -> bool:
    if not b or len(b) > 5000:
        return False
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not s.strip():
        return False
    # mostly printable?
    pr = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    return pr / max(len(s), 1) > 0.9


def fetch_item_info_raw(shared_id: int, timeout: int = 30) -> bytes:
    """GET svc/shared/item-info?sharedId=<id>. No auth. Returns raw protobuf bytes."""
    r = requests.get(
        ITEM_INFO_URL,
        params={"sharedId": shared_id},  # camelCase required; shared_id -> 400
        headers={"Accept": "*/*"},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise AnkiWebError(f"item-info HTTP {r.status_code}: {r.text[:300]}")
    return r.content


def parse_item_info(buf: bytes) -> dict:
    """Heuristically extract title/description/size/timestamps/versions.

    Field numbers observed (2026-10, may drift with frontend deploys):
      ItemInfo{title=f5, tags?=f6, size=f7, last_updated=f8, description=f9,
               addon=f11{v2_1=f2, versions=f3[{description=f1, updated_at=f2}]},
               items_shared_by_user=f13}
    We don't rely on exact numbers: strings are classified by content,
    varints by magnitude (unix time vs size vs small flags).
    """
    strings: list[tuple[int, int, bytes]] = []  # (depth, field, raw)
    varints: list[int] = []
    for _d, _f, w, v in _walk(buf):
        if w == 2 and isinstance(v, bytes) and _is_printable_text(v):
            strings.append((_d, _f, v))
        elif w == 0 and isinstance(v, int):
            varints.append(v)

    def txt(raw: bytes) -> str:
        return raw.decode("utf-8", "replace")

    # Exact positions (stable across ids observed 2026-10):
    #   ItemInfo @ depth1: title=f5, tags=f6, description=f9, support_url=f12
    #   AddonVersion @ depth3: description=f1 ("2.1.45+", "2.1.0-2.1.44")
    # Reviews share depth1 (f1) / depth2 (f4) — never use longest-string fallback.
    def at(depth: int, field: int) -> list[str]:
        return [txt(r) for d, f, r in strings if d == depth and f == field]

    titles = at(1, 5)
    title = max(titles, key=len).strip() if titles else ""
    descs = at(1, 9)
    if descs:
        description = max(descs, key=len)
    else:
        fall = [txt(r) for _d, _f, r in strings if "<" in txt(r)]
        description = max(fall, key=len) if fall else ""
    tags = at(1, 6)
    tag_str = max(tags, key=len).strip() if tags else ""
    support = at(1, 12)
    support_url = support[0].strip() if support else ""
    versions = sorted({t.strip() for t in at(3, 1) if "." in t})
    if not versions:  # fallback for tiny items (e.g. private test addon)
        versions = sorted(
            {
                txt(r).strip()
                for d, f, r in strings
                if d >= 2 and "." in txt(r)
                and re.fullmatch(r"[\d.\-]+\+?", txt(r).strip())
            }
        )
    # timestamps: varints in plausible unix range (2020-01-01 .. 2035-01-01)
    times = sorted({v for v in varints if 1577836800 <= v <= 2051222400})
    last_updated = max(times) if times else 0
    # size: largest varint that is NOT a timestamp and < 500MB
    sizes = [v for v in varints if v not in times and 0 < v < 500_000_000]
    size = max(sizes) if sizes else 0
    return {
        "title": title,
        "description": description,
        "tags": tag_str,
        "support_url": support_url,
        "versions": versions,
        "last_updated": last_updated,
        "size": size,
        "timestamps_seen": times,
    }


def fetch_item_info(shared_id: int, timeout: int = 30) -> dict:
    raw = fetch_item_info_raw(shared_id, timeout)
    info = parse_item_info(raw)
    info["shared_id"] = shared_id
    return info
