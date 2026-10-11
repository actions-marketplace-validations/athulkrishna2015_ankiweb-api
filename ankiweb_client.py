"""AnkiWeb full API client - typed methods for all 41 public /svc/* endpoints.

Decoded from AnkiWeb's own SvelteKit frontend bundle (protobuf-es definitions);
wire format matches the official web app exactly. No ad-hoc parsing.

    client = AnkiWebClient()          # auto-loads .env
    client.login()                    # or AnkiWebClient(cookie=...)
    client.shared_list_mine()         # your shared add-ons & decks
    client.shared_item_info(shared_id=805854302)

Endpoint reference: docs/API.md and docs/ENDPOINTS.md.
Regenerate the schema with: python3 tools/generate_schema.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests

from ankiweb_proto import decode, encode, ProtoError
from ankiweb_schema import (
    ENDPOINTS,
    SCHEMA,
    has_message,
    public_endpoints,
    endpoint,
)
from ankiweb_auth import (
    AuthError,
    default_env_file,
    load_dotenv as auth_load_dotenv,
    login as auth_login,
)

BASE = "https://ankiweb.net"
SHARED = f"{BASE}/shared/"

SCHEMA_REVISION = "2026-10-10"


class AnkiWebError(RuntimeError):
    """Network-level or HTTP error from AnkiWeb."""


class NotFoundError(AnkiWebError):
    """Resource doesn't exist or isn't public."""


class ValidationError(ValueError):
    """Invalid input for a known endpoint."""


_NO_AUTH_PATHS = frozenset({
    "/svc/account/login",
    "/svc/account/signup",
    "/svc/account/reset-password",
    "/svc/account/resend-verification",
    "/svc/account/verify-email",
    "/svc/account/get-account-status",
    "/svc/shared/item-info",
    "/svc/shared/list-addons",
    "/svc/shared/list-decks",
})

_ALIASES = {
    "login": "account_login",
    "list_mine": "shared_list_mine",
    "item_info": "shared_item_info",
}


def _method_name(path: str) -> str:
    parts = [p for p in path.split("/") if p and p not in ("svc", "")]
    if len(parts) == 1:
        return parts[0]
    return "_".join(parts[-2:]).replace("-", "_")


class AnkiWebClient:
    """High-level AnkiWeb API client (41 public endpoints as typed methods)."""

    def __init__(self, username=None, password=None, env_file=None,
                 cookie=None, timeout=30):
        self._cookie = cookie
        self._timeout = timeout
        self._username = username
        self._password = password
        self._env_file = Path(env_file) if env_file else default_env_file()
        auth_load_dotenv(self._env_file)

    def login(self, username=None, password=None) -> str:
        """Authenticate and cache session cookie. Returns the cookie."""
        u = username or self._username or os.environ.get("ANKIWEB_USERNAME", "")
        p = password or self._password or os.environ.get("ANKIWEB_PASSWORD", "")
        if not u or not p:
            raise AuthError("username/password required (ANKIWEB_USERNAME/PASSWORD or explicit)")
        self._cookie = auth_login(u, p, timeout=self._timeout)
        return self._cookie

    def _ensure_auth(self, path: str):
        if path in _NO_AUTH_PATHS:
            return self._cookie
        if not self._cookie:
            self.login()
        return self._cookie

    def logout(self) -> None:
        self._cookie = None

    @property
    def is_authenticated(self) -> bool:
        return self._cookie is not None

    def _request(self, method, path, request_obj=None, response_name=None, query=None) -> dict:
        ep = endpoint(path)
        if ep is None:
            raise AnkiWebError(f"Unknown endpoint: {path}")
        headers = {"Accept": "*/*", "Content-Type": "application/octet-stream"}
        cookie = self._ensure_auth(path)
        if cookie and path not in ("/svc/account/login", "/svc/account/signup",
                "/svc/account/reset-password", "/svc/account/resend-verification"):
            headers["Cookie"] = f"has_auth=1; ankiweb={cookie}"
            headers["Referer"] = f"{BASE}/shared/mine"
        body = b""
        if request_obj is not None and ep["request"]:
            if not has_message(ep["request"]):
                raise ValidationError(f"Request type {ep['request']} not in schema")
            body = encode(ep["request"], request_obj)
        qs = ""
        if query:
            qs = "?" + "&".join(f"{k}={v}" for k, v in query.items())
        url = f"{BASE}{path}{qs}"
        try:
            r = requests.request(method, url, data=body, headers=headers, timeout=self._timeout)
        except requests.RequestException as e:
            raise AnkiWebError(f"Network error: {e}") from e
        if r.status_code in (401, 403):
            self._cookie = None
            raise AnkiWebError("Session expired or invalid credentials")
        if r.status_code == 404:
            raise NotFoundError(f"404 for {path}")
        if r.status_code != 200:
            raise AnkiWebError(f"HTTP {r.status_code}: {r.text[:300]}")
        if response_name is None:
            response_name = ep["response"]
        if not response_name or not has_message(response_name):
            return {"raw": r.content, "endpoint": path}
        try:
            return decode(response_name, r.content)
        except ProtoError as e:
            raise AnkiWebError(f"Decode failed: {e}") from e

    def _call(self, path, request=None, query=None, response_as=None) -> dict:
        ep = endpoint(path)
        if ep is None:
            raise AnkiWebError(f"Unknown endpoint: {path}")
        req_name = ep["request"]
        if req_name and request is None:
            raise ValidationError(f"{path} requires a request object ({req_name})")
        if req_name and not has_message(req_name):
            raise ValidationError(f"Request type {req_name} not in schema")
        return self._request(method=ep["method"], path=path, request_obj=request,
                             response_name=response_as or ep["response"], query=query)
    # ================= account (12) =================

    def account_login(self, username: str, password: str) -> dict:
        """POST /svc/account/login (no session). -> {status, token}."""
        return self._call("/svc/account/login", {"username": username, "password": password})

    def account_check_terms(self) -> dict:
        """POST /svc/account/check-terms -> {needs_to_confirm}."""
        return self._call("/svc/account/check-terms", {})

    def account_confirm_terms(self, agree_to_terms: bool = True) -> dict:
        """POST /svc/account/confirm-terms (empty response)."""
        return self._call("/svc/account/confirm-terms", {"agree_to_terms": agree_to_terms})

    def account_get_account_status(self) -> dict:
        """POST /svc/account/get-account-status -> {logged_in, redirect_to?}."""
        return self._call("/svc/account/get-account-status", {})

    def account_get_settings(self) -> dict:
        """POST /svc/account/get-settings -> {current_email}."""
        return self._call("/svc/account/get-settings", {})

    def account_update_settings(self, current_password="", new_password="", new_email="") -> dict:
        """POST /svc/account/update-settings -> {result enum}."""
        return self._call("/svc/account/update-settings", {
            "current_password": current_password, "new_password": new_password,
            "new_email": new_email})

    def account_signup(self, username: str, password: str) -> dict:
        """POST /svc/account/signup (no session) -> {status, ankiuser_login_token?}."""
        return self._call("/svc/account/signup", {"username": username, "password": password})

    def account_verify_email(self, token="") -> dict:
        """POST /svc/account/verify-email -> {token_verified, sending_status}."""
        return self._call("/svc/account/verify-email", {"token": token} if token else {})

    def account_resend_verification(self, hkey="") -> dict:
        """POST /svc/account/resend-verification -> {throttled}."""
        return self._call("/svc/account/resend-verification", {"hkey": hkey} if hkey else {})

    def account_reset_password(self, email_to="", check_token="", new_password=None) -> dict:
        """POST /svc/account/reset-password -> {send_email, token_ok, set_new_password}."""
        req = {"email_to": email_to, "check_token": check_token}
        if new_password is not None:
            req["new_password"] = new_password
        return self._call("/svc/account/reset-password", req)

    def account_total_media(self) -> dict:
        """POST /svc/account/total-media -> {total_bytes}."""
        return self._call("/svc/account/total-media", {})

    def account_remove_account(self, current_password: str) -> dict:
        """POST /svc/account/remove-account - IRREVERSIBLE -> {status, media_removed}."""
        return self._call("/svc/account/remove-account", {"current_password": current_password})

    # ================= decks (8) =================

    def decks_create_deck(self, name: str) -> dict:
        """POST /svc/decks/create-deck (empty response)."""
        return self._call("/svc/decks/create-deck", {"name": name})

    def decks_deck_list_info(self, minutes_west_of_utc=None) -> dict:
        """POST /svc/decks/deck-list-info -> {top_node, current_deck_id, sizes}."""
        req = {} if minutes_west_of_utc is None else {"minutes_west_of_utc": minutes_west_of_utc}
        return self._call("/svc/decks/deck-list-info", req)

    def decks_deck_share_info(self, deck_id: int) -> dict:
        """POST /svc/decks/deck-share-info -> {metadata, is_large_user, share_count}."""
        return self._call("/svc/decks/deck-share-info", {"deck_id": deck_id})

    def decks_deck_share(self, metadata: dict, confirm_copyright: bool = True) -> dict:
        """POST /svc/decks/deck-share (empty response)."""
        return self._call("/svc/decks/deck-share",
                          {"metadata": metadata, "confirm_copyright": confirm_copyright})

    def decks_deck_share_state(self) -> dict:
        """POST /svc/decks/deck-share-state -> {state, shared_id?}."""
        return self._call("/svc/decks/deck-share-state", {})

    def decks_rename_deck(self, deck_id: int, new_name: str) -> dict:
        """POST /svc/decks/rename-deck -> {error}."""
        return self._call("/svc/decks/rename-deck", {"deck_id": deck_id, "new_name": new_name})

    def decks_remove_deck(self, deck_id: int) -> dict:
        """POST /svc/decks/remove-deck (empty response)."""
        return self._call("/svc/decks/remove-deck", {"deck_id": deck_id})

    def decks_select_deck(self, deck_id: int) -> dict:
        """POST /svc/decks/select-deck (empty response)."""
        return self._call("/svc/decks/select-deck", {"deck_id": deck_id})

    # ================= editor (3) + search (1) =================

    def editor_get_info_for_adding(self) -> dict:
        """POST /svc/editor/get-info-for-adding -> {notetypes[], decks[], fields[]...}."""
        return self._call("/svc/editor/get-info-for-adding", {})

    def editor_get_note_info(self, note_id: int) -> dict:
        """POST /svc/editor/get-note-info -> {fields[], notetype_fields[], tags}."""
        return self._call("/svc/editor/get-note-info", {"note_id": note_id})

    def editor_get_notetype_fields(self, notetype_id: int) -> dict:
        """POST /svc/editor/get-notetype-fields -> {fields[]}."""
        return self._call("/svc/editor/get-notetype-fields", {"notetype_id": notetype_id})

    def editor_add_or_update(self, request: dict) -> dict:
        """POST /svc/editor/add-or-update. See SCHEMA['EditorAddOrUpdateRequest']."""
        return self._call("/svc/editor/add-or-update", request)

    def search_search(self, search: str) -> dict:
        """POST /svc/search/search -> {notes[], error}."""
        return self._call("/svc/search/search", {"search": search})
    # ================= shared: public reads (5) =================

    def shared_item_info(self, shared_id=None, query=None) -> dict:
        """GET /svc/shared/item-info?sharedId=<id> (no auth) -> {available, missing, access_denied}."""
        q = dict(query or {})
        if shared_id is not None:
            q.setdefault("sharedId", shared_id)
        if "sharedId" not in q:
            raise ValidationError("item-info requires query={'sharedId': <id>}")
        return self._call("/svc/shared/item-info", query=q)

    def item_info(self, addon_id: int) -> dict:
        """Alias of shared_item_info(shared_id=addon_id)."""
        return self.shared_item_info(shared_id=addon_id)

    def shared_list_addons(self) -> dict:
        """GET /svc/shared/list-addons (no auth) -> {rows[], user_upload_status}."""
        return self._call("/svc/shared/list-addons")

    def shared_list_decks(self) -> dict:
        """GET /svc/shared/list-decks (no auth) -> {rows[]}."""
        return self._call("/svc/shared/list-decks")

    def shared_items_by_author(self, shared_id: int) -> dict:
        """POST /svc/shared/items-by-author -> {items[{shared_id, title}]}."""
        return self._call("/svc/shared/items-by-author", {"shared_id": shared_id})

    def shared_get_addon_info(self, addon_id: int) -> dict:
        """POST /svc/shared/get-addon-info -> {addon{...}}."""
        return self._call("/svc/shared/get-addon-info", {"addon_id": addon_id})

    # ================= shared: account reads/writes (7) =================

    def shared_list_mine(self) -> dict:
        """POST /svc/shared/list-mine (auth) -> {items[], reviews[], expired_decks[]}."""
        return self._call("/svc/shared/list-mine", {})

    def list_mine(self) -> dict:
        """Alias of shared_list_mine()."""
        return self.shared_list_mine()

    def shared_remove_item(self, shared_id: int) -> dict:
        """POST /svc/shared/remove-item (empty response)."""
        return self._call("/svc/shared/remove-item", {"shared_id": shared_id})

    def shared_get_own_review(self, shared_id: int) -> dict:
        """POST /svc/shared/get-own-review -> {review, shared_item_title, support_page?}."""
        return self._call("/svc/shared/get-own-review", {"shared_id": shared_id})

    def shared_set_own_review(self, shared_id: int, review: dict) -> dict:
        """POST /svc/shared/set-own-review (empty response). review={body, thumbs_up}."""
        return self._call("/svc/shared/set-own-review",
                          {"shared_id": shared_id, "review": review})

    def shared_reply_to_review(self, shared_id: int, hash: int, body: str) -> dict:
        """POST /svc/shared/reply-to-review (empty response)."""
        return self._call("/svc/shared/reply-to-review",
                          {"shared_Id": shared_id, "hash": hash, "body": body})

    def shared_report_copyright(self, shared_id: int) -> dict:
        """POST /svc/shared/report-copyright (empty response)."""
        return self._call("/svc/shared/report-copyright", {"shared_id": shared_id})

    def shared_upload_addon(self, info: dict, file: dict | None = None) -> dict:
        """POST /svc/shared/upload-addon -> {addon_id}. Also see upload.py / Action."""
        req = {"info": info}
        if file is not None:
            req["file"] = file
        return self._call("/svc/shared/upload-addon", req)

    # ================= study (4) =================

    def study_get_deck_limits(self) -> dict:
        """POST /svc/study/get-deck-limits -> {new, review, new_cards_ignore_review_limit, error}."""
        return self._call("/svc/study/get-deck-limits", {})

    def study_set_deck_limits(self, new: int, review: int,
                              new_cards_ignore_review_limit: bool = False) -> dict:
        """POST /svc/study/set-deck-limits (empty response)."""
        return self._call("/svc/study/set-deck-limits", {
            "new": new, "review": review,
            "new_cards_ignore_review_limit": new_cards_ignore_review_limit})

    def study_study_cards(self, answer=None, next_card_id=None) -> dict:
        """POST /svc/study/study-cards -> {sched_ver, cards[], new/learn/review_count}."""
        req = {}
        if answer is not None:
            req["answer"] = answer
        if next_card_id is not None:
            req["next_card_id"] = next_card_id
        return self._call("/svc/study/study-cards", req)

    def study_upgrade_scheduler(self, v3: bool = True) -> dict:
        """POST /svc/study/upgrade-scheduler (empty response)."""
        return self._call("/svc/study/upgrade-scheduler", {"v3": v3})

    def __getattr__(self, name: str):
        if name in _ALIASES:
            return getattr(self, _ALIASES[name])
        for ep in public_endpoints():
            if _method_name(ep["path"]) == name:
                path = ep["path"]

                def caller(request=None, *, query=None, response_as=None, _path=path):
                    return self._call(_path, request, query=query, response_as=response_as)

                caller.__name__ = name
                caller.__doc__ = f"{ep['method']} {ep['path']} req={ep['request']} resp={ep['response']}"
                return caller
        raise AttributeError(f"'AnkiWebClient' has no method '{name}'")


_client = None


def get_client(**kwargs) -> AnkiWebClient:
    """Get or create the default client (uses .env if present)."""
    global _client
    if _client is None:
        _client = AnkiWebClient(**kwargs)
    return _client


__all__ = ["AnkiWebClient", "get_client", "AnkiWebError", "NotFoundError",
           "AuthError", "ValidationError", "SCHEMA", "ENDPOINTS",
           "SCHEMA_REVISION", "public_endpoints", "endpoint"]
