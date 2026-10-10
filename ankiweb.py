"""AnkiWeb hidden svc API client (stdlib protobuf codec + requests).

Reverse-engineered from:
- https://github.com/danny900714/upload-anki-addon (MIT)
  - proto/ankiweb.proto, src/ankiweb.ts, src/main.ts
- https://github.com/ankitects/anki/blob/main/qt/aqt/addons.py (download_addon)
- https://addon-docs.ankiweb.net/sharing.html (.ankiaddon format)

Endpoints (AnkiWeb has no public API; these are used by the SvelteKit frontend):
  POST https://ankiweb.net/svc/account/login          -> LoginResponse + Set-Cookie: ankiweb=...
  POST https://ankiweb.net/svc/shared/upload-addon    -> UploadAddonResponse{addon_id}
  GET  https://ankiweb.net/shared/download/<id>?v=2.1&p=<ver> -> 303 -> /svc/shared/download-addon/<id>?t=..&minpt=..&maxpt=..&bidx=..

Only dependency: requests.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

import requests

BASE = "https://ankiweb.net"
LOGIN_URL = f"{BASE}/svc/account/login"
UPLOAD_URL = f"{BASE}/svc/shared/upload-addon"
SHARED = f"{BASE}/shared/"

OCTET = "application/octet-stream"


# ---------------------------------------------------------------- protobuf mini-codec
# wire types: 0 = varint, 2 = length-delimited


def _varint_encode(n: int) -> bytes:
    if n < 0:  # int32 negative -> sign-extend to 64 bit (protobuf semantics)
        n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


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


def _tag(field: int, wire: int) -> bytes:
    return _varint_encode((field << 3) | wire)


def _enc_str(field: int, s: str) -> bytes:
    b = s.encode("utf-8")
    return _tag(field, 2) + _varint_encode(len(b)) + b


def _enc_bytes(field: int, b: bytes) -> bytes:
    return _tag(field, 2) + _varint_encode(len(b)) + b


def _enc_msg(field: int, msg: bytes) -> bytes:
    return _tag(field, 2) + _varint_encode(len(msg)) + msg


def _enc_varint(field: int, n: int) -> bytes:
    return _tag(field, 0) + _varint_encode(n)


def _decode_fields(buf: bytes) -> list[tuple[int, int, bytes | int]]:
    """Return list of (field_no, wire_type, value). value is int for varint,
    bytes for length-delimited. Other wire types raise."""
    out = []
    pos = 0
    while pos < len(buf):
        key, pos = _varint_decode(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, pos = _varint_decode(buf, pos)
            # int32 negative values arrive as huge uint64; convert back if > 2**31?
            # Caller decides; keep raw unsigned here.
            out.append((field, wire, v))
        elif wire == 2:
            ln, pos = _varint_decode(buf, pos)
            v = buf[pos : pos + ln]
            pos += ln
            out.append((field, wire, v))
        else:
            raise ValueError(f"unsupported wire type {wire} for field {field}")
    return out


def _to_int32(n: int) -> int:
    # wire gives unsigned 64-bit; reinterpret low 32 bits as signed
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n & 0x80000000 else n


# ---------------------------------------------------------------- messages


def encode_login(username: str, password: str) -> bytes:
    return _enc_str(1, username) + _enc_str(2, password)


def decode_login_response(buf: bytes) -> tuple[int, str]:
    status = 0
    token = ""
    for field, wire, v in _decode_fields(buf):
        if field == 1 and wire == 0:
            assert isinstance(v, int)
            status = v
        elif field == 2 and wire == 2:
            assert isinstance(v, bytes)
            token = v.decode("utf-8", "replace")
    return status, token


def encode_branch(min_version: int, max_version: int) -> bytes:
    # field1 uint32 varint, field2 int32 varint (may be negative)
    return _enc_varint(1, min_version) + _enc_varint(2, max_version)


def encode_addon_info(
    title: str,
    description: str,
    branches: list[tuple[int, int]],
    addon_id: int | None = None,
    tags: str = "",
    support_url: str = "",
) -> bytes:
    out = b""
    if addon_id is not None:
        out += _enc_varint(1, addon_id)
    out += _enc_str(2, title)
    out += _enc_str(3, tags)
    out += _enc_str(4, support_url)
    out += _enc_str(5, description)
    for lo, hi in branches:
        out += _enc_msg(6, encode_branch(lo, hi))
    return out


def encode_addon_file(zip_data: bytes, branch_index: int) -> bytes:
    return _enc_bytes(1, zip_data) + _enc_varint(2, branch_index)


def encode_upload(info: bytes, file: bytes | None = None) -> bytes:
    out = _enc_msg(1, info)
    if file is not None:
        out += _enc_msg(2, file)
    return out


def decode_upload_response(buf: bytes) -> int:
    for field, wire, v in _decode_fields(buf):
        if field == 1 and wire == 0:
            assert isinstance(v, int)
            return v
    return 0


# ---------------------------------------------------------------- branch notation
# Port of parseBranchNotation from danny900714/upload-anki-addon/src/main.ts
# Format: "min-max[+]", e.g. "2.1.1-2.1.66", "23.10-25.09.4+".
# max negated unless suffixed with "+" (means "all future versions").


def parse_branch(branch: str) -> tuple[int, int]:
    parts = branch.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"branch must be MIN-MAX, got: {branch!r}")
    out = [0, 0]
    for i, ver in enumerate(parts):
        future = False
        if i == 1 and ver.endswith("+"):
            future = True
            ver = ver[:-1]  # NOTE: upstream TS forgets this assignment; we fix it
        ver = ver.strip()
        if ver.startswith("2.1."):
            num = ver[4:]
            try:
                n = int(num)
            except ValueError:
                raise ValueError(f"invalid 2.1.x version in branch {branch!r}") from None
            out[i] = n
        else:
            nums = ver.split(".")
            if len(nums) > 3:
                raise ValueError(f"invalid version in branch {branch!r}")
            mult = 10000
            total = 0
            for s in nums:
                try:
                    n = int(s)
                except ValueError:
                    raise ValueError(f"invalid version in branch {branch!r}") from None
                if n >= 100 or n < 0:
                    raise ValueError(f"invalid version in branch {branch!r}")
                total += n * mult
                mult //= 100
            out[i] = total
        if i == 1 and not future:
            out[i] = -out[i]
    return out[0], out[1]


def int_version_to_str(n: int) -> str:
    """Mirror Anki's int_version_to_str for readable logs (best-effort)."""
    if n <= 66:  # old 2.1.x scheme
        return f"2.1.{n}"
    s = str(abs(n))
    # scheme is major*10000 + minor*100 + patch, but be lenient
    if len(s) <= 4:
        return s
    major = int(s[:-4]) if len(s) > 4 else 0
    minor = int(s[-4:-2])
    patch = int(s[-2:])
    base = f"{major}.{minor:02d}"
    return base if patch == 0 else f"{base}.{patch}"


# ---------------------------------------------------------------- API


class AnkiWebError(RuntimeError):
    pass


def login(username: str, password: str, timeout: int = 30) -> str:
    """POST svc/account/login, return raw `ankiweb` cookie value."""
    body = encode_login(username, password)
    r = requests.post(
        LOGIN_URL,
        data=body,
        headers={
            "Accept": "*/*",
            "Content-Type": OCTET,
            "Referer": f"{BASE}/account/login",
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise AnkiWebError(f"login HTTP {r.status_code}: {r.text[:500]}")
    status, _token = decode_login_response(r.content)
    if status != 1:
        names = {0: "UNKNOWN", 1: "AUTHENTICATED", 2: "INVALID_USER", 3: "INVALID_PASS"}
        raise AnkiWebError(f"login failed, status={names.get(status, status)}")
    cookie = r.cookies.get("ankiweb")
    if not cookie:
        # fallback: parse raw Set-Cookie
        m = re.search(r"ankiweb=([^;]+)", r.headers.get("Set-Cookie", ""))
        if m:
            cookie = m.group(1)
    if not cookie:
        raise AnkiWebError("login OK but no ankiweb cookie in response")
    return cookie


def upload_addon(
    cookie: str,
    title: str,
    description: str,
    branches: list[tuple[int, int]],
    addon_id: int | None = None,
    tags: str = "",
    support_url: str = "",
    files: dict[int, bytes] | None = None,
    timeout: int = 60,
) -> int:
    """Upload addon (possibly multi-branch). files maps branch_index -> zip bytes.
    If files is None/empty -> metadata-only update (single request, no file).
    Returns final addon_id."""
    if support_url and not support_url.startswith("http"):
        raise ValueError("support_url must start with http")
    if len(title) >= 80:
        raise ValueError("title must be fewer than 80 characters")
    referer = f"{BASE}/shared/upload" + (f"?id={addon_id}" if addon_id else "")
    headers = {
        "Accept": "*/*",
        "Content-Type": OCTET,
        "Cookie": f"has_auth=1; ankiweb={cookie}",
        "Referer": referer,
    }
    info = encode_addon_info(title, description, branches, addon_id, tags, support_url)

    result_id = addon_id or 0
    if not files:
        body = encode_upload(info)
        r = requests.post(UPLOAD_URL, data=body, headers=headers, timeout=timeout)
        if r.status_code != 200:
            raise AnkiWebError(f"upload HTTP {r.status_code}: {r.text[:1000]}")
        result_id = decode_upload_response(r.content)
    else:
        for idx in sorted(files):
            fmsg = encode_addon_file(files[idx], idx)
            # addon_id for follow-up requests: use id returned from previous call
            use_id = result_id or addon_id
            i2 = encode_addon_info(title, description, branches, use_id, tags, support_url)
            body = encode_upload(i2, fmsg)
            # update referer once we know the id
            h = dict(headers)
            if use_id:
                h["Referer"] = f"{BASE}/shared/upload?id={use_id}"
            r = requests.post(UPLOAD_URL, data=body, headers=h, timeout=timeout)
            if r.status_code != 200:
                raise AnkiWebError(
                    f"upload branch {idx} HTTP {r.status_code}: {r.text[:1000]}"
                )
            result_id = decode_upload_response(r.content)
    return result_id


def download_addon(
    addon_id: int, dest: str | None = None, point_version: int = 250902, timeout: int = 60
) -> dict:
    """Download .ankiaddon via /shared/download/<id> (follows 303 to svc).
    Returns dict with path, filename, final_url, t/minpt/maxpt/bidx."""
    url = f"{SHARED}download/{addon_id}?v=2.1&p={point_version}"
    with requests.get(url, timeout=timeout, stream=True, allow_redirects=True) as r:
        if r.status_code != 200:
            raise AnkiWebError(f"download HTTP {r.status_code} for id {addon_id}")
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
