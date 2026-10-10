#!/usr/bin/env python3
"""Generate ankiweb_schema.py from AnkiWeb's frontend bundle.

AnkiWeb's web app is a SvelteKit bundle that embeds protobuf-es message
definitions in plain JS. We parse them to recover the wire schema for every
`/svc/*` endpoint, so the Python client is generated rather than guessed.

Source: https://ankiweb.net/shared/mine -> the app shell -> entry/app.*.mjs
        -> chunks/frontend.*.mjs  (holds makeMessageType definitions)

Usage:
    python3 tools/generate_schema.py            # download + regenerate
    python3 tools/generate_schema.py --bundle /tmp/awjs/frontend.mjs

Type codes are protobuf FieldDescriptorProto.Type (descriptor.proto), which is
what protobuf-es embeds as the `T:` property:
    1 DOUBLE 2 FLOAT 3 INT64 4 UINT64 5 INT32 6 FIXED64 7 FIXED32
    8 BOOL 9 STRING 11 MESSAGE 12 BYTES 13 UINT32 14 ENUM
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ankiweb_schema.py"

# FieldDescriptorProto.Type -> (python name, wire type)
TYPES: dict[int, tuple[str, int]] = {
    1: ("double", 1), 2: ("float", 5), 3: ("int64", 0), 4: ("uint64", 0),
    5: ("int32", 0), 6: ("fixed64", 1), 7: ("fixed32", 5), 8: ("bool", 0),
    9: ("string", 2), 10: ("group", 3), 11: ("message", 2), 12: ("bytes", 2),
    13: ("uint32", 0), 14: ("enum", 0), 15: ("sfixed32", 5), 16: ("sfixed64", 1),
    17: ("sint32", 0), 18: ("sint64", 0),
}


def discover_bundle() -> str:
    """Follow the SvelteKit app shell to the chunk holding the schemas.

    Newer shells use Vite's __vite__mapDeps table instead of entry/app.*.mjs
    + nodes/*.mjs imports, so probe several strategies in order:
      1. legacy entry/app.*.mjs + nodes/*
      2. Vite mapDeps table (../chunks/frontend.*.mjs entry)
      3. direct scan of likely chunk names
    """
    with urllib.request.urlopen("https://ankiweb.net/shared/mine", timeout=30) as r:
        shell = r.read().decode("utf-8", "replace")

    def fetch(path: str) -> str | None:
        try:
            with urllib.request.urlopen("https://ankiweb.net" + path, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None

    # Strategy 2 (current): Vite mapDeps table in entry/app.*.mjs
    for m in re.finditer(r'/_app/immutable/entry/app\.[A-Za-z0-9_-]+\.mjs', shell):
        app_js = fetch(m.group(0))
        if not app_js:
            continue
        for dep in sorted(set(re.findall(r'"(\.\./(?:chunks|nodes)/[^"]+\.mjs)"', app_js))):
            if "frontend." not in dep:
                continue
            body = fetch("/_app/immutable/chunks/" + dep.split("/")[-1])
            if body and "makeMessageType" in body and "/svc/" in body:
                return body
        # fall through: scan every dep for the schema chunk
        for dep in sorted(set(re.findall(r'"(\.\./(?:chunks|nodes)/[^"]+\.mjs)"', app_js))):
            body = fetch("/_app/immutable/chunks/" + dep.split("/")[-1])
            if not body:
                # nodes live under a different prefix
                body = fetch("/_app/immutable/nodes/" + dep.split("/")[-1])
            if body and "makeMessageType" in body and "/svc/" in body:
                return body

    # Strategy 1 (legacy): nodes/*.mjs imports in app chunk
    for m in re.finditer(r'/_app/immutable/entry/app\.([A-Za-z0-9_-]+)\.mjs', shell):
        app_js = fetch(m.group(0))
        if not app_js:
            continue
        nodes = sorted(set(re.findall(r"nodes/(\d+\.[A-Za-z0-9_-]+\.mjs)", app_js)))
        for node in nodes:
            body = fetch(f"/_app/immutable/nodes/{node}")
            if body and "makeMessageType" in body and "/svc/" in body:
                return body
    raise SystemExit("no chunk contained both makeMessageType and /svc/")


# Response types for endpoints whose call site hides the type behind a shared
# or reused variable. Each entry was verified against the bundle by checking
# the response var's first field names (see docs/API.md, "Extending the schema").
#
#   /svc/shared/list-mine        -> Ft  {items, reviews, expired_decks}
#   /svc/shared/list-addons      -> Dt  {rows, user_upload_status}
#   /svc/shared/list-decks       -> At  {rows}
#   /svc/shared/items-by-author  -> Ut  {items}
#   /svc/shared/item-info        -> Tt  {available, missing, access_denied}
#   /svc/shared/upload-addon     -> Jt  {addon_id}
#   /svc/editor/get-notetype-fields -> as {fields}
SHARED_RESPONSE_ALIASES: dict[str, str] = {
    "/svc/shared/items-by-author": "Ut",
    "/svc/shared/list-decks": "At",
    "/svc/shared/list-addons": "Dt",
    "/svc/shared/list-mine": "Ft",
    "/svc/shared/item-info": "Tt",
    "/svc/shared/upload-addon": "Jt",
    "/svc/editor/get-notetype-fields": "as",
    "/svc/account/signup": "ra",
    "/svc/account/verify-email": "ca",
}

# The frontend's minifier can reuse message variables and the call-site regex
# can associate a neighbouring message with an endpoint. Keep verified
# endpoint-specific corrections here (values are minified message variables).
# As of Oct 2026 the precise call-site parser reads responses directly, so no
# overrides are needed; login is kept as a pinned sanity check.
ENDPOINT_RESPONSE_OVERRIDES: dict[str, str] = {
    "/svc/account/login": "Jn",  # {status, token}; Xn is needs_to_confirm
}


def apply_aliases(eps: list[dict], msgs: dict[str, dict]) -> list[dict]:
    """Apply verified endpoint-specific response aliases and corrections."""
    known = set(msgs)
    out = []
    for e in eps:
        e = dict(e)
        if e["path"] in ENDPOINT_RESPONSE_OVERRIDES:
            alias = ENDPOINT_RESPONSE_OVERRIDES[e["path"]]
            e["resp"] = alias if alias in known else ""
        else:
            alias = SHARED_RESPONSE_ALIASES.get(e["path"])
            if alias and alias in known:
                e["resp"] = alias
        if not e.get("resp") or e["resp"] not in known:
            e["resp"] = ""  # unresolved; surfaced by the report below
        out.append(e)
    return out


FIELD_RE = re.compile(
    r'\{no:(\d+),name:"([^"]+)",kind:"([^"]+)",T:([^,}]+)'
    r'(,repeated:!0)?(,opt:!0)?(?:,oneof:"([^"]+)")?(?:,default:[^}]*)?\}'
)
MSG_START = re.compile(r'([\w$]+)=r\.makeMessageType\(')
LOCAL_NAME = re.compile(r'localName:"([^"]+)"')


def _match_bracket(src: str, open_idx: int, op: str, cl: str) -> int:
    """Index just past the bracket matching src[open_idx]; -1 if unbalanced.

    Needed because field arrays contain nested braces and regex cannot count them.
    """
    depth = 0
    i = open_idx
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == '"':  # skip string literals (braces inside are not structural)
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == '"':
                    break
                i += 1
        elif ch == op:
            depth += 1
        elif ch == cl:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def iter_message_defs(src: str):
    """Yield (var, local_name, fields_source) for each makeMessageType call."""
    for m in MSG_START.finditer(src):
        var = m.group(1)
        i = m.end()
        n = len(src)
        # First argument is the proto package name, a string literal: "".
        while i < n and src[i] in " \t\n":
            i += 1
        if i < n and src[i] == '"':
            end = src.find('"', i + 1)
            if end == -1:
                continue
            j = end + 1
        else:
            arg_end = _match_bracket(src, i, "(", ")")
            if arg_end < 0:
                continue
            j = arg_end
        # Second argument: ()=>[...]  or  function(){return [...]}
        while j < n and src[j] in ", \t\n":
            j += 1
        # An empty message may be declared inline with no thunk at all:
        #   makeMessageType("",[])
        # Handle that first, or the scanner would swallow the *next* definition.
        if j < n and src[j] == "[":
            arr_end = _match_bracket(src, j, "[", "]")
            if arr_end < 0:
                continue
            yield var, "", src[j + 1:arr_end - 1]
            continue
        if src.startswith("()=>", j):
            j += 4  # len("()=>") - the array literal follows the arrow
        elif src.startswith("function", j):
            ret = src.find("return", j)
            j = ret + 6 if ret != -1 else j
        else:
            continue
        while j < n and src[j] in " \t\n":
            j += 1
        if j >= n or src[j] != "[":
            continue
        arr_end = _match_bracket(src, j, "[", "]")
        if arr_end < 0:
            continue
        body = src[j + 1:arr_end - 1]
        # trailing {localName:"..."} object, if any
        local = ""
        k = arr_end
        while k < n and src[k] in ", \t\n":
            k += 1
        if k < n and src[k] == "{":
            obj_end = _match_bracket(src, k, "{", "}")
            if obj_end > 0:
                lm = LOCAL_NAME.search(src[k:obj_end])
                if lm:
                    local = lm.group(1)
        yield var, local, body
ENUM_RE = re.compile(r'([\w$]+)=r\.makeEnum\("([^"]*)",\[(.*?)\]\)', re.S)
ENUM_ITEM_RE = re.compile(r'\{no:(\d+),name:"([^"]+)",localName:"([^"]+)"\}')


def parse_enums(src: str) -> dict[str, dict]:
    """Recover enum value tables; minifier keeps `name:` intact."""
    enums: dict[str, dict] = {}
    for m in ENUM_RE.finditer(src):
        var = m.group(1)
        values = {}
        for v in ENUM_ITEM_RE.finditer(m.group(3)):
            values[int(v.group(1))] = {"name": v.group(2), "short": v.group(3)}
        enums[var] = {"values": values}
    return enums


def parse_messages(src: str, enums: dict[str, dict]) -> dict[str, dict]:
    msgs: dict[str, dict] = {}
    for var, local, body in iter_message_defs(src):
        name = local or var
        fields = []
        for f in FIELD_RE.finditer(body):
            tcode_raw = f.group(4).strip()
            kind = f.group(3)
            if kind == "message":
                ttype, wire = "message", 2
            elif kind == "enum":
                enum_var = ""
                em = re.match(r"r\.getEnumType\((\w+)\)", tcode_raw)
                if em:
                    enum_var = em.group(1)
                ttype, wire = "enum", 0
            else:
                try:
                    ttype, wire = TYPES[int(tcode_raw)]
                except (KeyError, ValueError):
                    ttype, wire = "unknown", 2
            entry = {
                "no": int(f.group(1)),
                "name": f.group(2),
                "kind": kind,
                "type": ttype,
                "T": tcode_raw,
                "wire": wire,
                "repeated": bool(f.group(5)),
                "optional": bool(f.group(6)),
            }
            if kind == "enum" and enum_var:
                entry["enum"] = enums.get(enum_var, {})
            fields.append(entry)
        msgs[var] = {"name": name, "fields": fields}
    return msgs


def get_query_params(src: str, var: str, method: str) -> list[str]:
    """For GET endpoints, recover query keys passed at call sites."""
    if method != "GET":
        return []
    keys: list[str] = []
    for m in re.finditer(r'\bK\(' + re.escape(var) + r'\b', src):
        pre = src[max(0, m.start() - 260):m.start()]
        for om in re.finditer(r'\{([^{}]{0,200})\}', pre):
            km = re.match(r'\s*([A-Za-z_$][\w$]*)\s*:', om.group(1))
            if km:
                keys.append(km.group(1))
    return sorted(set(keys))


def parse_endpoints(src: str) -> list[dict]:
    """endpoint path -> {method, fn, req var, resp var, query params}.

    Call sites have the exact shape (verified Oct 2026 against the live bundle):
        await k(VAR, new REQ(n), RESP, e)   POST
        await K(VAR, n, RESP, e)            GET  (query keys unrecoverable, see below)
    """
    var_of = dict(re.findall(r'([\w$]+)="(/svc/[a-zA-Z0-9/_-]+)"', src))
    rows: dict[str, dict] = {}
    for m in re.finditer(r'\b([Kk])\(([\w$]+),new ([\w$]+)\(\w+\),([\w$]+),\w+\)', src):
        method = "GET" if m.group(1) == "K" else "POST"
        var, req, resp = m.group(2), m.group(3), m.group(4)
        path = var_of.get(var)
        if not path:
            continue
        pre = src[max(0, m.start() - 140):m.start()]
        fns = re.findall(r'async function ([\w$]+)\(', pre)
        fn = fns[-1] if fns else "?"
        rows.setdefault(path, {"path": path, "method": method, "fn": fn,
                               "req": req, "resp": resp,
                               "query": get_query_params(src, var, method)})
    # GET sites carry no request constructor; match them separately.
    for m in re.finditer(r'\bK\(([\w$]+),\w+,([\w$]+),\w+\)', src):
        var, resp = m.group(1), m.group(2)
        path = var_of.get(var)
        if not path or path in rows:
            continue
        pre = src[max(0, m.start() - 140):m.start()]
        fns = re.findall(r'async function ([\w$]+)\(', pre)
        fn = fns[-1] if fns else "?"
        rows.setdefault(path, {"path": path, "method": "GET", "fn": fn,
                               "req": "", "resp": resp,
                               "query": get_query_params(src, var, "GET")})
    return sorted(rows.values(), key=lambda r: r["path"])


# The bundle is minified: message *type names* are gone, but each message is
# referenced by a unique minified var and (for most) exactly one endpoint.
# These names are ours, assigned from the endpoint path + role. They are the
# stable public identifiers; SCHEMA keys stay the minified vars.
def semantic_names(msgs: dict, eps: list[dict]) -> dict[str, str]:
    """minified var -> CamelCase name derived from its endpoint."""
    counts: dict[str, list[tuple[str, str]]] = {}
    for e in eps:
        for role, var in (("Request", e["req"]), ("Response", e["resp"])):
            if var:
                counts.setdefault(var, []).append((e["path"], role))

    # An endpoint's corrected response may be a different message from the
    # call-site regex's apparent response. Reserve the endpoint-derived name
    # for that authoritative message, even if the wrong inferred message is
    # still referenced elsewhere.
    forced_names: dict[str, str] = {}
    for path, var in ENDPOINT_RESPONSE_OVERRIDES.items():
        if var and var in msgs:
            parts = [p for p in path.split("/") if p and p != "svc"]
            words = [w for part in parts for w in re.split(r"[-_]", part) if w]
            forced_names[var] = "".join(w[0].upper() + w[1:] for w in words) + "Response"

    out: dict[str, str] = {}
    out.update(forced_names)
    # Prefer a real localName when the bundle preserved one.
    for var, m in msgs.items():
        nm = m["name"]
        if nm and not re.fullmatch(r"\w", nm) and nm not in {v["name"] for v in msgs.values()}:
            pass  # uniqueness handled below
    for var, m in msgs.items():
        nm = m["name"]
        if nm and len(nm) > 2 and not re.fullmatch(r"[A-Za-z_$][\w$]*", nm):
            out[var] = nm

    for var, uses in sorted(counts.items()):
        if var in out or len(uses) != 1:
            continue
        path, role = uses[0]
        parts = [p for p in path.split("/") if p and p != "svc"]
        # split-hyphen into words so "list-mine" -> "ListMine"
        words: list[str] = []
        for p in parts:
            words.extend(w for w in re.split(r"[-_]", p) if w)
        stem = "".join(w[0].upper() + w[1:] for w in words)
        out[var] = stem + role

    # second pass: name nested messages after their (already named) parent,
    # BFS so grandchildren resolve too. Tie-break on minified var order so the
    # result is deterministic across regenerations.
    referenced: dict[str, list[tuple[str, str]]] = {}
    for var, m in msgs.items():
        for f in m["fields"]:
            if f["type"] == "message" and re.fullmatch(r"[\w$]+", str(f["T"])):
                referenced.setdefault(f["T"], []).append((var, f["name"]))

    def pascal(text: str) -> str:
        return "".join(w[0].upper() + w[1:] for w in re.split(r"[_\s]+", text) if w)

    for _ in range(4):
        progress = False
        for var, uses in sorted(referenced.items()):
            if var in out or len(uses) != 1:
                continue
            parent, fname = uses[0]
            pname = out.get(parent)
            if pname:
                out[var] = pname + pascal(fname)
                progress = True
        if not progress:
            break

    # last resort: any still-unnamed message gets its minified var as a title
    for var in sorted(msgs):
        out.setdefault(var, var)

    # Disambiguate: two minified vars must never share a name, otherwise one
    # would overwrite the other in SCHEMA. Suffix duplicates with the var.
    seen: dict[str, str] = {}
    for var in sorted(out):
        name = out[var]
        if name in seen:
            out[var] = f"{name}__{var}"
        else:
            seen[name] = var
    return out


HEADER = '''"""GENERATED by tools/generate_schema.py - do not edit by hand.

Recovered protobuf schema for AnkiWeb's `/svc/*` HTTP API. AnkiWeb exposes no
public API; this is reconstructed from the SvelteKit frontend bundle that the
site itself uses (protobuf-es `makeMessageType` definitions).

Field numbers and types here are authoritative *as of generation time*. If
AnkiWeb ships a breaking change, regenerate rather than patch.

Usage:
    from ankiweb_schema import SCHEMA, ENDPOINTS, encode, decode

    req = encode("LoginRequest", username="me", password="pw")
    data = decode("LoginResponse", raw_bytes)
"""

from __future__ import annotations

GENERATED = True
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", help="path to frontend chunk (skips download)")
    ap.add_argument("--json", help="also write raw schema JSON here")
    args = ap.parse_args()

    if args.bundle:
        src = Path(args.bundle).read_text(encoding="utf-8", errors="replace")
    else:
        src = discover_bundle()

    enums = parse_enums(src)
    msgs = parse_messages(src, enums)
    eps = apply_aliases(parse_endpoints(src), msgs)
    if len(msgs) < 50 or len(eps) < 20:
        print(f"WARNING: only {len(msgs)} messages / {len(eps)} endpoints parsed",
              file=sys.stderr)

    names = semantic_names(msgs, eps)
    # Rewrite SCHEMA so keys are semantic names; message-typed field "T" refs
    # are rewritten to match, so the codec can resolve nested types by name.
    unresolved: set[str] = set()
    schema: dict[str, dict] = {}

    def resolve(var: str) -> str:
        return names.get(var, var)

    for var, m in msgs.items():
        fields = []
        for f in m["fields"]:
            g = dict(f)
            if g["type"] == "message":
                g["T"] = resolve(str(f["T"]))
                if g["T"] not in msgs:
                    unresolved.add(var)
            fields.append(g)
        key = resolve(var)
        schema[key] = {"name": key, "minified": var, "fields": fields}

    named_eps = []
    for e in eps:
        ne = dict(e)
        ne["request"] = resolve(e["req"]) if e["req"] else None
        ne["response"] = resolve(e["resp"]) if e["resp"] else None
        named_eps.append(ne)

    lines = [HEADER]
    lines.append("\n# message name -> {name, minified, fields[no,name,type,repeated,optional]}\n")
    lines.append("SCHEMA: dict[str, dict] = " + repr(schema) + "\n")
    lines.append("\n# All discovered endpoints. `query` holds GET query keys.\n")
    lines.append("ENDPOINTS: list[dict] = " + repr(named_eps) + "\n")
    lines.append('''
def schema_of(name: str) -> dict:
    return SCHEMA[name]


def has_message(name: str) -> bool:
    return name in SCHEMA


def endpoint(path: str) -> dict | None:
    for e in ENDPOINTS:
        if e["path"] == path:
            return e
    return None


def public_endpoints() -> list[dict]:
    """Endpoints a normal user account can call (excludes /svc/radmin/*)."""
    return [e for e in ENDPOINTS if "/radmin/" not in e["path"]]
''')
    OUT.write_text("\n".join(lines), encoding="utf-8")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"messages": msgs, "endpoints": named_eps, "names": names},
                       indent=1), encoding="utf-8"
        )

    admin = [e for e in eps if "/radmin/" in e["path"]]
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  messages: {len(msgs)} (named {len(names)})")
    print(f"  endpoints: {len(eps)} ({len(eps) - len(admin)} non-admin, {len(admin)} radmin)")
    if unresolved:
        print(f"  WARNING: {len(unresolved)} messages reference unnamed submessages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
