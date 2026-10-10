"""AnkiWeb session login for read endpoints that need auth (e.g. list-mine).

Uploads keep using the upstream Node engine (dist/index.js). This module only
adds the login step needed to call authenticated *read* endpoints from Python.

Wire format from upstream proto/ankiweb.proto:
  POST /svc/account/login
    LoginRequest{username=1, password=2} -> LoginResponse{status=1, token=2}
  status: 0 UNKNOWN, 1 AUTHENTICATED, 2 INVALID_USER, 3 INVALID_PASS
"""

from __future__ import annotations

import re

import requests

BASE = "https://ankiweb.net"
LOGIN_URL = f"{BASE}/svc/account/login"

LOGIN_STATUS = {
    0: "UNKNOWN",
    1: "AUTHENTICATED",
    2: "INVALID_USER",
    3: "INVALID_PASS",
}


class AuthError(RuntimeError):
    pass


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field_str(field: int, text: str) -> bytes:
    raw = text.encode("utf-8")
    return _varint((field << 3) | 2) + _varint(len(raw)) + raw


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
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


def encode_login_request(username: str, password: str) -> bytes:
    return _field_str(1, username) + _field_str(2, password)


def decode_login_response(buf: bytes) -> tuple[int, str]:
    status, token = 0, ""
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, pos = _read_varint(buf, pos)
            if field == 1:
                status = v
        elif wire == 2:
            ln, pos = _read_varint(buf, pos)
            if field == 2:
                token = buf[pos : pos + ln].decode("utf-8", "replace")
            pos += ln
        else:
            raise ValueError(f"unexpected wire type {wire}")
    return status, token


def load_dotenv(path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    from pathlib import Path as _Path

    p = _Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        import os as _os

        _os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def login(username: str, password: str, timeout: int = 30) -> str:
    """Return the raw `ankiweb` session cookie value."""
    r = requests.post(
        LOGIN_URL,
        data=encode_login_request(username, password),
        headers={
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
            "Referer": f"{BASE}/account/login",
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        raise AuthError(f"login HTTP {r.status_code}: {r.text[:300]}")
    status, _token = decode_login_response(r.content)
    if status != 1:
        raise AuthError(f"login failed: {LOGIN_STATUS.get(status, status)}")
    cookie = r.cookies.get("ankiweb")
    if not cookie:
        m = re.search(r"ankiweb=([^;]+)", r.headers.get("Set-Cookie", ""))
        cookie = m.group(1) if m else None
    if not cookie:
        raise AuthError("login succeeded but no ankiweb cookie in response")
    return cookie