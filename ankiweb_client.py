"""AnkiWeb unified client — schema-driven, covers all 41 public /svc/* endpoints.

Generated from AnkiWeb's own SvelteKit frontend bundle (protobuf-es definitions).
No ad-hoc parsing; wire format matches the official web app exactly.

Usage:
    client = AnkiWebClient()                    # auto-loads .env
    client.login()                              # or pass credentials
    client.list_mine()                          # your shared add-ons & decks
    client.item_info(805854302)                 # public metadata
    # ... all 41 endpoints available as methods
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Union

import requests

from ankiweb_proto import decode, encode, ProtoError
from ankiweb_schema import (
    ENDPOINTS,
    SCHEMA,
    has_message,
    public_endpoints,
    endpoint,
)
from ankiweb_auth import login as auth_login, load_dotenv as auth_load_dotenv, AuthError

BASE = "https://ankiweb.net"
SHARED = f"{BASE}/shared/"

# ---- exceptions ----


class AnkiWebError(RuntimeError):
    """Network-level or HTTP error from AnkiWeb."""


class NotFoundError(AnkiWebError):
    """Resource doesn't exist or isn't public."""


class ValidationError(ValueError):
    """Invalid input for a known endpoint."""


# ---- helpers ----

_FIELD_RE = re.compile(r"[A-Z][a-z]+|[A-Z]+(?=[A-Z]|$)")


def _to_snake(name: str) -> str:
    """AccountLoginResponse -> account_login_response"""
    return "_".join(w.lower() for w in _FIELD_RE.findall(name))


def _method_name(path: str) -> str:
    """/svc/account/login -> login; /svc/shared/list-mine -> list_mine"""
    parts = [p for p in path.split("/") if p and p not in ("svc", "")]
    if len(parts) == 1:
        return parts[0]
    name = "_".join(parts[-2:])  # account_login, shared_list_mine
    return name.replace("-", "_")  # account_check_terms -> account_check_terms


# ---- client ----

class AnkiWebClient:
    """High-level AnkiWeb API client.

    All 41 public endpoints are callable as methods after login.
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        env_file: str | Path | None = None,
        cookie: str | None = None,
        timeout: int = 30,
    ):
        """
        Args:
            username: AnkiWeb username/email. Defaults to $ANKIWEB_USERNAME.
            password: AnkiWeb password. Defaults to $ANKIWEB_PASSWORD.
            env_file: Path to .env (gitignored). Defaults to ./<repo>/.env.
            cookie: Pre-fetched `ankiweb` session cookie (skips login).
            timeout: Request timeout in seconds.
        """
        self._cookie = cookie
        self._timeout = timeout
        self._username = username
        self._password = password
        # default env_file to .env in the package directory
        self._env_file = Path(env_file) if env_file else (Path(__file__).parent / ".env")

        # auto-load .env for credential fallback
        auth_load_dotenv(self._env_file)

    # --- session ---

    def login(self, username: str | None = None, password: str | None = None) -> str:
        """Authenticate and cache session cookie. Returns the cookie."""
        u = username or self._username or os.environ.get("ANKIWEB_USERNAME", "")
        p = password or self._password or os.environ.get("ANKIWEB_PASSWORD", "")
        if not u or not p:
            raise AuthError("username/password required (set ANKIWEB_USERNAME/PASSWORD or pass explicitly)")
        self._cookie = auth_login(u, p, timeout=self._timeout)
        return self._cookie

    def _ensure_auth(self) -> str:
        if not self._cookie:
            self.login()
        return self._cookie

    def logout(self) -> None:
        """Clear cached cookie."""
        self._cookie = None

    @property
    def is_authenticated(self) -> bool:
        return self._cookie is not None

    # --- generic transport ---

    def _request(
        self,
        method: str,
        path: str,
        request_obj: dict | None = None,
        response_name: str | None = None,
        query: dict | None = None,
    ) -> dict:
        """Low-level: encode request -> POST/GET -> decode response."""
        ep = endpoint(path)
        if ep is None:
            raise AnkiWebError(f"Unknown endpoint: {path}")

        needs_auth = method == "POST" and ep["method"] == "POST"
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
        }
        if needs_auth:
            cookie = self._ensure_auth()
            headers["Cookie"] = f"has_auth=1; ankiweb={cookie}"
            headers["Referer"] = f"{BASE}/shared/mine"

        # encode request body
        body = b""
        if request_obj is not None and ep["request"]:
            if not has_message(ep["request"]):
                raise ValidationError(f"Request type {ep['request']} not in schema")
            body = encode(ep["request"], request_obj)

        # query string (GET endpoints)
        qs = ""
        if query:
            qs = "?" + "&".join(f"{k}={v}" for k, v in query.items())
        elif method == "GET" and ep.get("query"):
            # no query provided but endpoint expects some - user must supply
            pass

        url = f"{BASE}{path}{qs}"
        try:
            r = requests.request(
                method, url, data=body, headers=headers, timeout=self._timeout
            )
        except requests.RequestException as e:
            raise AnkiWebError(f"Network error: {e}") from e

        if r.status_code in (401, 403):
            self._cookie = None  # invalidate
            raise AnkiWebError("Session expired or invalid credentials")

        if r.status_code == 404:
            raise NotFoundError(f"404 for {path}")

        if r.status_code != 200:
            raise AnkiWebError(f"HTTP {r.status_code}: {r.text[:300]}")

        # decode response
        if response_name is None:
            response_name = ep["response"]
        if not response_name or not has_message(response_name):
            return {"raw": r.content, "endpoint": path}
        try:
            return decode(response_name, r.content)
        except ProtoError as e:
            raise AnkiWebError(f"Decode failed: {e}") from e

    # --- dynamic endpoint methods ---

    def __getattr__(self, name: str):
        """Allow dot-access to endpoints: client.list_mine()"""
        for ep in public_endpoints():
            if _method_name(ep["path"]) == name:
                return self._make_endpoint_method(ep)
        raise AttributeError(f"'AnkiWebClient' has no method '{name}'")

    def _make_endpoint_method(self, ep: dict):
        """Return a callable for this endpoint."""
        method = ep["method"]
        path = ep["path"]
        req_name = ep["request"]
        resp_name = ep["response"]
        query_params = ep.get("query", [])

        def caller(
            request: dict | None = None,
            *,
            query: dict | None = None,
            response_as: str | None = None,
        ) -> dict:
            # basic validation
            if req_name and request is None:
                raise ValidationError(f"{path} requires a request object ({req_name})")
            if req_name and not has_message(req_name):
                raise ValidationError(f"Request type {req_name} not in schema")
            return self._request(
                method=method,
                path=path,
                request_obj=request,
                response_name=response_as or resp_name,
                query=query,
            )

        caller.__name__ = _method_name(path)
        caller.__doc__ = f"{method} {path}  req={req_name} resp={resp_name}"
        return caller


# ---- convenience: module-level singleton ----

_client: AnkiWebClient | None = None


def get_client(**kwargs) -> AnkiWebClient:
    """Get or create the default client (uses .env if present)."""
    global _client
    if _client is None:
        _client = AnkiWebClient(**kwargs)
    return _client


# ---- re-export schema for reference ----

__all__ = [
    "AnkiWebClient",
    "get_client",
    "AnkiWebError",
    "NotFoundError",
    "AuthError",
    "ValidationError",
    "SCHEMA",
    "ENDPOINTS",
    "public_endpoints",
    "endpoint",
]