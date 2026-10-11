# AnkiWeb API client

Full Python client for AnkiWeb's protobuf-based `/svc/*` endpoints — the same
wire protocol the AnkiWeb web frontend uses. There is no official, supported
public AnkiWeb API: endpoints and schemas here are reverse-engineered, may
change without notice, and are subject to AnkiWeb's terms and rate limits. Use
only with an account and data you are authorized to access.
`/svc/radmin/*` administrative endpoints are decoded in the schema but
intentionally not exposed on the client.

**Coverage: 41/41 public endpoints** as typed `AnkiWebClient` methods, plus a
complete reference in [ENDPOINTS.md](ENDPOINTS.md). Schema revision 2026-10-10
(174 messages; all request/response/nested names resolve).

## Installation and basic use

Install `requests` from `requirements-terminal.txt`. Pass a session cookie, or
configure credentials and call `login()` (`.env` is auto-loaded):

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient(cookie="your-session-cookie")
print(client.shared_list_mine()["items"])

# Alternatively, after setting ANKIWEB_USERNAME and ANKIWEB_PASSWORD:
client = AnkiWebClient()
client.login()
print(client.shared_list_mine()["items"])

# Public endpoint (no auth needed):
item = client.shared_item_info(shared_id=2055492159)
print(item["available"]["title"])
```

Method names are `<area>_<action>` (`shared_list_mine`, `shared_item_info`,
`account_login`, ...). Legacy aliases `login`, `list_mine`, `item_info` still
work. Any other public endpoint is also reachable via the generic fallback
`client.<area>_<action>(request={...}, query={...})`.

POST methods take keyword arguments matching the request fields (see
[ENDPOINTS.md](ENDPOINTS.md)); `editor_add_or_update(request)` takes the full
request mapping. GET methods take `shared_id=` or `query={...}`.

## Safety

- Read-only/public methods (`shared_item_info`, `shared_list_addons`,
  `shared_list_decks`, `shared_list_mine`, ...) are safe to explore.
- Account actions (`update-settings`, `remove-account`, `deck-share`,
  `remove-item`, `upload-addon`, ...) have real effects. Prefer synthetic or
  offline fixtures during development. **Never test uploads with a real add-on
  file** — an upload replaces the file on AnkiWeb irreversibly; follow the
  synthetic-fixture instructions in the README.

## Schema regeneration

The generator decodes protobuf definitions and call sites from AnkiWeb's live
frontend bundle (Vite `__vite__mapDeps` discovery + precise
`k(VAR,new REQ(n),RESP,e)` call-site parsing). Refresh with:

```sh
python3 tools/generate_schema.py                      # download + regenerate
python3 tools/generate_schema.py --bundle /path/to/frontend.mjs
```

Review generated diffs before accepting them. `tools/generate_schema.py` keeps
`SHARED_RESPONSE_ALIASES` (verified response-var corrections) and a pinned
`ENDPOINT_RESPONSE_OVERRIDES` sanity entry for login.

## Codec

`ankiweb_proto.py` provides `encode(message_name, mapping)` and
`decode(message_name, bytes)` — pure stdlib, no protobuf dependency. Supports
scalar, repeated (packed/unpacked), nested, optional and map fields, and
retains unknown fields for round-tripping. Offline regression tests:

```sh
python3 -m unittest -v test_ankiweb_proto.py
python3 test_terminal_ankiweb.py
```

## Upload verification

The GitHub Actions upload path (`node dist/index.js`, wrapped locally by
`upload.py`) is verified live against the private throwaway add-on 805854302
(saved as `ANKIWEB_TEST_ADDON_ID` in `.env` / `.env.example`):
upload a synthetic fixture from `make_test_addon.py`, confirm the new
description/timestamp via `ankicli.py info`, and confirm the re-downloaded
bytes are sha256-identical to the upload. The same path is covered on real
runners by the CI `test-action` job (run `38121891143`, green). See the README
Tests section for the exact commands and latest verified snapshot.
