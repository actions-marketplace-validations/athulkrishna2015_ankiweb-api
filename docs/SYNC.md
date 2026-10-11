# Anki sync protocol — self-hosted sync server reference

> **Source:** [`ankitects/anki`](https://github.com/ankitects/anki) — the official
> Anki desktop repository (`rslib/src/sync/`), plus the
> [self-hosted sync server manual](https://docs.ankiweb.net/manual/sync-server).
> Unlike the [/svc/\* API](ENDPOINTS.md), the sync protocol is **official and
> documented by upstream**; this page is a condensed reference gathered from the
> server implementation so the whole Anki HTTP surface is described in one place.
>
> AnkiWeb's hosted sync service speaks this same protocol. Everything below also
> applies to running your **own** server, which is what upstream ships in-tree.

**Jump to:** [Overview](#overview) · [Running a server](#running-a-server) ·
[Configuration](#server-configuration) · [Wire format](#wire-format) ·
[Auth](#authentication) · [Collection endpoints](#collection-endpoints-12) ·
[Media endpoints](#media-endpoints-5) · [Client setup](#client-setup) ·
[Caveats](#caveats-and-relationship-to-svc)

## Overview

Anki clients (desktop, AnkiMobile, AnkiDroid ≥ 2.16) sync collections and media
over plain HTTP against a base URL such as `http://192.168.1.200:8080/`. The
server exposes three route groups, mounted in
[`rslib/src/sync/http_server/mod.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/http_server/mod.rs):

| Mount     | Router                                                    | Purpose                       |
| --------- | --------------------------------------------------------- | ----------------------------- |
| `/sync`   | `collection_sync_router()` — POST `/{method}` (12)        | Collection sync (notes/cards) |
| `/msync`  | `media_sync_router()` — POST `/{method}` (5), GET `begin` | Media sync (images/audio)     |
| `/health` | `health_check_handler()` — GET                            | Liveness check, returns `200` |

This is a **different protocol** from the `/svc/*` JSON-RPC-style web API
documented in [ENDPOINTS.md](ENDPOINTS.md): sync uses camelCase method paths,
versioned envelopes, compressed bodies, and a host-key session — not the
`ankiweb` cookie + codec used by the add-on/deck/study endpoints.

## Running a server

Any of these forms exist upstream (all read the same `SYNC_*` env vars):

```sh
# 1. Sync server built into desktop Anki (2.1.57+)
SYNC_USER1=user:pass anki --syncserver   # Linux; anki-console on Windows, binary path on macOS

# 2. Standalone Python server from PyPI (no GUI dependencies, Python 3.9+)
python3 -m venv ~/syncserver
~/syncserver/bin/pip install anki
SYNC_USER1=user:pass ~/syncserver/bin/python -m anki.syncserver

# 3. Standalone Rust server (Anki 2.1.66+; needs protoc)
cargo install --locked --git https://github.com/ankitects/anki.git --tag 25.02.5 anki-sync-server
SYNC_USER1=user:pass anki-sync-server
```

Dockerfiles (plain and distroless) live in
[`docs/syncserver/`](https://github.com/ankitects/anki/tree/main/docs/syncserver)
of the anki repo; the container runs on port `8080`, ignores `SYNC_BASE` /
`SYNC_PORT` (data goes into the mounted `/anki_data` volume), and supports
`PUID`/`PGID` on the regular image.

## Server configuration

Environment variables are read with the `SYNC_` prefix
([`SyncServerConfig`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/http_server/mod.rs)):

| Variable                      | Default         | Meaning                                                                 |
| ----------------------------- | --------------- | ----------------------------------------------------------------------- |
| `SYNC_USER1`                  | _(required)_    | First account, format `username:password`                               |
| `SYNC_USER2`, `SYNC_USER3`, … | _(optional)_    | Additional accounts, same format                                        |
| `PASSWORDS_HASHED`            | unset           | If set to any value, `SYNC_USER*` passwords are PHC-format hashes       |
| `SYNC_HOST`                   | `0.0.0.0`       | Bind address                                                            |
| `SYNC_PORT`                   | `8080`          | Bind port                                                               |
| `SYNC_BASE`                   | `~/.syncserver` | Storage folder for collection + media (never a normal Anki data folder) |
| `SYNC_IP_HEADER`              | connection info | Client IP source (`axum-client-ip` `ClientIpSource`)                    |
| `MAX_SYNC_PAYLOAD_MEGS`       | `100`           | Max request payload in MB                                               |

Plain-text passwords are hashed server-side with PBKDF2 (fixed salt). With
`PASSWORDS_HASHED=1`, use `username:password_hash` instead.

## Wire format

Two encodings exist; the client picks via the sync version:

| Version constant               | Value | Encoding                                                                  |
| ------------------------------ | ----- | ------------------------------------------------------------------------- |
| `SYNC_VERSION_08_SESSIONKEY`   | 8     | Multipart request with gzip parts + session key                           |
| `SYNC_VERSION_09_V2_SCHEDULER` | 9     | Same wire format; advertises V2 scheduler support                         |
| `SYNC_VERSION_10_V2_TIMEZONE`  | 10    | Same wire format; advertises V2 timezones (media `begin` also via GET)    |
| `SYNC_VERSION_11_DIRECT_POST`  | 11    | **Current**: direct POST, JSON body, zstd compression, `anki-sync` header |

The server accepts versions **8–11** and rejects anything else with `400`
(`unsupported sync version`).

### Version 11 requests

- **Header:** `anki-sync: {"v": 11, "k": "<host key>", "c": "<client version>", "s": "<session key>"}`
  ([`SyncHeader`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/request/header_and_stream.rs))
  - `k` — the host key obtained from `hostKey` (empty on the login request itself)
  - `s` — session key; the server uses it to detect concurrent sync attempts
  - `c` — short client version string, e.g. `2.1.55`
- **Body:** the JSON payload, **zstd-compressed** (raw collection/media bytes
  for `upload`, `download`, `uploadChanges`, `downloadFiles`).
- **Responses** are zstd-compressed too; the server may send an
  `anki-original-size` response header with the uncompressed size.
- Methods without arguments must send the JSON object `{}` (upstream uses a
  padded empty struct so it serialises as a map, not `null`).

### Version ≤ 10 requests

Legacy clients package the payload as `multipart/form-data` with gzip
compression and (for media) pass the client version inside the multipart. The
server keeps this path for compatibility; new clients should use v11.

### Payload limits

`MAX_SYNC_PAYLOAD_MEGS` (default 100 MB) caps the compressed request body; the
decompressed cap is 3× that (`MAXIMUM_SYNC_PAYLOAD_BYTES_UNCOMPRESSED`). A
reverse proxy in front of the server may impose a lower limit that also needs
raising.

### Media responses

Media endpoints wrap results in a legacy JSON envelope that always contains an
`err` field, even on success:

```json
{ "data": { ... }, "err": "" }
```

or on failure `{ "err": "message" }`. `downloadFiles` returns a raw zip
instead.

## Authentication

Login is a normal collection-sync method:

```
POST /sync/hostKey
body (zstd JSON): { "u": "username", "p": "password" }
→ 200: { "key": "<host key>" }
→ 403: invalid user/pass (checked in constant time)
```

The returned key is the **sync key** (`k`) attached to every subsequent request
in the `anki-sync` header. There are no cookies or bearer tokens. On a
self-hosted server the user database is exactly the `SYNC_USER*` list.

## Collection endpoints (12)

All are `POST /sync/{method}` with camelCase method names
([`SyncMethod`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/collection/protocol.rs)):

| Method (POST /sync/…) | Request               | Response              | Purpose                                          |
| --------------------- | --------------------- | --------------------- | ------------------------------------------------ |
| `hostKey`             | `{u, p}`              | `{key}`               | Login; obtain the host/sync key                  |
| `meta`                | `MetaRequest`         | `SyncMeta`            | Collection USN, schema/min sync times, hostNum   |
| `start`               | `StartRequest`        | `Graves`              | Begin sync; server returns deleted-entity graves |
| `applyGraves`         | `ApplyGravesRequest`  | — (null)              | Send client-side deletions to the server         |
| `applyChanges`        | `ApplyChangesRequest` | `UnchunkedChanges`    | Exchange note/card/deck changes                  |
| `chunk`               | `{}`                  | `Chunk`               | Pull the next chunk of server changes            |
| `applyChunk`          | `ApplyChunkRequest`   | — (null)              | Push a chunk of client changes                   |
| `sanityCheck2`        | `SanityCheckRequest`  | `SanityCheckResponse` | Verify collection counts after chunking          |
| `finish`              | `{}`                  | server time (ms)      | Finish sync; returns the server's new USN time   |
| `abort`               | `{}`                  | — (null)              | Abort and release the server-side lock           |
| `upload`              | collection file bytes | `UploadResponse`      | Full sync upload (collection.colpkg)             |
| `download`            | `{}`                  | collection bytes      | Full sync download                               |

`upload`/`download` carry the whole collection file and are chosen when the
server decides a full sync is needed (schema mismatch, first sync, …); the
incremental path is `start → applyGraves → applyChanges → chunk/applyChunk →
sanityCheck2 → finish`.

## Media endpoints (5)

Mounted under `/msync`
([`MediaSyncMethod`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/media/protocol.rs)):

| Method (POST /msync/…) | Request                      | Response                               | Purpose                                    |
| ---------------------- | ---------------------------- | -------------------------------------- | ------------------------------------------ |
| `begin`                | `SyncBeginRequest` (version) | `JsonResult<SyncBeginResponse>`        | Start a media sync; returns the loop index |
| `mediaChanges`         | `MediaChangesRequest`        | `JsonResult<MediaChangesResponse>`     | List media added/changed since an index    |
| `uploadChanges`        | zipped changes bytes         | `JsonResult<MediaUploadResponse>`      | Upload a zip of changed media files        |
| `downloadFiles`        | `DownloadFilesRequest`       | raw zip bytes                          | Download files listed by `mediaChanges`    |
| `mediaSanity`          | `SanityCheckRequest`         | `JsonResult<MediaSanityCheckResponse>` | Compare client/server file counts          |

`begin` also accepts **GET with query parameters** (`host_key`,
`client_version`) as a legacy path used by older clients. The media sync key is
the same host key obtained from `hostKey` (v11 removed the separate media
session key).

## Client setup

1. Point the client at the server base URL, e.g. `http://192.168.1.200:8080/`
   (Anki desktop: Preferences → sync server; AnkiMobile: Settings → custom sync
   server; AnkiDroid ≥ 2.16: custom sync server URL).
2. Sign in with a `SYNC_USER*` account in the AnkiWeb account section.
3. On iOS, "Allow Anki to access local network" may need toggling; iOS reverse
   proxies must offer **TLS 1.2** (not 1.3 only) or AnkiMobile fails with error
   `-9836`.

Client defaults (from
[`rslib/src/sync/http_client/mod.rs`](https://github.com/ankitects/anki/blob/main/rslib/src/sync/http_client/mod.rs)):
when no custom server is configured the endpoint is
**`https://sync.ankiweb.net/`** (not `ankiweb.net`), the per-request I/O
timeout is **30 s**, and the session key (`s` in the header) is a random
base-62 id regenerated each run. Since sync version 11 the old `hostNum`
server-sharding parameter is gone — servers hand out an **HTTP redirect**
instead (see the `SYNC_VERSION_11_DIRECT_POST` notes in `version.rs`).

Older clients expected the endpoints separately:

- `SYNC_ENDPOINT` → `http://host:8080/sync/`
- `SYNC_ENDPOINT_MEDIA` → `http://host:8080/msync/`

AnkiDroid before 2.16 also needs the two endpoints configured separately.
Reverse proxies binding a subpath **must** keep the trailing slash
(`http://example.com/custom/`), and Caddy users should raise the HTTP read
buffer (e.g. `read_buffer 512k`) for large media downloads.

## Caveats and relationship to /svc

- **Plain HTTP by default** — put TLS (VPN or reverse proxy) in front of it
  before exposing it beyond a trusted network.
- **Protocol/client coupling** — newer clients may require newer servers;
  update both together. Third-party sync server implementations exist but lag
  protocol changes and are not tested upstream.
- **No REST API by design** — upstream explicitly rejects PRs adding REST APIs
  or external databases to the bundled server; for a local programmatic API use
  the AnkiConnect add-on instead (third-party, not part of the ankitects org).
- **Different surface from `/svc/*`** — sync moves collections/media; the
  AnkiWeb `/svc/*` API ([ENDPOINTS.md](ENDPOINTS.md)) drives the website:
  add-on uploads, shared decks, study, account management. A self-hosted sync
  server serves neither `/svc` nor any website features.
- In-app messages still say "AnkiWeb" even against a custom server.

---

Related pages: [ENDPOINTS.md](ENDPOINTS.md) — the `/svc/*` reference ·
[ANKIDROID.md](ANKIDROID.md) — AnkiDroid as a sync **client** and its app APIs ·
[ECOSYSTEM.md](ECOSYSTEM.md) — map of every Anki API surface.
