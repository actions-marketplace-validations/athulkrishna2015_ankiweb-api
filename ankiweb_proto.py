"""Schema-driven protobuf codec for the AnkiWeb `/svc/*` API.

Pure stdlib. Wire format only - no .proto compilation, no protobuf dependency.
Messages are described by `ankiweb_schema.SCHEMA` (field numbers + types
recovered from AnkiWeb's own frontend bundle).

Supported field types
---------------------
scalar : int32 int64 uint32 uint64 sint32 sint64 bool sfixed32 sfixed64
         fixed32 fixed64 float double string bytes enum
message : nested message (named in SCHEMA)

Supported modifiers
-------------------
repeated  - packed (numeric scalars) or unpacked (everything else)
optional  - proto3 `optional`, i.e. presence tracked
map       - decoded as repeated key/value submessages

Unknown fields are preserved on decode and re-emitted on encode, so a round-trip
through this codec does not silently drop data from a newer server.
"""

from __future__ import annotations

import struct as _struct

from ankiweb_schema import SCHEMA

# ---------------------------------------------------------------- wire helpers


def _varint(n: int) -> bytes:
    if n < 0:
        n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


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
        if shift >= 70:
            raise ValueError("varint too long")


def _zigzag_decode(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def _zigzag_encode(n: int, bits: int = 64) -> int:
    return (n << 1) ^ (n >> (bits - 1))


def _to_signed(n: int, bits: int) -> int:
    n &= (1 << bits) - 1
    return n - (1 << bits) if n & (1 << (bits - 1)) else n


# numeric types that can use packed encoding
_PACKABLE = {
    "int32", "int64", "uint32", "uint64", "sint32", "sint64",
    "bool", "sfixed32", "sfixed64", "fixed32", "fixed64", "float", "double", "enum",
}


def _is_numeric(t: str) -> bool:
    return t in _PACKABLE


def _decode_scalar(t: str, raw: bytes, wire: int):
    """Decode one scalar value given its wire type."""
    if t == "string":
        return raw.decode("utf-8", "replace")
    if t == "bytes":
        return raw
    if t == "bool":
        return bool(raw if wire == 0 else raw[0])
    if t in ("float",):
        return _struct.unpack("<f", raw)[0]
    if t in ("double",):
        return _struct.unpack("<d", raw)[0]
    if t == "fixed32":
        return _struct.unpack("<I", raw)[0]
    if t == "sfixed32":
        return _struct.unpack("<i", raw)[0]
    if t == "fixed64":
        return _struct.unpack("<Q", raw)[0]
    if t == "sfixed64":
        return _struct.unpack("<q", raw)[0]
    if t in ("int32", "int64"):
        return _to_signed(raw, 64) if t == "int64" else _to_signed(raw, 32)
    if t in ("uint32", "uint64"):
        return raw & 0xFFFFFFFF if t == "uint32" else raw
    if t in ("sint32", "sint64"):
        return _to_signed(_zigzag_decode(raw), 32 if t == "sint32" else 64)
    if t == "enum":
        return _to_signed(raw, 32)
    raise ValueError(f"unsupported scalar type {t}")


def _encode_scalar(t: str, value) -> tuple[int, bytes]:
    """Return (wire_type, payload_bytes) for one scalar."""
    if t == "string":
        return 2, value.encode("utf-8") if isinstance(value, str) else bytes(value)
    if t == "bytes":
        return 2, bytes(value)
    if t == "bool":
        return 0, _varint(1 if value else 0)
    if t == "float":
        return 5, _struct.pack("<f", value)
    if t == "double":
        return 1, _struct.pack("<d", value)
    if t == "fixed32":
        return 5, _struct.pack("<I", value)
    if t == "sfixed32":
        return 5, _struct.pack("<i", value)
    if t == "fixed64":
        return 1, _struct.pack("<Q", value)
    if t == "sfixed64":
        return 1, _struct.pack("<q", value)
    if t == "sint32":
        return 0, _varint(_zigzag_encode(value, 32))
    if t == "sint64":
        return 0, _varint(_zigzag_encode(value, 64))
    if t == "int32":
        return 0, _varint(value & 0xFFFFFFFFFFFFFFFF if value >= 0 else value)
    if t == "int64":
        return 0, _varint(value)
    if t in ("uint32", "uint64", "enum"):
        return 0, _varint(value)
    raise ValueError(f"unsupported scalar type {t}")


def _wire_width(t: str) -> int:
    return {
        "float": 4, "fixed32": 4, "sfixed32": 4, "double": 8,
        "fixed64": 8, "sfixed64": 8,
    }.get(t, 0)


# ---------------------------------------------------------------- public API


class ProtoError(ValueError):
    pass


def _fields_of(msg_name: str) -> list[dict]:
    try:
        return SCHEMA[msg_name]["fields"]
    except KeyError:
        raise ProtoError(f"unknown message {msg_name!r}") from None


def decode(msg_name: str, buf: bytes) -> dict:
    """Decode protobuf bytes into a dict keyed by field name.

    Returns a plain dict: scalars as Python values, nested messages as dicts,
    repeated fields as lists, and unknown fields under `_unknown` as raw bytes.
    """
    fields = _fields_of(msg_name)
    by_no = {f["no"]: f for f in fields}
    out: dict = {}
    unknown: dict[int, list] = {}
    pos = 0
    while pos < len(buf):
        try:
            key, pos = _read_varint(buf, pos)
            no, wire = key >> 3, key & 7
        except ValueError as exc:
            raise ProtoError(f"invalid protobuf key at byte {pos}: {exc}") from exc
        f = by_no.get(no)
        if wire == 0:
            raw, pos = _read_varint(buf, pos)
        elif wire == 1:
            if pos + 8 > len(buf):
                raise ProtoError(f"truncated fixed64 field at byte {pos}")
            raw, pos = buf[pos:pos + 8], pos + 8
        elif wire == 5:
            if pos + 4 > len(buf):
                raise ProtoError(f"truncated fixed32 field at byte {pos}")
            raw, pos = buf[pos:pos + 4], pos + 4
        elif wire == 2:
            ln, pos = _read_varint(buf, pos)
            if pos + ln > len(buf):
                raise ProtoError(f"truncated length-delimited field at byte {pos}")
            raw, pos = buf[pos:pos + ln], pos + ln
        elif wire in (3, 4):
            # deprecated groups: skip to matching end-group
            depth = 1
            while pos < len(buf) and depth:
                k2, pos = _read_varint(buf, pos)
                w2 = k2 & 7
                if w2 == 3:
                    depth += 1
                elif w2 == 4:
                    depth -= 1
                elif w2 == 0:
                    _, pos = _read_varint(buf, pos)
                elif w2 == 2:
                    l2, pos = _read_varint(buf, pos)
                    pos += l2
                elif w2 == 1:
                    pos += 8
                elif w2 == 5:
                    pos += 4
            raw = None
        else:
            break

        if f is None:
            unknown.setdefault(no, []).append((wire, raw))
            continue

        t = f["type"]
        name = f["name"]
        expected_wire = f["wire"]
        packed_numeric = f["repeated"] and _is_numeric(t) and expected_wire == 0
        if wire != expected_wire and not (packed_numeric and wire == 2):
            # A reused/incorrect schema must not silently reinterpret a
            # length-delimited payload as an integer (or vice versa).
            unknown.setdefault(no, []).append((wire, raw))
            continue
        if f["repeated"]:
            # packed numeric run
            if wire == 2 and _is_numeric(t) and f["wire"] == 0:
                vals = []
                p2 = 0
                while p2 < len(raw):
                    v, p2 = _read_varint(raw, p2)
                    vals.append(_decode_scalar(t, v, 0))
                out.setdefault(name, []).extend(vals)
            elif wire == 2 and _is_numeric(t) and f["wire"] in (1, 5):
                width = _wire_width(t)
                if len(raw) % width:
                    raise ProtoError(f"malformed packed {t} field {name!r}")
                vals = [_decode_scalar(t, raw[i:i + width], f["wire"])
                        for i in range(0, len(raw), width)]
                out.setdefault(name, []).extend(vals)
            elif t == "message":
                out.setdefault(name, []).append(decode(f["T"], raw))
            elif t == "string":
                out.setdefault(name, []).append(raw.decode("utf-8", "replace"))
            elif t == "bytes":
                out.setdefault(name, []).append(raw)
            else:
                out.setdefault(name, []).append(_decode_scalar(t, raw, wire))
        else:
            if t == "message":
                out[name] = decode(f["T"], raw)
            elif t == "string":
                out[name] = raw.decode("utf-8", "replace")
            elif t == "bytes":
                out[name] = raw
            else:
                out[name] = _decode_scalar(t, raw, wire)
    if unknown:
        out["_unknown"] = unknown
    return out


def encode(msg_name: str, _fields: dict | None = None, **kwargs) -> bytes:
    """Encode a dict (or kwargs) into protobuf bytes using the schema.

    >>> encode("LoginRequest", username="me", password="pw")
    """
    data = dict(_fields or {})
    data.update(kwargs)
    fields = _fields_of(msg_name)
    by_name = {f["name"]: f for f in fields}
    out = bytearray()

    for f in fields:
        name = f["name"]
        if name not in data:
            continue
        value = data[name]
        if value is None:
            continue
        no, t = f["no"], f["type"]

        if f["repeated"]:
            if value is None:
                continue
            vals = value if isinstance(value, (list, tuple)) else [value]
            if not vals:
                continue
            if _is_numeric(t):
                packed = bytearray()
                for v in vals:
                    w, payload = _encode_scalar(t, v)
                    if w == 0:
                        packed += payload
                    elif w in (1, 5):
                        packed += payload
                out += _varint((no << 3) | 2) + _varint(len(packed)) + bytes(packed)
            else:
                for v in vals:
                    if t == "message":
                        payload = encode(f["T"], v)
                        out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
                    elif t == "string":
                        payload = v.encode("utf-8") if isinstance(v, str) else bytes(v)
                        out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
                    elif t == "bytes":
                        payload = bytes(v)
                        out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
                    else:
                        w, payload = _encode_scalar(t, v)
                        out += _varint((no << 3) | w) + payload
        else:
            if t == "message":
                payload = encode(f["T"], value)
                out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
            elif t == "string":
                payload = value.encode("utf-8") if isinstance(value, str) else bytes(value)
                out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
            elif t == "bytes":
                payload = bytes(value)
                out += _varint((no << 3) | 2) + _varint(len(payload)) + payload
            else:
                w, payload = _encode_scalar(t, value)
                out += _varint((no << 3) | w) + payload

    # re-emit unknown fields the caller passed through
    for no, entries in (data.get("_unknown") or {}).items():
        for wire, raw in entries:
            if raw is None:
                continue
            out += _varint((no << 3) | wire)
            if wire == 0:
                out += _varint(raw)
            elif wire in (1, 5):
                out += raw
            elif wire == 2:
                out += _varint(len(raw)) + raw
    return bytes(out)


def _varint_raw(n: int) -> bytes:
    return _varint(n)


def describe(msg_name: str) -> str:
    """Human-readable field list, for docs and debugging."""
    lines = [f"{msg_name}:"]
    for f in _fields_of(msg_name):
        flags = []
        if f["repeated"]:
            flags.append("repeated")
        if f["optional"]:
            flags.append("optional")
        fl = (" [" + ", ".join(flags) + "]") if flags else ""
        t = f["T"] if f["type"] == "message" else f["type"]
        lines.append(f"  {f['no']:>3}  {f['name']:<28} {t}{fl}")
    return "\n".join(lines)
