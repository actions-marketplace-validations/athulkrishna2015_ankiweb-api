# AnkiWeb API — full `/svc/*` compatibility + add-on tools

[![CI](https://github.com/athulkrishna2015/ankiweb-api/actions/workflows/ci.yml/badge.svg)](https://github.com/athulkrishna2015/ankiweb-api/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ankiweb-api.svg)](https://pypi.org/project/ankiweb-api/)
[![Python](https://img.shields.io/pypi/pyversions/ankiweb-api.svg)](https://pypi.org/project/ankiweb-api/)

A complete Python client for AnkiWeb's reverse-engineered `/svc/*` API —
**all 41 public endpoints** as typed `AnkiWebClient` methods — plus tools to
inspect, download, and upload [Anki](https://apps.ankiweb.net/) add-ons from
your terminal or GitHub Actions.

> Fork of [danny900714/upload-anki-addon](https://github.com/danny900714/upload-anki-addon) (`upstream/main` remote).
> The Node upload engine (`dist/index.js`) is unmodified upstream code. This repository adds terminal tooling and a full schema-driven API client decoded from AnkiWeb's own frontend bundle.

## Features

- **Full API coverage**: All 41 public `/svc/*` endpoints as typed methods
  ([reference](docs/ENDPOINTS.md)) — account, decks, editor, search, shared,
  study — decoded from AnkiWeb's own frontend bundle, verified live.
- **Multiple branches**: Upload different add-on files targeting different Anki version ranges.
- **Description file**: Use a separate file for the add-on description, making it easier to edit and format.
- **Terminal CLI**: Upload, inspect, download, and call any endpoint (`ankicli.py call ...`) without GitHub Actions.
- **Metadata-only updates**: Change title/description/tags without re-uploading the `.ankiaddon`.
- **Installable**: [`uv tool install ankiweb-api`](https://pypi.org/project/ankiweb-api/) — see [setup](#setup).

> [!CAUTION]
> These call AnkiWeb's reverse-engineered, unofficial API. Read the
> [safety notes](docs/API.md#safety) before pointing it at anything real.

## Table of contents

- [Documentation](#documentation)
- [Python API client](#python-api-client-full-svc-coverage) — [quick start](#quick-start) · [endpoint reference](docs/ENDPOINTS.md)
- [Terminal usage](#terminal-usage) — [setup](#setup) · [upload](#upload) · [info](#info-add-on-metadata) · [download](#download-ankiaddon) · [notes](#terminal-notes)
- [List your own shared items](#list-your-own-shared-items)
- [Tests](#tests)
- [GitHub Actions usage](#github-actions-usage) — [inputs](#inputs) · [outputs](#outputs)

## Documentation

Two deeper references live in [`docs/`](docs/):

| Doc                                    | What it covers                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [docs/Home.md](docs/Home.md)           | Wiki landing page and quick-start                                                                                                                                                                                                                                                                                                                                                 |
| [docs/API.md](docs/API.md)             | Client reference: [install](docs/API.md#installation), [authentication](docs/API.md#authentication), all [46 public methods](docs/API.md#method-reference), [errors](docs/API.md#errors-and-status-codes), [codec](docs/API.md#codec), [upload verification](docs/API.md#upload-verification), [description limits & stale reads](docs/API.md#description-limits-and-stale-reads) |
| [docs/ENDPOINTS.md](docs/ENDPOINTS.md) | All [41 endpoints](docs/ENDPOINTS.md#quick-start) with every field and enum — [account](docs/ENDPOINTS.md#account-12), [decks](docs/ENDPOINTS.md#decks-8), [editor & search](docs/ENDPOINTS.md#editor-and-search-4), [shared](docs/ENDPOINTS.md#shared-public-reads-5-no-auth), [study](docs/ENDPOINTS.md#study-4), [wire details](docs/ENDPOINTS.md#wire-details)                |

`docs/` is published to the repository wiki by
[`.github/workflows/sync-wiki.yml`](.github/workflows/sync-wiki.yml) whenever it
changes, so <https://github.com/athulkrishna2015/ankiweb-api/wiki> mirrors these pages.

## Python API client (full `/svc/*` coverage)

All **41 public endpoints** are typed methods on `AnkiWebClient` — account (12),
decks (8), editor (3), search (1), shared (12), and study (4). The wire schema
is decoded from AnkiWeb's own frontend bundle (revision `2026-10-10`, all
request/response/nested messages resolved) and verified live. Full field-level
reference: [docs/ENDPOINTS.md](docs/ENDPOINTS.md).

### Quick start

Requires Python 3.9+ with `requests` (same install as the terminal tools):

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient()          # auto-loads .env (ANKIWEB_USERNAME/PASSWORD)
client.login()

mine = client.shared_list_mine()          # your shared add-ons & decks
for item in mine["items"]:
    print(item["id"], item["title"])

# Public, no auth needed:
item = client.shared_item_info(shared_id=2055492159)
print(item["available"]["title"])

# The rest of the surface:
client.decks_create_deck("My Deck")
client.search_search("deck:My Deck")
info = client.decks_deck_list_info(minutes_west_of_utc=0)
```

Method names mirror the path (`/svc/shared/list-mine` → `shared_list_mine`).
Legacy aliases `login`, `list_mine`, and `item_info` still work.

### Any endpoint from the terminal

`ankicli.py` can call any public endpoint and print decoded JSON:

```sh
./ankicli.py endpoints                      # list all 41 with request/response types
./ankicli.py call shared_item_info --query sharedId=2055492159
./ankicli.py call shared_list_addons        # public, no auth
./ankicli.py call decks_create_deck --request '{"name": "New Deck"}'   # uses .env
```

### Keeping the schema fresh

AnkiWeb ships no official API, so the schema can change. Regenerate and review
the diff whenever something breaks:

```sh
python3 tools/generate_schema.py            # re-decode the live frontend bundle
```

Details: [docs/API.md](docs/API.md#schema-regeneration) (client usage, regeneration, codec) and
[docs/ENDPOINTS.md](docs/ENDPOINTS.md) (every endpoint, field, and enum).

## Terminal usage

Requires Python 3.9+ with `requests`, plus Node 24 if you upload (the action engine runs on Node).
`info` and `download` are Python-only and need no Node.

### Setup

Install as a command from [PyPI](https://pypi.org/project/ankiweb-api/):

```sh
uv tool install ankiweb-api         # provides: ankiweb, ankiweb-upload, ankiweb-test-addon
# or: pipx install ankiweb-api
```

Or run it straight from a checkout:

```sh
git clone https://github.com/athulkrishna2015/ankiweb-api.git
cd ankiweb-api
uv run --with requests ./ankicli.py info 805854302
```

Keep credentials in `.env` (gitignored — never commit it). The tools look for `.env` in
the current directory first, then next to the script:

```sh
cp .env.example .env
$EDITOR .env     # ANKIWEB_USERNAME=... / ANKIWEB_PASSWORD=...
```

`upload.py` reads `./.env` automatically. Exported shell variables take precedence, and
`--username` / `--password` override both. When installed as a tool, point the engine at
your own Node build with `ANKIWEB_ENGINE=/path/to/dist/index.js`.

Every example below uses the in-checkout form; the installed commands are equivalent:

| Script                 | Installed command    |
| ---------------------- | -------------------- |
| `./ankicli.py …`       | `ankiweb …`          |
| `./upload.py …`        | `ankiweb-upload …`   |
| `./make_test_addon.py` | `ankiweb-test-addon` |

> [!IMPORTANT]
> If you build the wheel yourself, send the artifacts somewhere other than `dist/` —
> that directory holds `dist/index.js`, the action's upload engine, and CI diffs it:
> `uv build --out-dir /tmp/wheel`.

#### Releasing to PyPI

Publishing uses **trusted publishing (OIDC)** — there is no API token stored anywhere.
`.github/workflows/publish.yml` builds on a tag and uploads with a short-lived token
that PyPI exchanges for an upload token.

One-time setup, once the project exists:

1. Create the project `ankiweb-api` on PyPI (under `athulkrishna2015`).
2. On that project: **Manage → Publishing → Add a pending publisher**:

   | Field             | Value              |
   | ----------------- | ------------------ |
   | PyPI project name | `ankiweb-api`      |
   | Owner             | `athulkrishna2015` |
   | Repository name   | `ankiweb-api`      |
   | Workflow name     | `publish.yml`      |

3. Publish a release — `workflow_dispatch` on that workflow, or tag a release, and it
   builds and uploads. The first successful upload activates the pending publisher;
   the name is then permanently claimed.

### Upload

Same inputs as the action, as CLI flags. `upload.py` maps them to the action's `INPUT_*`
variables and runs the upstream engine — no separate upload implementation.

> [!WARNING]
> **Never test uploads with a real add-on file.** An upload replaces the file on the target
> add-on id, and the previous version is **not** recoverable from AnkiWeb. Build the synthetic
> fixture instead and use a throwaway add-on id:
>
> ```sh
> python3 make_test_addon.py          # -> fixtures/test.ankiaddon
> ./upload.py --addon-id <test-id> --title "CLI Test" \
>     --description "test" --branches "2.1.1-2.1.1+" \
>     --addon-files fixtures/test.ankiaddon
> ```

```sh
# New add-on (omit --addon-id)
./upload.py --title "My Anki add-on" \
    --description "Description for my add-on" \
    --branches "2.1.1-25.09.4+" \
    --addon-files my-addon.ankiaddon

# Update an existing add-on, with description from a file
./upload.py --addon-id 805854302 --title "My Anki add-on" \
    --description-file DESCRIPTION.md \
    --branches "2.1.1-25.09.4+" \
    --addon-files my-addon.ankiaddon
```

**Metadata-only** — update title/description/tags with no file upload. Use `-` for the file,
the same convention the action uses:

```sh
./upload.py --addon-id 805854302 --title "My Anki add-on" \
    --description "Updated description" \
    --branches "2.1.1-2.1.1+" \
    --addon-files -
```

Useful flags:

| Flag                 | Description                                                  |
| -------------------- | ------------------------------------------------------------ |
| `--tags "a b"`       | Space-separated tags.                                        |
| `--support-page URL` | Must start with `http`.                                      |
| `--dry-run`          | Print the `INPUT_*` mapping and exit without network access. |
| `--env-file PATH`    | Use a different `.env` (default `./.env`).                   |
| `--node PATH`        | Node binary to run the engine with (default `node`).         |

Multi-branch works the same way — one branch and one file per line, in matching order:

```sh
./upload.py --addon-id 805854302 --title "My Anki add-on" --description "Desc" \
    --branches "2.1.1-2.1.66" "23.10-25.09.4+" \
    --addon-files first.ankiaddon second.ankiaddon
```

> [!IMPORTANT]
> Branch notation is `min-max`. A bare `2.1.1+` is rejected. Trailing `+` means
> "and all future versions". Reproduce an existing range by reading it first:
> `minpt`/`maxpt` from `./ankicli.py download <id> -o -` output map to it.

### List your own shared items

Everything on your account (add-ons and decks), with download counts and votes.
Uses the credentials from `.env`.

```sh
./ankicli.py mine
./ankicli.py mine --json
```

```text
22 shared item(s), 46 review(s):

          ID  UPD             DL    +   -  TITLE
------------------------------------------------
  2119980872  2026-10-10     856    3   1  AI-Hints and Options
   226796325  2026-09-25    2080    5   2  Background Auto Sync
  196373966  2026-07-17    4245    7   1  csv import plus
```

Pair it with `info` for full metadata on any id from the list:

```sh
for id in $(./ankicli.py mine --json | jq -r '.[].id'); do ./ankicli.py info "$id"; done
```

### Info (add-on metadata)

Public, no auth. Reads title, tags, support page, size, versions, and description
from AnkiWeb's `svc/shared/item-info` protobuf endpoint.

```sh
./ankicli.py info 805854302
```

```text
id:           805854302
title:        Integration test for ankiweb client of @athulkrishna2015/ankiweb-api
tags:         integration test tag
support:      https://github.com/danny900714/upload-anki-addon
size:         172
last_updated: 1791704155 (2026-10-11T07:35:55+00:00)
versions:     2.1.1-25.09.4+
description:
<p>Throwaway fixture for upload integration tests. Limit probe: 65535 bytes OK, 65536 rejected.</p>

verify:   https://ankiweb.net/shared/info/805854302?cb=1791710745423
```

### Download `.ankiaddon`

Public, no auth. Follows the `/shared/download/<id>` redirect and writes the file.

```sh
./ankicli.py download 805854302
./ankicli.py download 805854302 -o /tmp/test.ankiaddon
./ankicli.py download 805854302 --point-version 250902    # Anki int_version
```

```text
saved:    Integration_test_for_ankiweb_client_of_athulkrishna2015ankiweb-api.ankiaddon
filename: Integration_test_for_ankiweb_client_of_athulkrishna2015ankiweb-api.ankiaddon
size:     172
t=1791704155 minpt=1 maxpt=250904 bidx=0
```

Equivalent one-liner, no Python needed:

```sh
curl -sL "https://ankiweb.net/shared/download/805854302?v=2.1&p=250902" -o addon.ankiaddon
```

### Terminal notes

- **Description size limit: 65,535 bytes.** Measured on 2026-10-11 by probing
  the throwaway add-on — 65,535 stores, 65,536 is rejected. An over-limit
  upload is **rejected, not truncated**: the add-on keeps its previous
  description, so verify after every large upload. Full write-up:
  [docs/API.md](docs/API.md#description-limits-and-stale-reads).
- `info` prints a `verify:` line with a cache-busted link. AnkiWeb serves
  `item-info` with `max-age=600`, so a plain `/shared/info/<id>` URL can show
  up to 10 minutes of stale data; the `cb` query is required to see what was
  just uploaded.
- `v=2.1` is required on the download URL; without it AnkiWeb replies 404
  ("Your version of Anki is too old"). `p` is Anki's `int_version()`.
- The `.ankiaddon` must be a zip with `__init__.py` at the root — no wrapping
  folder, no `__pycache__` (see [Anki's sharing docs](https://addon-docs.ankiweb.net/sharing.html)).
  `make_test_addon.py` builds a compliant fixture you can inspect.
- Never commit `.env` or AnkiWeb credentials.

## Tests

```sh
python3 test_terminal_ankiweb.py          # offline, no network
python3 test_terminal_ankiweb.py --live   # + live AnkiWeb round-trips + API discovery
python3 -m unittest -v test_ankiweb_proto.py  # API codec and schema regressions
pnpm test                                # GitHub Action unit tests (mocked)
```

Offline tests parse real captured responses in `fixtures/` (private add-on and
AnkiConnect, which carries 133 KB of reviews) and cover CLI exit codes.
Live tests hit `info` / `download` / error paths. API client and codec
documentation is in [docs/API.md](docs/API.md#codec); the complete field-level
reference for all 41 public endpoints is [docs/ENDPOINTS.md](docs/ENDPOINTS.md).

`--live` additionally re-discovers AnkiWeb's live bundle and diffs it against the
committed schema, so a new or removed endpoint fails loudly instead of drifting.
It also asserts that long descriptions survive a real round-trip and that every
read carries a distinct cache-buster — see
[docs/API.md](docs/API.md#description-limits-and-stale-reads). Full run: 56 offline

- live checks, plus 5 codec tests and 16 Action tests.

> [!NOTE]
> Live assertions must read through the cache-buster. `item-info` is served with
> `max-age=600`, so a test hitting a stable URL can pass or fail against stale
> data — which is exactly how a parser bug came to look like a server-side wipe.
> Always go through `fetch_item_info()` / `ankicli.py info`, never a hand-built URL.

### Live upload verification (GitHub Actions engine)

Verified live on 2026-10-11 against the private throwaway add-on
[805854302](https://ankiweb.net/shared/info/805854302) — saved as
`ANKIWEB_TEST_ADDON_ID` in the gitignored `.env` (never committed), used by
local runs and the CI `test-action` / integration jobs (`vars.ADDON_ID`,
`vars.INTEGRATION_TEST_ADDON_ID`):

```sh
python3 make_test_addon.py -o /tmp/gh-action-test.ankiaddon
./upload.py --addon-id "$ANKIWEB_TEST_ADDON_ID" --title "testingaddon for me [private]" \
    --description "test upload via GitHub-Actions engine - 2026-10-11T07:28:56Z" \
    --branches "2.1.1-25.09.4+" --addon-files /tmp/gh-action-test.ankiaddon
./ankicli.py info "$ANKIWEB_TEST_ADDON_ID"        # new description + timestamp confirmed
./ankicli.py download "$ANKIWEB_TEST_ADDON_ID" -o /tmp/verify.ankiaddon   # sha256 matches upload
```

`upload.py` execs `node dist/index.js` — the exact engine the
`test-action` CI job runs — so this covers the GitHub Actions upload path.
Downloaded bytes were sha256-identical to the uploaded fixture.

Same upload verified from real runners: CI run `38121891143` (2026-10-11) is
fully green, with the `test-action` job uploading from `ubuntu-latest`:

```text
Successfully login to AnkiWeb.
Find addon file in test-addon-1.ankiaddon. Uploading it to 2.1.1-25.09.4+ branch ...
Successfully uploaded addon file: test-addon-1.ankiaddon.
```

Note: AnkiWeb requires site-wide unique add-on titles, so the fork's CI test
titles are qualified with `@athulkrishna2015/ankiweb-api` — the inherited
`@danny900714` titles are already taken and fail with `400 title must be unique`.

## GitHub Actions usage

The action itself is unchanged from upstream. Use this fork's reference if you want the
terminal additions from CI; otherwise `danny900714/upload-anki-addon@v1` behaves identically.

### Upload a new add-on to AnkiWeb

If `addon-id` is not provided, a new add-on will be created on AnkiWeb.

Specify the Anki versions your add-on supports using the `branches` parameter.
Use the `+` symbol for the max version to indicate that your add-on supports all future versions as well.

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  upload-addon:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Package add-on
        run: cd src/my-addon && zip -r ../../my-addon.ankiaddon *
      - name: Upload add-on to AnkiWeb
        uses: danny900714/upload-anki-addon@v1
        with:
          username: ${{ vars.ANKIWEB_USERNAME }}
          password: ${{ secrets.ANKIWEB_PASSWORD }}
          title: My Anki add-on
          description: Description for my Anki add-on
          branches: 2.1.1-25.09.4+
          addon-files: my-addon.ankiaddon
```

> [!TIP]
> Package the add-on before uploading. `zip -r ../../my-addon.ankiaddon *` from inside the
> add-on folder keeps `__init__.py` at the zip root (no wrapping folder, no `__pycache__`),
> which is what AnkiWeb requires and what `./upload.py --addon-files` expects locally.

### Using a description file

You can use a separate file for the add-on description, which makes it easier to edit and format.
Note that `description` takes precedence over `description-file` if both are provided.

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  upload-addon:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Package add-on
        run: cd src/my-addon && zip -r ../../my-addon.ankiaddon *
      - name: Upload add-on to AnkiWeb
        uses: danny900714/upload-anki-addon@v1
        with:
          username: ${{ vars.ANKIWEB_USERNAME }}
          password: ${{ secrets.ANKIWEB_PASSWORD }}
          addon-id: 12345678
          title: My Anki add-on
          description-file: README.md
          branches: 2.1.1-25.09.4+
          addon-files: my-addon.ankiaddon
```

### Multiple branches

You can target multiple Anki version ranges by specifying multiple branches, one per line.
The number of `addon-files` must match the number of `branches`.

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: read

jobs:
  upload-addon:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Package add-on for first branch
        run: cd src/first-branch && zip -r ../../first-branch.ankiaddon *
      - name: Package add-on for second branch
        run: cd src/second-branch && zip -r ../../second-branch.ankiaddon *
      - name: Upload add-on to AnkiWeb
        uses: danny900714/upload-anki-addon@v1
        with:
          username: ${{ vars.ANKIWEB_USERNAME }}
          password: ${{ secrets.ANKIWEB_PASSWORD }}
          addon-id: 12345678
          title: My Anki add-on
          description: Description for my Anki add-on
          branches: |
            2.1.1-2.1.66
            23.10-25.09.4+
          addon-files: |
            first-branch.ankiaddon
            second-branch.ankiaddon
```

## Customizing

### Inputs

The following inputs can be used as `step.with` keys:

> `List` type is a newline-delimited string
>
> ```yaml
> branches: |
>   2.1.1-2.1.66
>   23.10-25.09.4+
> ```

| Name               | Type   | Required | Description                                                                                                                                                                                                               |
| ------------------ | ------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `username`         | String | true     | AnkiWeb username.                                                                                                                                                                                                         |
| `password`         | String | true     | AnkiWeb password.                                                                                                                                                                                                         |
| `addon-id`         | String | false    | The download code for the add-on. Omit this when uploading a new add-on.                                                                                                                                                  |
| `title`            | String | true     | The title of the add-on. Must be fewer than 80 characters.                                                                                                                                                                |
| `tags`             | String | false    | Space-separated tags for this add-on.                                                                                                                                                                                     |
| `support-page`     | String | false    | A bug tracker, forum link, or other page where users can reach you. Must start with http.                                                                                                                                 |
| `branches`         | List   | true     | A list of Anki version branches that your add-on supports. Each branch must be in the format `min-max`, where `min` and `max` are Anki versions. Use `+` for the max version to indicate support for all future versions. |
| `addon-files`      | List   | true     | A list of add-on files to upload, in the same order as `branches`. Use `-` to skip updating the add-on file for a branch.                                                                                                 |
| `description`      | String | false    | The description of the add-on. Markdown and basic HTML are supported. AnkiWeb **rejects** descriptions larger than 65,535 bytes — the upload is refused and the add-on keeps its previous description.                    |
| `description-file` | String | false    | Path to a file containing the add-on description. Markdown and basic HTML are supported. Ignored if `description` is also provided.                                                                                       |

> [!NOTE]
>
> - `description` takes precedence over `description-file` if both are provided.
> - The number of `addon-files` must match the number of `branches`.

### Terminal flag equivalents

`upload.py` takes the same values as CLI flags. Each input maps 1:1:

| Input              | Terminal flag        | Notes                                       |
| ------------------ | -------------------- | ------------------------------------------- |
| `username`         | `--username`         | Default `$ANKIWEB_USERNAME` / `.env`.       |
| `password`         | `--password`         | Default `$ANKIWEB_PASSWORD` / `.env`.       |
| `addon-id`         | `--addon-id`         | Omit to create a new add-on.                |
| `title`            | `--title`            | Required, fewer than 80 characters.         |
| `tags`             | `--tags "a b"`       | Space-separated.                            |
| `support-page`     | `--support-page`     | Must start with `http`.                     |
| `branches`         | `--branches a b`     | Repeat the flag once per branch.            |
| `addon-files`      | `--addon-files a b`  | `-` skips a branch's file.                  |
| `description`      | `--description`      | Takes precedence over `--description-file`. |
| `description-file` | `--description-file` | Read from disk.                             |

### Outputs

The following outputs can be accessed via `${{ steps.<step-id>.outputs }}`:

| Name       | Type   | Description                          |
| ---------- | ------ | ------------------------------------ |
| `addon-id` | String | The id for the uploaded Anki add-on. |
