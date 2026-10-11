# AnkiWeb API — wiki

Documentation for [`athulkrishna2015/ankiweb-api`](https://github.com/athulkrishna2015/ankiweb-api):
a full Python client for AnkiWeb's reverse-engineered `/svc/*` API, plus tools to
inspect, download and upload [Anki](https://apps.ankiweb.net/) add-ons.

AnkiWeb ships no official API. Everything here is recovered from the site's own
frontend bundle, so it may change without notice — treat it as unofficial and
subject to AnkiWeb's terms and rate limits.

## Pages

| Page                         | Contents                                                                                                                                                    |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [API.md](API.md)             | Client reference: installation, authentication, all 46 public methods, error handling, the codec, upload verification, and the description/caching gotchas. |
| [ENDPOINTS.md](ENDPOINTS.md) | All 41 public `/svc/*` endpoints with every request field, response field and enum, grouped by area.                                                        |

## Quick start

```sh
uv tool install ankiweb-api
ankiweb info 805854302
```

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient()      # reads .env (ANKIWEB_USERNAME / ANKIWEB_PASSWORD)
client.login()

for item in client.shared_list_mine()["items"]:
    print(item["id"], item["title"])
```

## At a glance

- **41/41 public endpoints** as typed methods — account, decks, editor, search,
  shared, study. The 22 `/svc/radmin/*` admin endpoints are decoded but
  deliberately not exposed; they are listed as
  [reference only](ENDPOINTS.md#admin-endpoints-reference-only-not-callable).
- **Schema revision 2026-10-10**, 174 messages, regenerated from AnkiWeb's live
  bundle by `tools/generate_schema.py`.
- **Pure stdlib codec** — `requests` is the only runtime dependency.

## Things worth knowing

- **Descriptions cap at 65,535 bytes.** Over that the upload is _rejected_, not
  truncated, and the add-on keeps its old description — so it looks like a
  silent wipe. See [API.md](API.md#description-limits-and-stale-reads).
- **`item-info` is cached for 10 minutes.** Reads go out with a `cb`
  cache-buster; `ankiweb info` prints a `verify:` link that bypasses the cache.
- **Uploads are irreversible.** An upload replaces the file on the target add-on
  id. Test with the synthetic fixture from `make_test_addon.py`, never a real
  add-on.

## Outside the wiki

- [Repository README](https://github.com/athulkrishna2015/ankiweb-api) — CLI,
  GitHub Action, installation
- [PyPI](https://pypi.org/project/ankiweb-api/) — `uv tool install ankiweb-api`
- [Issues](https://github.com/athulkrishna2015/ankiweb-api/issues)
