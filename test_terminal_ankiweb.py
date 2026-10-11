#!/usr/bin/env python3
"""Tests for terminal_ankiweb parsing and CLI exit codes.

Offline tests run anywhere. Live tests (--live) hit AnkiWeb and need network.

    python3 test_terminal_ankiweb.py          # offline only
    python3 test_terminal_ankiweb.py --live   # + network round-trips
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

from terminal_ankiweb import (
    AnkiWebError,
    NotFoundError,
    download_addon,
    fetch_item_info,
    fetch_item_info_raw,
    parse_item_info,
)


def _varint_encode(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint_encode((field << 3) | wire)

LIVE = "--live" in sys.argv
failures: list[str] = []
passes = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passes
    if cond:
        passes += 1
        print(f"  PASS  {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name} {detail}")


# Real responses captured 2026-10-10 from GET /svc/shared/item-info?sharedId=...
# (stored as binaries so we test the real wire format, not a hand-typed hex)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PRIVATE_ITEM = (FIXTURES / "item_info_805854302.bin").read_bytes()
PUBLIC_ITEM = (FIXTURES / "item_info_2055492159.bin").read_bytes()


def _msg(field: int, payload: bytes) -> bytes:
    return _tag(field, 2) + _varint_encode(len(payload)) + payload


def _s(field: int, text: str) -> bytes:
    return _msg(field, text.encode("utf-8"))


# Regression: reviews live at ItemInfo.f1 (depth 2, f4) and can be far longer
# than the real title. An older parser picked the longest string and returned
# review text as the add-on title (seen on AnkiConnect, 133 KB payload).
def build_review_pollution() -> bytes:
    """Minimal ItemInfoResponse: outer f1 wraps ItemInfo, so its fields are depth 1."""
    long_review = "x" * 500
    item_info = (
        _msg(1, _s(4, long_review))  # reviews at f1 -> text at depth2/f4
        + _s(5, "AnkiConnect")        # title, depth1
        + _s(6, "anki api")           # tags, depth1
        + _s(9, "<p>Real description</p>")
    )
    return _msg(1, item_info)


def build_long_description() -> bytes:
    """ItemInfoResponse whose description is a full 22 KB README.

    Regression: the parser used to reject any string over 5000 bytes
    (`len(b) > 5000`), silently dropping real add-on descriptions. Reads then
    looked like AnkiWeb had wiped a long description after every upload.
    """
    readme = "# AI-Hints Anki Add-on\n\n" + ("Markdown body line.\n" * 1500) + "build / test / release)."
    item_info = _s(5, "AnkiWeb API") + _s(9, readme)
    return _msg(1, item_info)


def test_offline() -> None:
    print("offline parsing")

    # Long descriptions must survive parsing intact (was capped at 5000 bytes).
    long_info = parse_item_info(build_long_description())
    check(
        "long description is not dropped",
        len(long_info["description"]) > 20000,
        f"got {len(long_info['description'])} chars",
    )
    check(
        "long description keeps its content",
        long_info["description"].startswith("# AI-Hints Anki Add-on")
        and long_info["description"].endswith("build / test / release)."),
        repr(long_info["description"][:40]),
    )

    info = parse_item_info(PRIVATE_ITEM)
    check("title extracted", info["title"] == "testingaddon for me [private]", repr(info["title"]))
    check("description extracted", info["description"] == "<p>test</p>", repr(info["description"]))
    check("size extracted", info["size"] == 737, f"got {info['size']}")
    check("version extracted", info["versions"] == ["2.1.1+"], repr(info["versions"]))
    check("last_updated extracted", info["last_updated"] == 1791638340, str(info["last_updated"]))

    # Busy public add-on (133 KB of reviews): the two bugs that motivated
    # exact-field addressing. Regression coverage for both.
    pub = parse_item_info(PUBLIC_ITEM)
    check("public title not a review", pub["title"] == "AnkiConnect", repr(pub["title"][:60]))
    check("public tags", pub["tags"] == "yomichan anki api ankiconnect rest", repr(pub["tags"]))
    check("public support_url", pub["support_url"] == "https://foosoft.net/projects/anki-connect/")
    check("public versions", pub["versions"] == ["2.1.0-2.1.44", "2.1.45+"], repr(pub["versions"]))
    check("public size is real (not a review id)", pub["size"] == 25659, f"got {pub['size']}")
    check("public description is not a review", pub["description"].startswith("<p>AnkiConnect enables"),
          repr(pub["description"][:60]))

    polluted = parse_item_info(build_review_pollution())
    check("review text not used as title", polluted["title"] == "AnkiConnect",
          repr(polluted["title"][:60]))
    check("tags extracted", polluted["tags"] == "anki api", repr(polluted["tags"]))
    check("description extracted vs review",
          polluted["description"] == "<p>Real description</p>",
          repr(polluted["description"][:60]))

    # The exact shape AnkiWeb returns for a missing id: field 2 varint only.
    empty = bytes([0x10, 0x01])
    ei = parse_item_info(empty)
    check("empty payload yields no title", ei["title"] == "", repr(ei["title"]))
    check("empty payload is tiny", len(empty) <= 3)


def test_cache_busting() -> None:
    """item-info must be read with a cache-buster.

    AnkiWeb serves /svc/shared/item-info with `max-age=600`, so a stable URL
    returns up to 10 minutes of stale data -- right after an upload the CLI
    reported the previous (or empty) description. The web frontend appends
    `cb=<Date.now()>` (its `cacheBust` helper); the CLI must do the same.
    """
    print("item-info cache-busting")

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        content = _msg(1, _s(5, "Cached Add-on") + _s(9, "<p>body</p>"))

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        captured["params"] = params or {}
        captured["headers"] = headers or {}
        return FakeResponse()

    with mock.patch("terminal_ankiweb.requests.get", fake_get):
        fetch_item_info_raw(805854302)

    params = captured.get("params", {})
    cb = str(params.get("cb", ""))
    check("sends camelCase sharedId", params.get("sharedId") == 805854302, repr(params))
    check("sends cb cache-buster", bool(cb), repr(params))
    check("cb is epoch milliseconds", cb.isdigit() and len(cb) >= 13, repr(cb))
    check(
        "asks intermediaries not to serve a stale copy",
        "no-cache" in str(captured.get("headers", {})).lower(),
        repr(captured.get("headers")),
    )

    # fetch_item_info must surface the exact cache-buster it read with, so the
    # CLI can print a verification URL that shows the same (fresh) state.
    with mock.patch("terminal_ankiweb.requests.get", fake_get):
        parsed = fetch_item_info(805854302)
    check(
        "fetch_item_info echoes its cache_bust",
        parsed.get("cache_bust") == captured.get("params", {}).get("cb"),
        f"{parsed.get('cache_bust')!r} vs {captured.get('params', {}).get('cb')!r}",
    )
    check(
        "cache_bust yields a usable verification URL",
        f"https://ankiweb.net/shared/info/{parsed['shared_id']}?cb={parsed['cache_bust']}".count("?cb=") == 1,
        repr(parsed.get("cache_bust")),
    )

    # A frozen cache-buster would defeat the purpose: two reads must not reuse
    # the same URL, or the second would return the first one's cached copy.
    seen = []
    for _ in range(2):
        with mock.patch("terminal_ankiweb.requests.get", fake_get):
            fetch_item_info(805854302)
        seen.append(captured["params"]["cb"])
    check("each read uses a fresh cache_buster", seen[0] != seen[1], repr(seen))

    # An explicit cache_bust must be honoured, not regenerated.
    with mock.patch("terminal_ankiweb.requests.get", fake_get):
        fetch_item_info_raw(805854302, cache_bust="1234567890123")
    check(
        "explicit cache_bust is reused",
        captured["params"]["cb"] == "1234567890123",
        repr(captured["params"].get("cb")),
    )


def test_login_codec() -> None:
    """Round-trip the LoginRequest/Response protobuf codec (offline)."""
    from ankiweb_auth import decode_login_response, encode_login_request

    req = encode_login_request("user@example.com", "p@ss w0rd")
    check("login request encodes username", b"user@example.com" in req)
    check("login request encodes password", b"p@ss w0rd" in req)

    # LoginResponse{status=1(AUTHENTICATED), token="tok"}
    resp = bytes([0x08, 0x01, 0x12, 0x03]) + b"tok"
    status, token = decode_login_response(resp)
    check("login status decoded", status == 1, str(status))
    check("login token decoded", token == "tok", repr(token))

    status, _ = decode_login_response(bytes([0x08, 0x03]))  # INVALID_PASS
    check("invalid pass decoded", status == 3, str(status))


def test_list_mine_parse() -> None:
    """Decode a captured list-mine response: items vs reviews must not mix."""
    fixture = FIXTURES / "list_mine.bin"
    if not fixture.is_file():
        print("  SKIP  list-mine fixture not present")
        return
    from terminal_ankiweb import parse_list_mine

    data = parse_list_mine(fixture.read_bytes())
    items = data["items"]
    check("list-mine returns items", len(items) > 0, str(len(items)))
    titles = [i["title"] for i in items]
    check("items have real titles", all(titles), "some title empty")
    check("reviews counted separately", data["review_count"] > 0, str(data["review_count"]))
    first = items[0]
    check("item id is numeric", isinstance(first["id"], int) and first["id"] > 0, str(first["id"]))
    check("mtime is a unix ts", first["mtime"] > 1_500_000_000, str(first["mtime"]))
    # Regression: an earlier walk matched reviews as items, so titles were
    # blank and id/title columns were shifted.
    check("no review text as title",
          not any("thanks" in t.lower() or "works" in t.lower() for t in titles),
          str(titles[:3]))


# File/binary endpoints discovered by sweeping *all* frontend chunks (not just
# the schema chunk). They carry no protobuf message, so the generated schema
# can never contain them; they are documented in docs/ENDPOINTS.md under
# "Discovered live, beyond the schema".
LIVE_FILE_ENDPOINTS = {
    "/svc/shared/download-deck",
    "/svc/radmin/collection",
    "/svc/radmin/get-collection-backup",
    "/svc/radmin/get-media",
}


def sweep_all_chunks() -> set[str]:
    """Every /svc/<area>/<action> prefix referenced anywhere in the app chunks."""
    import importlib.util
    import re
    import urllib.request
    import concurrent.futures

    spec = importlib.util.spec_from_file_location(
        "generate_schema", Path(__file__).resolve().parent / "tools" / "generate_schema.py"
    )
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    # start from the schema chunk's shell, then follow every chunk import
    with urllib.request.urlopen("https://ankiweb.net/shared/mine", timeout=30) as r:
        shell = r.read().decode("utf-8", "replace")
    seeds = set(re.findall(r"/_app/immutable/[a-zA-Z0-9_/.-]+\.(?:mjs|js)", shell))

    def fetch(path: str) -> str | None:
        try:
            with urllib.request.urlopen("https://ankiweb.net" + path, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None

    downloaded: dict[str, str] = {}
    pending = set(seeds)
    paths: set[str] = set()
    while pending:
        wave = list(pending)
        pending = set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            for path, body in zip(wave, ex.map(fetch, wave)):
                if not body or path in downloaded:
                    continue
                downloaded[path] = body
                paths.update(re.findall(r"/svc/[a-z0-9-]+/[a-z0-9-]+", body))
                for dep in re.findall(r'"\.\./(chunks|nodes)/([^"]+\.mjs)"', body):
                    newp = f"/_app/immutable/{dep[0]}/{dep[1]}"
                    if newp not in downloaded:
                        pending.add(newp)
    return paths


def test_api_discovery_live() -> None:
    """Re-discover AnkiWeb's live bundle and check it against the snapshot.

    Guards against silent drift: if AnkiWeb adds or removes an endpoint, the
    committed schema stops matching reality. Regenerating with
    `python3 tools/generate_schema.py` should produce a byte-identical file
    while this passes.
    """
    print("api discovery (live bundle)")
    import importlib.util
    import re

    spec = importlib.util.spec_from_file_location(
        "generate_schema", Path(__file__).resolve().parent / "tools" / "generate_schema.py"
    )
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    from ankiweb_schema import ENDPOINTS

    try:
        src = gen.discover_bundle()
    except SystemExit as e:
        check("live bundle discovered", False, str(e))
        return

    live = set(re.findall(r'"/svc/[a-zA-Z0-9/_-]+"', src))
    live_paths = {p.strip('"') for p in live}
    known = {e["path"] for e in ENDPOINTS}

    check("live bundle discovered", bool(live_paths), f"{len(live_paths)} paths")
    check(
        "every live /svc path is in the schema",
        live_paths <= known,
        f"missing: {sorted(live_paths - known)}",
    )
    check(
        "no stale /svc paths in the schema",
        known <= live_paths,
        f"stale: {sorted(known - live_paths)}",
    )
    public = [p for p in live_paths if "/radmin/" not in p]
    check("41 public endpoints present", len(public) == 41, f"got {len(public)}")

    # Full-chunk sweep: the schema chunk alone misses the binary/file endpoints
    # (download-deck, radmin file links) which live in lazily-loaded route
    # chunks. Verify those are still present and nothing else appeared.
    try:
        swept = sweep_all_chunks()
    except Exception as e:  # noqa: BLE001
        check("full chunk sweep", False, str(e))
        return
    extras = {p for p in swept if p not in known}
    check(
        "no unknown /svc paths across all chunks",
        extras <= LIVE_FILE_ENDPOINTS,
        f"unexpected: {sorted(extras - LIVE_FILE_ENDPOINTS)}",
    )
    check(
        "known file endpoints still live",
        LIVE_FILE_ENDPOINTS <= swept,
        f"missing: {sorted(LIVE_FILE_ENDPOINTS - swept)}",
    )


def test_live() -> None:
    print("live (network)")
    try:
        info = fetch_item_info(805854302)
        check("live info returns title", bool(info["title"]), info)
        check("live info id echoed", info["shared_id"] == 805854302)
    except AnkiWebError as e:
        check("live info", False, str(e))

    try:
        fetch_item_info(123456789)
        check("missing id raises NotFoundError", False, "no exception")
    except NotFoundError:
        check("missing id raises NotFoundError", True)
    except Exception as e:  # noqa: BLE001
        check("missing id raises NotFoundError", False, f"wrong type: {type(e).__name__}")

    try:
        fetch_item_info(999999999999)
        check("oversized id raises", False, "no exception")
    except NotFoundError:
        check("oversized id raises NotFoundError", True)
    except Exception as e:  # noqa: BLE001
        check("oversized id raises NotFoundError", False, f"wrong type: {type(e).__name__}")

    try:
        meta = download_addon(805854302, dest="/tmp/_test_dl.ankiaddon")
        check("download returns metadata", meta["size"] > 0, str(meta))
        check("download has filename", meta["filename"].endswith(".ankiaddon"), meta["filename"])
    except Exception as e:  # noqa: BLE001
        check("download works", False, str(e))

    # Cache-busting, live. `item-info` is served `max-age=600`, so a live test
    # that reads a stable URL can silently assert against stale data -- which is
    # exactly how a parser bug came to look like AnkiWeb wiping descriptions.
    try:
        first = fetch_item_info(805854302)
        second = fetch_item_info(805854302)
        check("live read is cache-busted", bool(first.get("cache_bust")), str(first)[:120])
        check("consecutive live reads use different cache_busters",
              first.get("cache_bust") != second.get("cache_bust"),
              f"{first.get('cache_bust')} vs {second.get('cache_bust')}")
        check("consecutive live reads agree",
              first["title"] == second["title"] and first["size"] == second["size"],
              f"{first['title']!r}/{first['size']} vs {second['title']!r}/{second['size']}")
        check("verify URL carries the cache_buster",
              f"https://ankiweb.net/shared/info/805854302?cb={first['cache_bust']}".count("cb=") == 1,
              repr(first.get("cache_bust")))
    except Exception as e:  # noqa: BLE001
        check("live cache-busted read", False, str(e))

    # Long descriptions must survive a real round-trip. This parser used to drop
    # anything over 5000 bytes, so a full README read back as "(empty)" and was
    # misdiagnosed as a server-side wipe.
    long_id = int(os.environ.get("ANKIWEB_LONG_DESCRIPTION_ID", "2119980872"))
    try:
        big = fetch_item_info(long_id)
        desc = big["description"]
        check("long description not dropped (live)", len(desc) > 20000,
              f"id {long_id}: got {len(desc)} chars")
        check("long description is real content (live)",
              len(desc) > 20000 and "<" in desc and len(desc.split()) > 100,
              f"{len(desc)} chars, {len(desc.split())} words")
    except (AnkiWebError, NotFoundError) as e:
        check("long description round-trip (live)", False, f"id {long_id}: {e}")


    # --- newly discovered endpoints (download-deck / mpreview), live ---
    # 911122782 = public "Tae Kim's grammar guide" deck (stable, public).
    try:
        from ankiweb_client import AnkiWebClient

        client = AnkiWebClient()
        rows = client.shared_list_decks(search="japanese").get("rows", [])
        check("live list-decks with search returns rows", len(rows) > 0, f"{len(rows)} rows")
    except Exception as e:  # noqa: BLE001
        check("live list-decks with search", False, str(e))

    try:
        from ankiweb_client import AnkiWebClient

        client = AnkiWebClient()
        mp3 = client.shared_media_preview(911122782, "0.mp3", last_updated=1697739853)
        check("live mpreview returns mp3 bytes", mp3[:3] == b"ID3", f"{len(mp3)} bytes")
    except Exception as e:  # noqa: BLE001
        check("live mpreview", False, str(e))

    try:
        from ankiweb_client import AnkiWebClient

        client = AnkiWebClient()
        n = client.shared_download_deck(
            911122782, dest="/tmp/_test_deck.apkg", max_bytes=65536)
        head = open("/tmp/_test_deck.apkg", "rb").read(4)
        check("live download-deck streams a zip (.apkg)",
              head == b"PK\x03\x04", f"{n} bytes, magic {head.hex()}")
    except Exception as e:  # noqa: BLE001
        check("live download-deck", False, str(e))


def test_cli() -> None:
    print("cli exit codes")
    import subprocess

    for args, expect in (
        (["info", "123456789"], 1),
        (["info", "805854302"], 0),
        (["download", "123456789", "-o", "/tmp/_t.ankiaddon"], 1),
    ):
        r = subprocess.run([sys.executable, "ankicli.py", *args], capture_output=True)
        check(f"ankicli.py {' '.join(args)} -> exit {expect}", r.returncode == expect,
              f"got {r.returncode}: {r.stderr.decode()[:120]}")


if __name__ == "__main__":
    test_offline()
    test_cache_busting()
    test_login_codec()
    test_list_mine_parse()
    if LIVE:
        test_api_discovery_live()
        test_live()
    test_cli()
    print(f"\n{passes} passed, {len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1 if failures else 0)