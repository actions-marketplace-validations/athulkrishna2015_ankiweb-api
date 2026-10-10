# Terminal use (fork additions)

This fork of [danny900714/upload-anki-addon](https://github.com/danny900714/upload-anki-addon)
(`upstream/main` remote) keeps the upstream Node upload engine untouched and adds
thin terminal helpers around it. No reinvented upload logic.

## What lives where

| File | Purpose |
|---|---|
| `dist/index.js` (+ `src/`) | **Upstream engine** — login + `POST svc/shared/upload-addon` (protobuf). Canonical for uploads. |
| `upload.py` | Thin wrapper: CLI args → `INPUT_*` env → `node dist/index.js`. No protobuf of its own. |
| `terminal_ankiweb.py` | **New**: public no-auth endpoints upstream lacks (download + item-info). |
| `ankicli.py` | CLI for the above: `info`, `download`. |

## Info + download (no auth)

```sh
pip install requests   # only dependency
./ankicli.py info 805854302
./ankicli.py download 805854302 -o /tmp/test.ankiaddon
```

Endpoints (AnkiWeb has no public API; used by its SvelteKit frontend):

- `GET /svc/shared/item-info?sharedId=<id>` — protobuf, `max-age=600`, no auth.
  `sharedId` must be camelCase (`shared_id` → 400). Decoded heuristically in
  `terminal_ankiweb.parse_item_info` (title=f5, description=f9, versions@depth3/f1;
  reviews share depth1/f1 so longest-string matching is wrong — see code).
- `GET /shared/download/<id>?v=2.1&p=<int_version>` — 303 to
  `/svc/shared/download-addon/<id>?t=..&minpt=..&maxpt=..&bidx=..`, then
  `application/octet-stream` + `Content-Disposition: attachment; filename=...`.
  No auth. `v=2.1` is required (without it: 404 "Your version of Anki is too old").
  `p` is Anki's `int_version()` (e.g. `250902`); default `250902` works for old branches.

Test addon: [805854302](https://ankiweb.net/shared/info/805854302)
(`testingaddon for me [private]`, branch `2.1.1+`).

## Upload / description update (auth, via upstream)

Credentials (`.env` is gitignored; never commit it):

```sh
cp .env.example .env
$EDITOR .env          # ANKIWEB_USERNAME=... / ANKIWEB_PASSWORD=...
```

`upload.py` reads `./.env` automatically (existing exported vars take precedence,
`--env-file PATH` to override, or `--username/--password` flags).

```sh
# file + metadata update on the test addon:
./upload.py --addon-id 805854302 --title "testingaddon for me [private]" \
    --description-file DESCRIPTION.md \
    --branches "2.1.1+" --addon-files ./my.ankiaddon
# metadata-only (description/tags/title, no file — upstream `-` convention):
./upload.py --addon-id 805854302 --title "testingaddon for me [private]" \
    --description "new text" --branches "2.1.1+" --addon-files -
# preview the INPUT_* mapping without touching the network:
./upload.py ... --dry-run
```

Rules (from upstream `action.yml`): `--branches` and `--addon-files` must have
equal length and matching order; `--description` wins over `--description-file`;
title < 80 chars; support page must start with `http`.

## Policy note

AnkiWeb has no official upload API
([ankitects/anki#4869](https://github.com/ankitects/anki/issues/4869)); a forum
mod flags third-party API use as against ToS. Use this for your own add-ons,
and prefer the manual [upload page](https://ankiweb.net/shared/upload) when in doubt.
