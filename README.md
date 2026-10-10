# Upload Anki Add-on

[![CI](https://github.com/danny900714/upload-anki-addon/actions/workflows/ci.yml/badge.svg)](https://github.com/danny900714/upload-anki-addon/actions/workflows/ci.yml)

Upload an [Anki](https://apps.ankiweb.net/) add-on to [AnkiWeb](https://ankiweb.net/shared/addons) — from GitHub Actions or from your terminal.

> Fork of [danny900714/upload-anki-addon](https://github.com/danny900714/upload-anki-addon) (`upstream/main` remote).
> The Node upload engine (`dist/index.js`) is unmodified upstream code; this fork adds the terminal tooling below.

## Features

- **Multiple branches**: Upload different add-on files targeting different Anki version ranges.
- **Description file**: Use a separate file for the add-on description, making it easier to edit and format.
- **Terminal CLI**: Upload, inspect, and download add-ons without GitHub Actions.
- **Metadata-only updates**: Change title/description/tags without re-uploading the `.ankiaddon`.
- **Reverse-engineered API client**: Schema-driven access to discovered AnkiWeb `/svc/*` endpoints.

## Table of contents

- [Terminal usage](#terminal-usage) — [setup](#setup) · [upload](#upload) · [info](#info-add-on-metadata) · [download](#download-ankiaddon) · [notes](#terminal-notes)
- [Tests](#tests)
- [AnkiWeb API client](docs/API.md)
- [GitHub Actions usage](#github-actions-usage) — [inputs](#inputs) · [outputs](#outputs)

## Terminal usage

Requires Python 3.9+ with `requests`, plus Node 24 if you upload (the action engine runs on Node).
`info` and `download` are Python-only and need no Node.

### Setup

```sh
git clone https://github.com/athulkrishna2015/upload-anki-addon.git
cd upload-anki-addon
pip install -r requirements-terminal.txt
```

Keep credentials in `.env` (gitignored — never commit it):

```sh
cp .env.example .env
$EDITOR .env     # ANKIWEB_USERNAME=... / ANKIWEB_PASSWORD=...
```

`upload.py` reads `./.env` automatically. Exported shell variables take precedence, and
`--username` / `--password` override both.

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

| Flag                  | Description                                                             |
| --------------------- | ----------------------------------------------------------------------- |
| `--tags "a b"`        | Space-separated tags.                                                   |
| `--support-page URL`  | Must start with `http`.                                                 |
| `--dry-run`           | Print the `INPUT_*` mapping and exit without network access.            |
| `--env-file PATH`     | Use a different `.env` (default `./.env`).                             |
| `--node PATH`         | Node binary to run the engine with (default `node`).                    |

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
title:        testingaddon for me [private]
size:         16631
last_updated: 1761920298 (2025-10-31T14:18:18+00:00)
versions:     2.1.1+
description:
<p>test upload via terminal - 2026-10-10T13:15:37Z</p>
```

### Download `.ankiaddon`

Public, no auth. Follows the `/shared/download/<id>` redirect and writes the file.

```sh
./ankicli.py download 805854302
./ankicli.py download 805854302 -o /tmp/test.ankiaddon
./ankicli.py download 805854302 --point-version 250902    # Anki int_version
```

```text
saved:    testingaddon_for_me_private.ankiaddon
filename: testingaddon_for_me_private.ankiaddon
size:     16631
t=1761920298 minpt=1 maxpt=1 bidx=0
```

Equivalent one-liner, no Python needed:

```sh
curl -sL "https://ankiweb.net/shared/download/805854302?v=2.1&p=250902" -o addon.ankiaddon
```

### Terminal notes

- `v=2.1` is required on the download URL; without it AnkiWeb replies 404
  ("Your version of Anki is too old"). `p` is Anki's `int_version()`.
- The `.ankiaddon` must be a zip with `__init__.py` at the root — no wrapping
  folder, no `__pycache__` (see [Anki's sharing docs](https://addon-docs.ankiweb.net/sharing.html)).
  `make_test_addon.py` builds a compliant fixture you can inspect.
- Never commit `.env` or AnkiWeb credentials.

## Tests

```sh
python3 test_terminal_ankiweb.py          # offline, no network
python3 test_terminal_ankiweb.py --live   # + live AnkiWeb round-trips
```

Offline tests parse real captured responses in `fixtures/` (private add-on and
AnkiConnect, which carries 133 KB of reviews) and cover CLI exit codes.
Live tests hit `info` / `download` / error paths.

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
| `description`      | String | false    | The description of the add-on. Markdown and basic HTML are supported.                                                                                                                                                     |
| `description-file` | String | false    | Path to a file containing the add-on description. Markdown and basic HTML are supported. Ignored if `description` is also provided.                                                                                       |

> [!NOTE]
>
> - `description` takes precedence over `description-file` if both are provided.
> - The number of `addon-files` must match the number of `branches`.

### Terminal flag equivalents

`upload.py` takes the same values as CLI flags. Each input maps 1:1:

| Input             | Terminal flag       | Notes                                          |
| ----------------- | ------------------- | ---------------------------------------------- |
| `username`        | `--username`        | Default `$ANKIWEB_USERNAME` / `.env`.          |
| `password`        | `--password`        | Default `$ANKIWEB_PASSWORD` / `.env`.          |
| `addon-id`        | `--addon-id`        | Omit to create a new add-on.                   |
| `title`           | `--title`           | Required, fewer than 80 characters.            |
| `tags`            | `--tags "a b"`      | Space-separated.                               |
| `support-page`    | `--support-page`    | Must start with `http`.                        |
| `branches`        | `--branches a b`    | Repeat the flag once per branch.               |
| `addon-files`     | `--addon-files a b` | `-` skips a branch's file.                     |
| `description`     | `--description`     | Takes precedence over `--description-file`.    |
| `description-file`| `--description-file`| Read from disk.                                |

### Outputs

The following outputs can be accessed via `${{ steps.<step-id>.outputs }}`:

| Name       | Type   | Description                          |
| ---------- | ------ | ------------------------------------ |
| `addon-id` | String | The id for the uploaded Anki add-on. |
