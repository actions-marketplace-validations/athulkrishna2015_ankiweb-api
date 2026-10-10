# AnkiWeb API client

This project includes an experimental Python client for the protobuf-based
`/svc/*` endpoints used by AnkiWeb's web frontend. There is no official,
supported public AnkiWeb API. These endpoints and their wire schemas are
reverse-engineered, may change without notice, and may be subject to AnkiWeb's
terms and rate limits. Use only with an account and data you are authorized to
access. `/svc/radmin/*` administrative endpoints are deliberately excluded.

## Installation and basic use

Install `requests` from `requirements-terminal.txt`. The client supports a
pre-existing session cookie, and login credential acquisition through the
existing `ankiweb_auth` helper:

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient(cookie="your-session-cookie")
mine = client.shared_list_mine(request={})
print(mine)

# Public endpoint; GET arguments are query-string values.
item = client.shared_item_info(query={"sharedId": 2055492159})
print(item)
```

Endpoint methods are generated lazily from `ankiweb_schema.ENDPOINTS`. Their
Python names combine the final path segments with underscores (for example,
`shared_list_mine`, `shared_item_info`, `account_login`). For POST methods with
a request message, pass `request={...}` using the field names in the schema.
For GET endpoints pass `query={...}`. `response_as=` is a low-level escape
hatch for selecting a known response schema when the endpoint's response type
has not been identified.

## Current scope and limitations

- `ankiweb_schema.py` currently contains 174 recovered messages and 62
  discovered endpoints: 41 normal-user endpoints and 21 `/svc/radmin/*`
  endpoints. `public_endpoints()` excludes admin endpoints.
- Some endpoints have unresolved response mappings or nested message
  references. A `None` response mapping returns the raw response from the
  client; it does not imply the endpoint is fully understood.
- `ankiweb_client.py` is a generic transport, not a curated stable API. Check
  field names and required values in `SCHEMA` before calling an endpoint.
- Login and account actions can have effects. Prefer public/read-only methods
  and synthetic/offline fixtures during development. Do not use a real
  `.ankiaddon` for upload tests; follow the repository's synthetic-fixture
  instructions in the README.

## Schema regeneration

The generator extracts protobuf message declarations and call sites from the
frontend bundle. It can discover a current bundle or consume a local file:

```sh
python3 tools/generate_schema.py
python3 tools/generate_schema.py --bundle /path/to/frontend.mjs --json /tmp/ankiweb-schema.json
```

Review generated diffs before accepting them. Minification and bundle changes
can confuse endpoint association; known corrections are maintained in
`ENDPOINT_RESPONSE_OVERRIDES` and `SHARED_RESPONSE_ALIASES` in
`tools/generate_schema.py`. A generator warning about unnamed nested messages
means some field references still need investigation.

## Codec

`ankiweb_proto.py` provides `encode(message_name, mapping)` and
`decode(message_name, bytes)`. The codec supports scalar, repeated, nested,
packed, and optional fields represented in the extracted schema, and retains
unknown fields for round-tripping. It is a focused implementation for this
schema, not a general-purpose protobuf library. Offline regression tests:

```sh
python3 -m unittest -v test_ankiweb_proto.py
python3 test_terminal_ankiweb.py
```
