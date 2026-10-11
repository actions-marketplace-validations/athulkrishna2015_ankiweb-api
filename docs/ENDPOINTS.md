# AnkiWeb API — full endpoint reference (41 public endpoints)

> **Status: full compatibility.** Every non-admin `/svc/*` endpoint served by
> AnkiWeb's web frontend is decoded and callable via `AnkiWebClient`.
> Schema revision: **2026-10-10** — 174 messages, 41 public + 22 radmin endpoints.
> Regenerate any time with `python3 tools/generate_schema.py`.
>
> AnkiWeb exposes no official public API. These endpoints are reverse-engineered
> from the site's own frontend bundle, may change without notice, and are
> subject to AnkiWeb's terms and rate limits. The 22 `/svc/radmin/*` admin
> endpoints are decoded into the schema for completeness but are **not** exposed
> on the client — see [reference only](#admin-endpoints-reference-only-not-callable).
> Use only with an account and data you are authorized to access.

**Jump to:** [Account](#account-12) · [Decks](#decks-8) ·
[Editor and search](#editor-and-search-4) ·
[Shared public reads](#shared-public-reads-5-no-auth) ·
[Shared account reads and writes](#shared-account-reads-and-writes-7-auth) ·
[Study](#study-4) · [Admin (reference only)](#admin-endpoints-reference-only-not-callable) ·
[Wire details](#wire-details)

> Client concepts, safety rules, and schema regeneration are in
> [API.md](API.md); installation and the CLI are in the [README](../README.md).
>
> **Related APIs:** this reference covers `/svc/*` (AnkiWeb's website JSON
> API) only. Collection/media sync is a **separate protocol** served under
> `/sync/*` and `/msync/*` — see [SYNC.md](SYNC.md); AnkiDroid's on-device APIs
> are in [ANKIDROID.md](ANKIDROID.md); [ECOSYSTEM.md](ECOSYSTEM.md) maps every
> surface.

## Quick start

```python
from ankiweb_client import AnkiWebClient

client = AnkiWebClient()   # reads .env (ANKIWEB_USERNAME / ANKIWEB_PASSWORD)
client.login()

mine = client.shared_list_mine()
print(mine["items"])

item = client.shared_item_info(shared_id=2055492159)  # no auth needed
print(item["available"]["title"])
```

Method names are `<area>_<action>`, e.g. `account_login`, `shared_list_mine`,
`decks_create_deck`, `study_study_cards`. Legacy aliases `login`, `list_mine`,
`item_info` still work.

Auth: POST endpoints attach the `ankiweb` session cookie automatically (login
first), except the no-auth account endpoints (`login`, `signup`,
`reset-password`, `resend-verification`, `verify-email`, `get-account-status`)
and the three public GET endpoints (`item-info`, `list-addons`, `list-decks`).

---

## Account (12)

| Method                                                               | Endpoint                                | Auth | Request                                                         | Response                                                                                                                                           |
| -------------------------------------------------------------------- | --------------------------------------- | ---- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `account_login(username, password)`                                  | POST `/svc/account/login`               | no   | `username`, `password`                                          | `{status, token}` — status: UNKNOWN / AUTHENTICATED / INVALID_USER / INVALID_PASS                                                                  |
| `account_check_terms()`                                              | POST `/svc/account/check-terms`         | yes  | — (empty)                                                       | `{needs_to_confirm: bool}`                                                                                                                         |
| `account_confirm_terms(agree_to_terms=True)`                         | POST `/svc/account/confirm-terms`       | yes  | `agree_to_terms: bool`                                          | — (empty)                                                                                                                                          |
| `account_get_account_status()`                                       | POST `/svc/account/get-account-status`  | no   | — (empty)                                                       | `{logged_in: bool, redirect_to?: string}`                                                                                                          |
| `account_get_settings()`                                             | POST `/svc/account/get-settings`        | yes  | — (empty)                                                       | `{current_email: string}`                                                                                                                          |
| `account_update_settings(current_password, new_password, new_email)` | POST `/svc/account/update-settings`     | yes  | `current_password`, `new_password`, `new_email`                 | `{result}` — UNKNOWN / PASSWORD_CHANGED / EMAIL_CHANGED / INVALID_CURRENT_PASSWORD / INVALID_EMAIL / EMAIL_UNAVAILABLE / SPAM_REPORT               |
| `account_signup(username, password)`                                 | POST `/svc/account/signup`              | no   | `username`, `password`                                          | `{status, ankiuser_login_token?}` — UNKNOWN / SUCCESS / USERNAME_INVALID / USERNAME_TAKEN / SPAM_EMAIL                                             |
| `account_verify_email(token="")`                                     | POST `/svc/account/verify-email`        | no   | `token?: string`                                                | `{token_verified: bool, sending_status{updated, progress, email}}` — progress: UNKNOWN / SENDING / DELIVERED / SPAM / QUOTA / OTHER_DELAY / FAILED |
| `account_resend_verification(hkey="")`                               | POST `/svc/account/resend-verification` | no   | `hkey?: string`                                                 | `{throttled: bool}`                                                                                                                                |
| `account_reset_password(email_to, check_token, new_password?)`       | POST `/svc/account/reset-password`      | no   | `email_to`, `check_token`, `new_password{token, new_password}?` | `{send_email, token_ok: bool, set_new_password}` — send_email: UNKNOWN / THROTTLED / INVALID_EMAIL / SUCCESS                                       |
| `account_total_media()`                                              | POST `/svc/account/total-media`         | yes  | — (empty)                                                       | `{total_bytes: uint64}`                                                                                                                            |
| `account_remove_account(current_password)`                           | POST `/svc/account/remove-account`      | yes  | `current_password`                                              | `{status, media_removed: uint32}` — status: UNKNOWN / VALID_PASSWORD_REQUIRED / IN_PROGRESS / FINISHED. **Irreversible.**                          |

## Decks (8)

| Method                                               | Endpoint                           | Request                                    | Response                                                                                                                                                    |
| ---------------------------------------------------- | ---------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `decks_create_deck(name)`                            | POST `/svc/decks/create-deck`      | `name: string`                             | — (empty)                                                                                                                                                   |
| `decks_deck_list_info(minutes_west_of_utc?)`         | POST `/svc/decks/deck-list-info`   | `minutes_west_of_utc?: int32`              | `{top_node{deck_id, name, level, collapsed, review/learn/new_count, ...}, current_deck_id: int64, collection_size_bytes: uint32, media_size_bytes: uint64}` |
| `decks_deck_share_info(deck_id)`                     | POST `/svc/decks/deck-share-info`  | `deck_id: int64`                           | `{metadata{title, tags, support_url, description, deck_id, shared_id?}, is_large_user: bool, share_count: uint32}`                                          |
| `decks_deck_share(metadata, confirm_copyright=True)` | POST `/svc/decks/deck-share`       | `metadata{...}`, `confirm_copyright: bool` | — (empty)                                                                                                                                                   |
| `decks_deck_share_state()`                           | POST `/svc/decks/deck-share-state` | — (empty)                                  | `{state, shared_id?}` — state: NO_ACTIVE_SHARE / WAITING / IN_PROGRESS / SUCCESS / TOO_LARGE / UNKNOWN_ERROR                                                |
| `decks_rename_deck(deck_id, new_name)`               | POST `/svc/decks/rename-deck`      | `deck_id: int64`, `new_name: string`       | `{error: string}` (empty on success)                                                                                                                        |
| `decks_remove_deck(deck_id)`                         | POST `/svc/decks/remove-deck`      | `deck_id: int64`                           | — (empty)                                                                                                                                                   |
| `decks_select_deck(deck_id)`                         | POST `/svc/decks/select-deck`      | `deck_id: int64`                           | — (empty)                                                                                                                                                   |

## Editor and search (4)

| Method                                    | Endpoint                               | Request                                        | Response                                                               |
| ----------------------------------------- | -------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| `editor_get_info_for_adding()`            | POST `/svc/editor/get-info-for-adding` | — (empty)                                      | `{notetypes[], decks[], current_deck_id/notetype_id: int64, fields[]}` |
| `editor_get_note_info(note_id)`           | POST `/svc/editor/get-note-info`       | `note_id: int64`                               | `{fields[]: string, notetype_fields[], tags: string}`                  |
| `editor_get_notetype_fields(notetype_id)` | POST `/svc/editor/get-notetype-fields` | `notetype_id: int64`                           | `{fields[]}`                                                           |
| `editor_add_or_update(request)`           | POST `/svc/editor/add-or-update`       | full `EditorAddOrUpdateRequest` (see `SCHEMA`) | `{...}`                                                                |
| `search_search(search)`                   | POST `/svc/search/search`              | `search: string`                               | `{notes[{...}], error: string}`                                        |

## Shared public reads (5, no auth)

| Method                              | Endpoint                                  | Request                  | Response                                                                                                                                            |
| ----------------------------------- | ----------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `shared_item_info(shared_id)`       | GET `/svc/shared/item-info?sharedId=<id>` | query `sharedId: uint32` | `{available{title, description, tags, versions[], size, last_updated, reviews[]...}, missing: bool, access_denied: bool}` — cached 600s server-side |
| `shared_list_addons()`              | GET `/svc/shared/list-addons`             | —                        | `{rows[{id, title, thumbs_up/down, mtime, max_supported_version}], user_upload_status}` — UNSPECIFIED / NO_USER / TOO_NEW / CAN_UPLOAD              |
| `shared_list_decks()`               | GET `/svc/shared/list-decks`              | —                        | `{rows[{id, title, thumbs_up/down, mtime, notes, audio, images, ...}]}`                                                                             |
| `shared_items_by_author(shared_id)` | POST `/svc/shared/items-by-author`        | `shared_id: uint32`      | `{items[{shared_id, title}]}`                                                                                                                       |
| `shared_get_addon_info(addon_id)`   | POST `/svc/shared/get-addon-info`         | `addon_id: uint32`       | `{addon{addon_id?, title, tags, support_url, description, branches[{min_version, max_version}]}}`                                                   |

## Shared account reads and writes (7, auth)

| Method                                          | Endpoint                            | Request                                                                                                              | Response                                                                                                                            |
| ----------------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `shared_list_mine()`                            | POST `/svc/shared/list-mine`        | — (empty)                                                                                                            | `{items[{id, title, thumbs_up/down, mtime, downloads, max_supported_version?}], reviews[{review, item_id, hash}], expired_decks[]}` |
| `shared_remove_item(shared_id)`                 | POST `/svc/shared/remove-item`      | `shared_id: uint32`                                                                                                  | — (empty)                                                                                                                           |
| `shared_get_own_review(shared_id)`              | POST `/svc/shared/get-own-review`   | `shared_id: uint32`                                                                                                  | `{review{body, thumbs_up}, shared_item_title, support_page?}`                                                                       |
| `shared_set_own_review(shared_id, review)`      | POST `/svc/shared/set-own-review`   | `shared_id`, `review{body: string, thumbs_up: bool}`                                                                 | — (empty)                                                                                                                           |
| `shared_reply_to_review(shared_id, hash, body)` | POST `/svc/shared/reply-to-review`  | `shared_Id` (! exact wire name), `hash: uint32`, `body: string`                                                      | — (empty)                                                                                                                           |
| `shared_report_copyright(shared_id)`            | POST `/svc/shared/report-copyright` | `shared_id: uint32`                                                                                                  | — (empty)                                                                                                                           |
| `shared_upload_addon(info, file?)`              | POST `/svc/shared/upload-addon`     | `info{addon_id?, title, tags, support_url, description, branches[]}`, `file{zip_data: bytes, branch_index: uint32}?` | `{addon_id: uint32}` — also wrapped by `upload.py` / the GitHub Action                                                              |

## Study (4)

| Method                                                                    | Endpoint                            | Request                                                                                                              | Response                                                                                                                      |
| ------------------------------------------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `study_get_deck_limits()`                                                 | POST `/svc/study/get-deck-limits`   | — (empty)                                                                                                            | `{new: uint32, review: uint32, new_cards_ignore_review_limit: bool, error: string}`                                           |
| `study_set_deck_limits(new, review, new_cards_ignore_review_limit=False)` | POST `/svc/study/set-deck-limits`   | `new`, `review: uint32`, `new_cards_ignore_review_limit: bool`                                                       | — (empty)                                                                                                                     |
| `study_study_cards(answer?, next_card_id?)`                               | POST `/svc/study/study-cards`       | `answer{card_id, answer_button, time_taken_millis, answered_at_millis, current/next_state}?`, `next_card_id?: int64` | `{sched_ver: uint32, cards[{card_id, question, answer, count_index, button_labels[], note_id, ...}], new/learn/review_count}` |
| `study_upgrade_scheduler(v3=True)`                                        | POST `/svc/study/upgrade-scheduler` | `v3: bool`                                                                                                           | — (empty)                                                                                                                     |

## Admin endpoints — reference only, not callable

> [!CAUTION]
> **Reference only. Not part of the supported surface.** The 22 `/svc/radmin/*`
> endpoints below are decoded in `SCHEMA` — all request/response/nested names
> resolve — but are **deliberately not exposed** on `AnkiWebClient` and have no
> typed wrapper. They require AnkiWeb staff privileges and act on _other users'
> accounts_, so several are destructive and irreversible (`ban-user`,
> `clear-reviews`, `bulk-remove-reviews`, `move-addon`, `restore-collection-backup`,
> `balance-users`). They are listed so the decode coverage is honest and auditable,
> **not** as an invitation to call them.

They remain reachable through the codec if you deliberately construct a request
(`ankiweb_proto.encode("RadminBanUserRequest", {"user_id": 1})`), because removing
them from the schema would misreport what was actually decoded. Don't, unless you
are AnkiWeb staff debugging a live incident.

| Reference name (no wrapper exists) | Endpoint                                     | Request fields                                 | Response fields                            |
| ---------------------------------- | -------------------------------------------- | ---------------------------------------------- | ------------------------------------------ |
| `radmin_all_shared_items`          | POST `/svc/radmin/all-shared-items`          | `user_id`                                      | `items`, `reviews`                         |
| `radmin_balance_users`             | POST `/svc/radmin/balance-users`             | `batch_size`, `batch_count`, `shards_to_drain` | — (empty)                                  |
| `radmin_ban_user`                  | POST `/svc/radmin/ban-user`                  | `user_id`                                      | — (empty)                                  |
| `radmin_become_user`               | POST `/svc/radmin/become-user`               | `user_id`                                      | `token`                                    |
| `radmin_bulk_disable_sharing`      | POST `/svc/radmin/bulk-disable-sharing`      | `user_ids`, `reason`                           | — (empty)                                  |
| `radmin_bulk_remove_reviews`       | POST `/svc/radmin/bulk-remove-reviews`       | `user_ids`, `reason`                           | — (empty)                                  |
| `radmin_clear_reviews`             | POST `/svc/radmin/clear-reviews`             | `user_id`, `mode`                              | — (empty)                                  |
| `radmin_dump_all_addons`           | POST `/svc/radmin/dump-all-addons`           | —                                              | — (empty)                                  |
| `radmin_email_status`              | POST `/svc/radmin/email-status`              | `email`, `action`                              | `sent`, `changed`, `verified`, `state`     |
| `radmin_export_revlogs`            | POST `/svc/radmin/export-revlogs`            | `shard`, `options`                             | — (empty)                                  |
| `radmin_fix_media`                 | POST `/svc/radmin/fix-media`                 | `user_id`, `dry_run`                           | `files_processed`                          |
| `radmin_get_collection_backups`    | POST `/svc/radmin/get-collection-backups`    | `user_id`                                      | `backups`                                  |
| `radmin_get_user_info`             | POST `/svc/radmin/get-user-info`             | `user_id`                                      | `user`                                     |
| `radmin_list_media`                | POST `/svc/radmin/list-media`                | `user_id`                                      | `entries`                                  |
| `radmin_lookup_users`              | POST `/svc/radmin/lookup-users`              | `search`                                       | `matched_users`, `first_match`, `ip_match` |
| `radmin_migrate_user`              | POST `/svc/radmin/migrate-user`              | `user_id`, `target_shard`                      | — (empty)                                  |
| `radmin_migrate_users`             | POST `/svc/radmin/migrate-users`             | `source_shard`, `target_shard`, `count`        | — (empty)                                  |
| `radmin_move_addon`                | POST `/svc/radmin/move-addon`                | `shared_id`, `target_user_id`                  | — (empty)                                  |
| `radmin_recalculate_ratings`       | POST `/svc/radmin/recalculate-ratings`       | `shared_id`                                    | — (empty)                                  |
| `radmin_restore_collection_backup` | POST `/svc/radmin/restore-collection-backup` | `user_id`, `version`                           | — (empty)                                  |
| `radmin_restore_media`             | POST `/svc/radmin/restore-media`             | `user_id`, `days`, `dry_run`                   | `files_processed`                          |
| `radmin_support_notes`             | POST `/svc/radmin/support-notes`             | `user_id`, `new_note`                          | `notes`                                    |

> [!NOTE]
> The first column is a **documentation label, not a method name**. There is no
> `AnkiWebClient.radmin_ban_user()` — calling it raises `AttributeError`. Only
> the 41 public endpoints in the sections above are callable.

The client enforces this in code, not just in docs: `public_endpoints()` filters
`/radmin/` out of the schema's endpoint list, and `AnkiWebClient.__getattr__`
refuses to synthesise a wrapper for any path that is admin-only.

## Wire details

- Transport: `POST` with `Content-Type: application/octet-stream` (protobuf
  bytes), except the three GET endpoints which pass `URLSearchParams`.
- Session: `Cookie: has_auth=1; ankiweb=<cookie>` + `Referer:
https://ankiweb.net/shared/mine`, exactly as the web app sends.
- Verified live 2026-10-10: `GET /svc/shared/item-info?sharedId=2055492159`
  → 200 → decodes as `SharedItemInfoResponse` via `ankiweb_proto.decode`.
- Field numbers/types: see `ankiweb_schema.SCHEMA` (generated, authoritative as
  of the revision date). Regenerate with `python3 tools/generate_schema.py`
  and review the diff before accepting.

### This is not the sync protocol

AnkiWeb serves two unrelated HTTP surfaces; only the first is documented here:

|           | `/svc/*` (this page)                                                     | `/sync/*` + `/msync/*`                                                                    |
| --------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Purpose   | Website features: add-ons, shared decks, study, account                  | Collection & media sync between clients and a server                                      |
| Encoding  | Protobuf messages in octet-stream bodies (codec: [API.md](API.md#codec)) | JSON (or multipart/gzip for legacy clients), zstd-compressed, `anki-sync` header envelope |
| Auth      | `ankiweb` session cookie (or none for public reads)                      | Host key from `POST /sync/hostKey` (`{u, p}`)                                             |
| Official? | No — reverse-engineered from the frontend bundle                         | Yes — official protocol, client and server in `ankitects/anki`                            |
| Reference | [ENDPOINTS.md](ENDPOINTS.md) (here)                                      | [SYNC.md](SYNC.md)                                                                        |

There is no overlap: an endpoint under `/svc/*` never appears under
`/sync/*`, and a self-hosted sync server serves neither `/svc/*` nor any
website features. In-app "AnkiWeb" messages during sync refer to the sync
server, even against a custom one.
