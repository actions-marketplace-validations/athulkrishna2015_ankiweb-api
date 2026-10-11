# The Anki API landscape — surfaces across ankitects & ankidroid

> This page maps **every API surface for talking to Anki** discoverable in the
> two official GitHub organisations —
> [ankitects](https://github.com/ankitects) (Anki desktop & infrastructure)
> and [ankidroid](https://github.com/ankidroid) (Anki for Android) — and says
> which of them this repository documents or implements. Sources are the
> upstream repositories themselves; third-party projects are marked as such.

**Jump to:** [Surface map](#surface-map) · [ankitects repos](#ankitects-repositories-api-relevant) ·
[ankidroid repos](#ankidroid-repositories) · [Third-party](#third-party-not-in-either-org) ·
[Choosing](#choosing-a-surface)

## Surface map

| #   | Surface                                                                   | Transport                                  | Official                                                | Auth                                            | Reference                                                     |
| --- | ------------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------- |
| 1   | **AnkiWeb `/svc/*`** — website API: add-ons, shared decks, study, account | HTTPS JSON (POST/GET `/svc/*`)             | Unofficial (reverse-engineered from AnkiWeb's frontend) | `ankiweb` session cookie / login token          | **This repo**: [ENDPOINTS.md](ENDPOINTS.md), [API.md](API.md) |
| 2   | **Anki sync protocol** — collection + media sync                          | HTTP, zstd/multipart, `anki-sync` header   | Official                                                | Host key from `u`/`p` login                     | [SYNC.md](SYNC.md)                                            |
| 3   | **Self-hosted sync server** — same protocol, your own box                 | HTTP on `:8080`                            | Official (ships in `ankitects/anki`)                    | `SYNC_USER*` accounts                           | [SYNC.md](SYNC.md)                                            |
| 4   | **Anki add-on (Python) API** — `aqt` / `anki` modules, hooks              | In-process (desktop)                       | Official                                                | n/a                                             | Upstream docs¹ (see below)                                    |
| 5   | **AnkiDroid ContentProvider / Instant-Add**                               | `content://com.ichi2.anki.flashcards`      | Official (Android)                                      | `com.ichi2.anki.permission.READ_WRITE_DATABASE` | [ANKIDROID.md](ANKIDROID.md)                                  |
| 6   | **AnkiDroid intent API**                                                  | Android intents (`ACTION_SEND`, `DO_SYNC`) | Official (Android)                                      | none                                            | [ANKIDROID.md](ANKIDROID.md)                                  |
| 7   | **AnkiDroid JavaScript API**                                              | WebView bridge (`AnkiDroidJS`)             | Official (Android)                                      | none (developer contact required)               | [ANKIDROID.md](ANKIDROID.md)                                  |
| 8   | **AnkiDroid media/file APIs**                                             | part of the provider (`/media`)            | Official (Android)                                      | as #5                                           | [ANKIDROID.md](ANKIDROID.md)                                  |

¹ `ankitects/anki/docs/api-python.md` and `docs/api-aqt-modules.md` are Sphinx
toctrees over auto-generated docstrings for `anki` (collection model) and
`aqt` (Qt UI); the Rust API is `cargo doc` over `rslib/` crates. Add-on
how-tos live in the separate
[ankitects/addon-docs](https://github.com/ankitects/addon-docs) site
(addon-docs.ankiweb.net).

**Not to be confused:** the **sync protocol** moves collections between
devices; the **`/svc/*` API** (this repo) drives ankiweb.net's website
features; the **AnkiDroid APIs** talk to the app on a device over Android IPC.
They share no wire format and no auth — see [SYNC.md — caveats](SYNC.md#caveats-and-relationship-to-svc).

## ankitects repositories (API-relevant)

| Repository                                                      | What it gives you                                                                                                                                                                                                               |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [anki](https://github.com/ankitects/anki)                       | The desktop app. Contains the **sync protocol client + server** (`rslib/src/sync/`), the collection library (`rslib/`), the Python packages `anki` + `aqt` (add-on API), and `docs/` (Sphinx API docs, sync-server Dockerfiles) |
| [addon-docs](https://github.com/ankitects/addon-docs)           | The official add-on writing documentation (hooks, editor APIs, scheduling) — source of addon-docs.ankiweb.net                                                                                                                   |
| [anki-manual](https://github.com/ankitects/anki-manual)         | End-user manual, including the [sync server manual](https://docs.ankiweb.net/manual/sync-server)                                                                                                                                |
| [anki-addons](https://github.com/ankitects/anki-addons)         | Source of Anki's own bundled add-ons — worked examples of the add-on API                                                                                                                                                        |
| [faqs](https://github.com/ankitects/faqs)                       | AnkiWeb FAQ content (behaviour of the website APIs)                                                                                                                                                                             |
| [anki-changes](https://github.com/ankitects/anki-changes)       | Release/change notes — the history of API and protocol changes                                                                                                                                                                  |
| [ankimobile-docs](https://github.com/ankitects/ankimobile-docs) | AnkiMobile manual (iOS client behaviour, incl. custom sync servers)                                                                                                                                                             |
| [anki-betas](https://github.com/ankitects/anki-betas)           | Beta release notes                                                                                                                                                                                                              |

## ankidroid repositories

| Repository                                                                                                                                                                        | What it gives you                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Anki-Android](https://github.com/ankidroid/Anki-Android)                                                                                                                         | The Android app. Hosts the **`api/` module** (Instant-Add library: `AddContentApi` + `FlashCardsContract`), the ContentProvider implementation, the intent handlers, and the `AnkiDroidJS` WebView bridge; wiki pages: [AnkiDroid API](https://github.com/ankidroid/Anki-Android/wiki/AnkiDroid-API), [JavaScript API](https://github.com/ankidroid/Anki-Android/wiki/AnkiDroid-JavaScript-API), [Third Party Apps](https://github.com/ankidroid/Anki-Android/wiki/Third-Party-Apps) |
| [apisample](https://github.com/ankidroid/apisample)                                                                                                                               | Reference client of the Instant-Add API (dictionary demo + Tasker sync profile)                                                                                                                                                                                                                                                                                                                                                                                                      |
| [Anki-Android-Backend](https://github.com/ankidroid/Anki-Android-Backend)                                                                                                         | JNI bridge exposing Anki's Rust collection code (`rslib`) to Kotlin — the layer AnkiDroid's DB/scheduler is built on (not an app-facing API)                                                                                                                                                                                                                                                                                                                                         |
| [ankidroiddocs](https://github.com/ankidroid/ankidroiddocs)                                                                                                                       | User documentation site (ankidroid.org)                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| [anki](https://github.com/ankidroid/anki)                                                                                                                                         | Archived tracking fork of Anki desktop used for bundling — no API                                                                                                                                                                                                                                                                                                                                                                                                                    |
| [acra-storage](https://github.com/ankidroid/acra-storage), [acralyzer](https://github.com/ankidroid/acralyzer), [ankidroid-triage](https://github.com/ankidroid/ankidroid-triage) | Crash-reporting infrastructure (archived) — not APIs                                                                                                                                                                                                                                                                                                                                                                                                                                 |

AnkiDroid itself **is a client of surface #2**: it syncs through the standard
Anki sync protocol (custom server URL supported since 2.16; earlier versions
needed the `/sync/` and `/msync/` endpoints separately — see
[SYNC.md — client setup](SYNC.md#client-setup)).

## Third-party (not in either org)

Listed only to avoid confusion — none of these are maintained by ankitects or
ankidroid:

- **AnkiConnect** (`foosoft/anki-connect`) — local HTTP API add-on for Anki
  desktop; upstream's sync-server docs point to it when a REST API is wanted.
- **AnkiJS-API** (`jhhr/AnkiJS-API`) — desktop-port of most of the AnkiDroid
  JS API (also on AnkiWeb as add-on 1490471827).
- **react-native-ankidroid** — React Native wrapper over the Instant-Add API.
- Third-party sync servers — exist, but upstream does not test them and they
  tend to lag protocol changes.

## Choosing a surface

| You want to…                                                             | Use                                                                                         |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Upload/update your add-on, list shared decks, drive study on ankiweb.net | `/svc/*` in this repo — [ENDPOINTS.md](ENDPOINTS.md)                                        |
| Sync collections between devices / host your own sync server             | Sync protocol — [SYNC.md](SYNC.md)                                                          |
| Read/write cards in AnkiDroid from another Android app                   | Instant-Add / ContentProvider — [ANKIDROID.md](ANKIDROID.md)                                |
| Send a card to AnkiDroid without permissions, or trigger a sync          | Intents — [ANKIDROID.md](ANKIDROID.md#intent-api)                                           |
| Build custom reviewer UIs inside a card template                         | JS API — [ANKIDROID.md](ANKIDROID.md#javascript-api)                                        |
| Extend Anki desktop itself                                               | Add-on Python API (`aqt`) — [ankitects/addon-docs](https://github.com/ankitects/addon-docs) |
| Control a local Anki desktop from a program                              | Third-party AnkiConnect (external; see above)                                               |

---

Related pages: [ENDPOINTS.md](ENDPOINTS.md) · [API.md](API.md) ·
[SYNC.md](SYNC.md) · [ANKIDROID.md](ANKIDROID.md) · [Home.md](Home.md)
