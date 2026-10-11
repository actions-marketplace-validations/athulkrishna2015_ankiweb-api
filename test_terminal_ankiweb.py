#!/usr/bin/env python3
"""Tests for terminal_ankiweb parsing and CLI exit codes.

Offline tests run anywhere. Live tests (--live) hit AnkiWeb and need network.

    python3 test_terminal_ankiweb.py          # offline only
    python3 test_terminal_ankiweb.py --live   # + network round-trips
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

from terminal_ankiweb import (
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
        test_live()
    test_cli()
    print(f"\n{passes} passed, {len(failures)} failed")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1 if failures else 0)