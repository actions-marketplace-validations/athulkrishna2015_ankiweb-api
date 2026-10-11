# AnkiWeb API client

Full Python client for AnkiWeb's protobuf-based `/svc/*` endpoints — the same
wire protocol the AnkiWeb web frontend uses. There is no official, supported
public AnkiWeb API: endpoints and schemas here are reverse-engineered, may
change without notice, and are subject to AnkiWeb's terms and rate limits. Use
only with an account and data you are authorized to access.
`/svc/radmin/*` administrative endpoints are decoded in the schema but
intentionally not exposed on the client.

**Coverage: 41/41 public endpoints** as typed `AnkiWebClient` methods, plus a
complete field-level reference in [ENDPOINTS.md](ENDPOINTS.md). Schema revision
2026-10-10 (174 messages; all request/response/nested names resolve).

> CLI usage, installation and the GitHub Action live in the
> [README](../README.md). Jump to:
> [install](#installation) · [authentication](#authentication) ·
> [method reference](#method-reference) · [errors](#errors-and-status-codes) ·
> [escape hatch](#generic-escape-hatch) · [schema](#schema-regeneration) ·
> [codec](#codec) · [upload](#upload-verification) ·
> [limits & caching](#description-limits-and-stale-reads) · [testing](#testing)

## Contents

- [Installation](#installation)
- [Authentication](#authentication)
- [Method reference](#method-reference) — [session](#session-5) ·
  [account](#account-12) · [decks](#decks-8) · [editor](#editor-3) ·
  [search](#search-1) · [shared](#shared-12) · [study](#study-4)
- [Errors and status codes](#errors-and-status-codes)
- [Generic escape hatch](#generic-escape-hatch)
- [Schema regeneration](#schema-regeneration)
- [Codec](#codec)
- [Upload verification](#upload-verification)
- [Description limits and stale reads](#description-limits-and-stale-reads)
- [Testing](#testing)

## Installation

```sh
uv tool install ankiweb-api          # provides: ankiweb, ankiweb-upload, ankiweb-test-addon
# or
pipx install ankiweb-api
```

As a library, the only runtime dependency is `requests`:

```sh
uv pip install requests          # or: pip install requests
```

Put credentials in `./.env` (gitignored — never commit it):

```dotenv
ANKIWEB_USERNAME=you@example.com
ANKIWEB_PASSWORD=...
```

`AnkiWebClient()` auto-loads `.env` from the current directory, falling back to
the directory holding the installed module. Exported environment variables win,
and `username=` / `password=` override both.

## Authentication

Authentication is a single `ankiweb` session cookie obtained from
`POST /svc/account/login`. The client attaches it automatically and re-logs in on
demand, so most callers never handle cookies.

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient()                 # reads .env
client.login()                           # caches the session cookie
client.is_authenticated()                # -> True

# Or reuse an existing cookie from another tool:
client = AnkiWebClient(cookie="eyJvcCI6...")
```

`logout()` drops the cached cookie. If AnkiWeb expires the session, the next
call raises `AnkiWebError("Session expired or invalid credentials")` and clears
the cookie; calling `login()` again recovers.

### Endpoints that need no session

These are safe to call unauthenticated, and the client will **not** trigger a
login for them:

| Endpoint                           | Method |
| ---------------------------------- | ------ |
| `/svc/account/login`               | POST   |
| `/svc/account/signup`              | POST   |
| `/svc/account/get-account-status`  | POST   |
| `/svc/account/reset-password`      | POST   |
| `/svc/account/resend-verification` | POST   |
| `/svc/account/verify-email`        | POST   |
| `/svc/shared/item-info`            | GET    |
| `/svc/shared/list-addons`          | GET    |
| `/svc/shared/list-decks`           | GET    |

Everything else sends `Cookie: has_auth=1; ankiweb=<session>`.

## Method reference

Method names mirror the path: `/svc/shared/list-mine` → `shared_list_mine`.
POST methods take keyword arguments matching the request fields; GET methods
take `shared_id=` or `query={...}`. Field-level detail for every request and
response is in [ENDPOINTS.md](ENDPOINTS.md).

`auth` below means the call requires a session cookie.

### Session (5)

| Method                                | auth | Returns                                         |
| ------------------------------------- | ---- | ----------------------------------------------- |
| `login(username=None, password=None)` | —    | the session cookie (`str`)                      |
| `logout()`                            | —    | `None`                                          |
| `is_authenticated()`                  | —    | `bool`                                          |
| `list_mine()`                         | yes  | alias of `shared_list_mine()`                   |
| `item_info(addon_id)`                 | no   | alias of `shared_item_info(shared_id=addon_id)` |

### Account (12)

| Method                                                                        | auth | Returns                                      |
| ----------------------------------------------------------------------------- | ---- | -------------------------------------------- |
| `account_login(username, password)`                                           | no   | `{status, token}`                            |
| `account_signup(username, password)`                                          | no   | `{status, ankiuser_login_token?}`            |
| `account_get_account_status()`                                                | no   | `{logged_in, redirect_to?}`                  |
| `account_reset_password(email_to='', check_token='', new_password=None)`      | no   | `{send_email, token_ok, set_new_password}`   |
| `account_resend_verification(hkey='')`                                        | no   | `{throttled}`                                |
| `account_verify_email(token='')`                                              | no   | `{token_verified, sending_status{...}}`      |
| `account_check_terms()`                                                       | yes  | `{needs_to_confirm}`                         |
| `account_confirm_terms(agree_to_terms=True)`                                  | yes  | empty                                        |
| `account_get_settings()`                                                      | yes  | `{current_email}`                            |
| `account_update_settings(current_password='', new_password='', new_email='')` | yes  | `{result}` enum                              |
| `account_total_media()`                                                       | yes  | `{total_bytes}`                              |
| `account_remove_account(current_password)`                                    | yes  | `{status, media_removed}` — **irreversible** |

### Decks (8)

| Method                                               | auth | Returns                                                                |
| ---------------------------------------------------- | ---- | ---------------------------------------------------------------------- |
| `decks_create_deck(name)`                            | yes  | empty                                                                  |
| `decks_deck_list_info(minutes_west_of_utc=None)`     | yes  | `{top_node, current_deck_id, collection_size_bytes, media_size_bytes}` |
| `decks_deck_share_info(deck_id)`                     | yes  | `{metadata, is_large_user, share_count}`                               |
| `decks_deck_share(metadata, confirm_copyright=True)` | yes  | empty                                                                  |
| `decks_deck_share_state()`                           | yes  | `{state, shared_id?}`                                                  |
| `decks_rename_deck(deck_id, new_name)`               | yes  | `{error}`                                                              |
| `decks_remove_deck(deck_id)`                         | yes  | empty                                                                  |
| `decks_select_deck(deck_id)`                         | yes  | empty                                                                  |

### Editor (3)

| Method                                    | auth | Returns                                        |
| ----------------------------------------- | ---- | ---------------------------------------------- |
| `editor_get_info_for_adding()`            | yes  | `{notetypes[], decks[], current_deck_id, ...}` |
| `editor_get_note_info(note_id)`           | yes  | `{fields[], notetype_fields[], tags}`          |
| `editor_get_notetype_fields(notetype_id)` | yes  | `{fields[]}`                                   |

`editor_add_or_update(request)` also lives in this area but takes the **full
request mapping** (nested `fields`, `current_notetype_id`, `audio`, `video`,
`picture`) rather than keyword arguments — see
`SCHEMA["EditorAddOrUpdateRequest"]` and [ENDPOINTS.md](ENDPOINTS.md).

### Search (1)

| Method                  | auth | Returns                                            |
| ----------------------- | ---- | -------------------------------------------------- |
| `search_search(search)` | yes  | `{notes[{note_id, sorted_field_names...}], error}` |

`search` uses Anki's own query language, e.g. `deck:My\ Deck added:7`.

### Shared (12)

| Method                                          | auth | Returns                                                                                                                  |
| ----------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------ |
| `shared_item_info(shared_id=None, query=None)`  | no   | `{available{title, tags, description, size, last_updated, support_url, addon{versions[]}, ...}, missing, access_denied}` |
| `shared_list_addons()`                          | no   | `{rows[], user_upload_status}`                                                                                           |
| `shared_list_decks()`                           | no   | `{rows[]}`                                                                                                               |
| `shared_items_by_author(shared_id)`             | yes  | `{items[{shared_id, title}]}`                                                                                            |
| `shared_get_addon_info(addon_id)`               | yes  | `{addon{title, tags, support_url, description, branches[]}}`                                                             |
| `shared_list_mine()`                            | yes  | `{items[], reviews[], expired_decks[]}`                                                                                  |
| `shared_upload_addon(info, file=None)`          | yes  | `{addon_id}`                                                                                                             |
| `shared_remove_item(shared_id)`                 | yes  | empty — **deletes the shared item**                                                                                      |
| `shared_get_own_review(shared_id)`              | yes  | `{review{body, thumbs_up}, shared_item_title, support_page?}`                                                            |
| `shared_set_own_review(shared_id, review)`      | yes  | empty; `review={body, thumbs_up}`                                                                                        |
| `shared_reply_to_review(shared_id, hash, body)` | yes  | empty                                                                                                                    |
| `shared_report_copyright(shared_id)`            | yes  | empty                                                                                                                    |

`shared_upload_addon` takes the nested `info` mapping directly, e.g.:

```python
client.shared_upload_addon(
    info={
        "addon_id": 805854302,          # omit to create a new add-on
        "title": "My add-on",
        "tags": "anki addon",
        "support_url": "https://github.com/athulkrishna2015/ankiweb-api",
        "description": "Markdown is supported.",
        "branches": [{"min_version": 1, "max_version": 250904}],
    },
    file={"zip_data": Path("my.ankiaddon").read_bytes(), "branch_index": 0},
)
```

Prefer `upload.py` / `ankiweb-upload` for uploads — it wraps this endpoint with
branch-notation parsing and the action's own `INPUT_*` mapping. See
[Upload verification](#upload-verification) and the [README](../README.md#upload).

### Study (4)

| Method                                                                    | auth | Returns                                                      |
| ------------------------------------------------------------------------- | ---- | ------------------------------------------------------------ |
| `study_get_deck_limits()`                                                 | yes  | `{new, review, new_cards_ignore_review_limit, error}`        |
| `study_set_deck_limits(new, review, new_cards_ignore_review_limit=False)` | yes  | empty                                                        |
| `study_study_cards(answer=None, next_card_id=None)`                       | yes  | `{sched_ver, cards[], new_count, learn_count, review_count}` |
| `study_upgrade_scheduler(v3=True)`                                        | yes  | empty                                                        |

## Errors and status codes

| Exception         | Module                               | Raised when                                                                   |
| ----------------- | ------------------------------------ | ----------------------------------------------------------------------------- |
| `AnkiWebError`    | `ankiweb_client`, `terminal_ankiweb` | any non-2xx response, network failure, or decode failure                      |
| `NotFoundError`   | `ankiweb_client`, `terminal_ankiweb` | HTTP 404, or a 200 with an empty payload (wrong/private id)                   |
| `ValidationError` | `ankiweb_client`                     | a required request object is missing, or a request field is not in the schema |
| `AuthError`       | `ankiweb_auth`                       | login failed or returned no `ankiweb` cookie                                  |
| `ProtoError`      | `ankiweb_proto`                      | malformed protobuf input                                                      |

`AnkiWebError` is the base for `NotFoundError`, so catching the base class is
enough. The client's status handling is:

| Status        | Behaviour                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------ |
| `200`         | decoded via the endpoint's response message                                                |
| `401`, `403`  | clears the cached cookie, raises `AnkiWebError` ("Session expired or invalid credentials") |
| `404`         | raises `NotFoundError`                                                                     |
| anything else | raises `AnkiWebError` with the status and a truncated body                                 |

AnkiWeb reports some failures in the **body**, not the status — e.g. uploading
an add-on whose title is already taken returns HTTP 400 with
`title must be unique`. Always read the exception message.

## Generic escape hatch

Any public endpoint is also reachable by method name without a typed wrapper,
which is useful while exploring or when the schema gains a field the wrapper does
not expose yet:

```python
client.shared_list_mine()                       # typed
client.call("shared_list_mine")                 # dynamic, same call
client.editor_add_or_update(request={...})      # typed, full request mapping
```

`call` accepts `request=` for POST bodies, `query=` for GET parameters, and
`response_as=` to force a specific response message when a shared variable made
the generator's inference ambiguous.

From the terminal the same escape hatch is exposed as `ankicli.py call`:

```sh
ankiweb endpoints                                        # list all 41
ankiweb call shared_item_info --query sharedId=2055492159
ankiweb call decks_create_deck --request '{"name": "New Deck"}'
```

## Safety

- Read-only/public methods (`shared_item_info`, `shared_list_addons`,
  `shared_list_decks`, `shared_list_mine`, ...) are safe to explore.
- Account actions (`update_settings`, `account_remove_account`, `decks_deck_share`,
  `shared_remove_item`, `shared_upload_addon`, ...) have real effects. Prefer
  synthetic or offline fixtures during development. **Never test uploads with a
  real add-on file** — an upload replaces the file on AnkiWeb irreversibly;
  follow the synthetic-fixture instructions in the [README](../README.md#upload).
- `/svc/radmin/*` endpoints are decoded but deliberately not exposed.

## Schema regeneration

The generator decodes protobuf definitions and call sites from AnkiWeb's live
frontend bundle (Vite `__vite__mapDeps` discovery + precise
`k(VAR,new REQ(n),RESP,e)` call-site parsing). Refresh with:

```sh
python3 tools/generate_schema.py                      # download + regenerate
python3 tools/generate_schema.py --bundle /path/to/frontend.mjs
python3 tools/generate_schema.py --json out.json      # also dump raw decode
```

Review generated diffs before accepting them. `tools/generate_schema.py` keeps
`SHARED_RESPONSE_ALIASES` (verified response-var corrections) and a pinned
`ENDPOINT_RESPONSE_OVERRIDES` sanity entry for login. While the live test passes,
regeneration is byte-for-byte stable — see [Testing](#testing).

## Codec

`ankiweb_proto.py` provides `encode(message_name, mapping)` and
`decode(message_name, bytes)` — pure stdlib, no protobuf dependency. Supports
scalar, repeated (packed/unpacked), nested, optional and map fields, and
retains unknown fields for round-tripping.

```python
from ankiweb_proto import encode, decode
from ankiweb_schema import SCHEMA

encode("AccountLoginRequest", username="me", password="pw")
decode("AccountLoginResponse", raw_bytes)     # -> {'status': 1, 'token': '...'}
```

Offline regression tests:

```sh
python3 -m unittest -v test_ankiweb_proto.py
```

## Upload verification

The GitHub Actions upload path (`node dist/index.js`, wrapped locally by
`upload.py`) is verified live against the private throwaway add-on 805854302
(saved as `ANKIWEB_TEST_ADDON_ID` in the gitignored `.env`): upload a synthetic
fixture from `make_test_addon.py`, confirm the new description/timestamp via
`ankicli.py info`, and confirm the re-downloaded bytes are sha256-identical to
the upload. The same path is covered on real runners by the CI `test-action` job
(run `38121891143`, green). See the [README](../README.md#tests) for the exact
commands and latest verified snapshot.

## Description limits and stale reads

Two AnkiWeb behaviours that look like data loss but are not. Both are handled in
this client; neither is a server bug you can work around by changing the
uploader.

**Size limit: 65,535 bytes.** Measured 2026-10-11 on the throwaway add-on by
bisection: 65,535 stores, 65,536 does not. An over-limit upload is _rejected_,
not truncated — the add-on keeps whatever description it already had, so a
failed large upload looks like "my new text vanished" while the old text is
still live. Verify after every large description upload.

**`item-info` is cached for 10 minutes** (`Cache-Control: max-age=600`). Reads of
a stable URL can therefore return pre-upload state, which again looks like a
silent wipe. `fetch_item_info_raw` sends the same cache-buster AnkiWeb's own
frontend uses — `cb=<Date.now()>` in epoch milliseconds, from its `cacheBust`
helper — plus `Cache-Control: no-cache`, and surfaces the value as
`info["cache_bust"]` so `ankicli.py info` can print a `verify:` URL that matches
the data it just read:

```sh
./ankicli.py info 805854302
# ...
# verify:   https://ankiweb.net/shared/info/805854302?cb=1791710745423
```

Without the `cb` query the browser will happily show you stale data for up to ten
minutes.

`_next_cache_bust()` is strictly monotonic rather than a bare `Date.now()`: two
reads inside the same millisecond would otherwise produce the same URL, and the
second could be served the first one's cached copy.

> **Note**
> `AnkiWebClient.shared_item_info()` does not cache-bust — it is the raw client.
> For description reads that must reflect a recent upload, use
> `terminal_ankiweb.fetch_item_info()`, which is what the CLI and the test suite
> use.

## Testing

```sh
python3 test_terminal_ankiweb.py          # offline, no network
python3 test_terminal_ankiweb.py --live   # + live round-trips + API discovery
python3 -m unittest -v test_ankiweb_proto.py   # codec and schema regressions
pnpm test                                # GitHub Action unit tests (mocked)
```

### Testing against a cache

Any test that reads live `item-info` must go through `fetch_item_info()` rather
than building a URL by hand. A stable URL means the assertions may silently run
against pre-upload state. The live suite checks this explicitly:

```sh
python3 test_terminal_ankiweb.py --live
```

- consecutive reads must carry **different** cache-busters and agree on content
- a long (>20,000 char) description must survive the round-trip — this is the
  regression guard for the 5,000-byte parser cap that made uploads look wiped
- the live bundle is re-discovered and diffed against the committed schema, so
  new or removed endpoints fail loudly instead of drifting

While this passes, `python3 tools/generate_schema.py` rewrites
`ankiweb_schema.py` byte-for-byte.
