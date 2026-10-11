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
import time
from urllib.parse import urlparse, parse_qs

import requests

BASE = "https://ankiweb.net"
SHARED = f"{BASE}/shared/"
ITEM_INFO_URL = f"{BASE}/svc/shared/item-info"
LIST_MINE_URL = f"{BASE}/svc/shared/list-mine"


class AnkiWebError(RuntimeError):
    pass


class NotFoundError(AnkiWebError):
    """The id does not exist, or its item is not publicly visible."""


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


def _walk(buf: bytes, depth: int = 0, max_depth: int = 6):
    """Yield (depth, field_no, wire, value), recursing into nested messages.

    Always attempts recursion on wire-type-2 payloads: a container message can
    itself be valid UTF-8 (e.g. ItemInfo wrapping a title), so "looks like text"
    is not a safe test for "is a message". Callers pick fields by exact
    (depth, field_no), so over-walking is harmless.
    """
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
            if depth < max_depth and ln >= 2:
                # Yield incrementally: a payload can parse as a message for a
                # few fields and then hit an invalid wire type. Keep what we
                # already decoded instead of discarding the whole subtree.
                it = _walk(v, depth + 1, max_depth)
                while True:
                    try:
                        yield next(it)
                    except StopIteration:
                        break
                    except Exception:
                        break  # not a nested message past this point
        else:
            raise ValueError(f"unsupported wire type {wire}")


def _is_printable_text(b: bytes) -> bool:
    # No length cap: add-on descriptions are legitimately 20KB+ READMEs, and a
    # 5000-byte cutoff silently dropped them (the description then read back as
    # empty and looked like AnkiWeb had wiped it). UTF-8 decodability plus the
    # printable ratio are what actually distinguish text from binary payloads.
    if not b:
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


_last_cache_bust = 0


def _next_cache_bust() -> str:
    """Strictly increasing epoch-ms value for the `cb` query parameter.

    Mirrors AnkiWeb's `cacheBust` helper (Date.now()), but monotonic: two reads
    within the same millisecond would otherwise produce the same URL and the
    second could be served the first one's cached copy.
    """
    global _last_cache_bust
    now = int(time.time() * 1000)
    _last_cache_bust = max(now, _last_cache_bust + 1)
    return str(_last_cache_bust)


def fetch_item_info_raw(
    shared_id: int, timeout: int = 30, cache_bust: str | None = None
) -> bytes:
    """GET svc/shared/item-info?sharedId=<id>. No auth. Returns raw protobuf bytes.

    AnkiWeb serves this with `max-age=600`, so a stable URL returns up to 10
    minutes of stale data -- after an upload, reads looked like the server had
    silently wiped a long description. Append the same `cb` cache-buster the
    web frontend uses to force a fresh read. Pass `cache_bust` to reuse the
    exact value, so callers can echo the URL they actually read.
    """
    if cache_bust is None:
        cache_bust = _next_cache_bust()
    r = requests.get(
        ITEM_INFO_URL,
        params={
            "sharedId": shared_id,  # camelCase required; shared_id -> 400
            "cb": cache_bust,
        },
        headers={"Accept": "*/*", "Cache-Control": "no-cache"},
        timeout=timeout,
    )
    if r.status_code != 400 and r.status_code != 404 and r.status_code != 200:
        raise AnkiWebError(f"item-info HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code in (400, 404):
        raise NotFoundError(f"item-info HTTP {r.status_code} for id {shared_id}: {r.text[:200]}")
    # A missing/private id still returns 200, but with an empty response message
    # (no ItemInfo payload). Anything under ~4 bytes carries no fields.
    if len(r.content) <= 3:
        raise NotFoundError(
            f"no shared item {shared_id} (empty response; wrong id, or not public)"
        )
    return r.content


def parse_item_info(buf: bytes) -> dict:
    """Extract title/description/tags/size/versions from an ItemInfoResponse.

    Field numbers verified against fixtures/ on 2026-10:
      ItemInfo @ depth1: title=f5, tags=f6, size=f7, last_updated=f8,
                        description=f9, support_url=f12, items_shared_by_user=f13
      AddonVersion @ depth3: description=f1 ("2.1.45+", "2.1.0-2.1.44")

    Every field is addressed by exact (depth, field_no). Heuristic matching
    by content/length is deliberately avoided: reviews live at f1/f4 and are
    often far longer than the title, and review ids are plausible varints.
    """
    strings: list[tuple[int, int, bytes]] = []  # (depth, field, raw)
    varints_at: list[tuple[int, int, int, int]] = []  # (depth, field, wire, varint)
    for d, f, w, v in _walk(buf):
        if w == 2 and isinstance(v, bytes) and _is_printable_text(v):
            strings.append((d, f, v))
        elif w == 0 and isinstance(v, int):
            varints_at.append((d, f, w, v))

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
    # Scalars by exact position (magic-number guessing picked up review ids
    # as "size" on busy add-ons, e.g. AnkiConnect reporting 67 MB):
    #   ItemInfo @ depth1: size=f7, last_updated=f8, items_shared_by_user=f13
    def vat(depth: int, field: int) -> list[int]:
        return [v for d, f, w, v in varints_at if d == depth and f == field]

    size = vat(1, 7)[0] if vat(1, 7) else 0
    last_updated = vat(1, 8)[0] if vat(1, 8) else 0
    shared_by = vat(1, 13)[0] if vat(1, 13) else 0
    times = sorted({v for _d, _f, _w, v in varints_at if 1577836800 <= v <= 2051222400})
    return {
        "title": title,
        "description": description,
        "tags": tag_str,
        "support_url": support_url,
        "versions": versions,
        "last_updated": last_updated,
        "size": size,
        "items_shared_by_user": shared_by,
        "timestamps_seen": times,
    }


def parse_list_mine(buf: bytes) -> dict:
    """Decode ListMineResponse (schema from AnkiWeb's frontend chunk):

      ListMineResponse{ items=1[]OwnItem, reviews=2[], expired_decks=3[] }
      OwnItem{ id=1, title=2, thumbs_up=3, thumbs_down=4, mtime=5,
               downloads=6, max_supported_version=7(opt int32) }
    """
    items: list[dict] = []
    reviews = 0
    for d, f, w, v in _walk(buf):
        if d != 0:
            continue
        if f == 2 and w == 2:
            reviews += 1
            continue
        if f != 1 or w != 2:
            continue
        item: dict = {"id": 0, "title": "", "thumbs_up": 0, "thumbs_down": 0,
                      "mtime": 0, "downloads": 0, "max_supported_version": None}
        for _d, id_, fw, wv in _walk(v):
            if _d != 0:
                continue
            if id_ == 1 and fw == 0:
                item["id"] = int(wv)
            elif id_ == 2 and fw == 2 and isinstance(wv, bytes):
                item["title"] = wv.decode("utf-8", "replace")
            elif id_ == 3 and fw == 0:
                item["thumbs_up"] = int(wv)
            elif id_ == 4 and fw == 0:
                item["thumbs_down"] = int(wv)
            elif id_ == 5 and fw == 0:
                item["mtime"] = int(wv)
            elif id_ == 6 and fw == 0:
                item["downloads"] = int(wv)
            elif id_ == 7 and fw == 0:
                # proto int32: wire gives unsigned; reinterpret signed
                item["max_supported_version"] = (
                    int(wv) - (1 << 32) if int(wv) & 0x80000000 else int(wv)
                )
        items.append(item)
    return {"items": items, "review_count": reviews}


def fetch_list_mine(cookie: str, timeout: int = 30) -> dict:
    """POST svc/shared/list-mine with your session cookie (empty body)."""
    r = requests.post(
        LIST_MINE_URL,
        data=b"",
        headers={
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
            "Cookie": f"has_auth=1; ankiweb={cookie}",
            "Referer": f"{BASE}/shared/mine",
        },
        timeout=timeout,
    )
    if r.status_code in (401, 403):
        raise AnkiWebError(
            f"list-mine HTTP {r.status_code}: session not valid; re-check credentials"
        )
    if r.status_code != 200:
        raise AnkiWebError(f"list-mine HTTP {r.status_code}: {r.text[:300]}")
    return parse_list_mine(r.content)


def fetch_item_info(shared_id: int, timeout: int = 30) -> dict:
    # One cache-buster for the read, echoed back as info["cache_bust"] so
    # callers can print the exact verification URL that was just fetched.
    cache_bust = _next_cache_bust()
    raw = fetch_item_info_raw(shared_id, timeout, cache_bust=cache_bust)
    info = parse_item_info(raw)
    # Defensive: a real ItemInfo always carries a title or a description.
    if not info["title"] and not info["description"]:
        raise NotFoundError(
            f"no usable metadata for id {shared_id} "
            f"(wrong id, deleted, or not public)"
        )
    info["shared_id"] = shared_id
    info["cache_bust"] = cache_bust
    return info
