"""Short-lived Google OAuth token provider with injected credential location."""

import json
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


SHEETS_WRITE_SCOPES = {
    "https://www.googleapis.com/auth/spreadsheets",
}


class GoogleAuthError(RuntimeError):
    """A sanitized authentication failure with a stable machine code."""

    def __init__(self, code: str, detail: str):
        super().__init__(code + ": " + detail)
        self.code = code


class GoogleAuthTokenProvider:
    """Refresh an authorized-user credential and retain its token in memory only."""

    ENVIRONMENT_VARIABLE = "SEO_GEO_GOOGLE_SHEETS_CREDENTIALS"

    def __init__(
        self,
        credential_path: str | os.PathLike[str],
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.time,
        timeout_seconds: float = 20,
    ):
        if not isinstance(credential_path, (str, os.PathLike)) or not str(credential_path):
            raise GoogleAuthError("AUTH_CONFIG_MISSING", "credential path is required")
        if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.credential_path = Path(credential_path)
        self.opener = opener
        self.clock = clock
        self.timeout_seconds = timeout_seconds
        self._access_token: str | None = None
        self._expires_at = 0.0

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "GoogleAuthTokenProvider":
        path = os.environ.get(cls.ENVIRONMENT_VARIABLE)
        if not path:
            raise GoogleAuthError(
                "AUTH_CONFIG_MISSING",
                cls.ENVIRONMENT_VARIABLE + " is not configured",
            )
        return cls(path, **kwargs)

    def _configuration(self) -> dict[str, Any]:
        try:
            raw = self.credential_path.read_text(encoding="utf8")
            config = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GoogleAuthError("AUTH_CONFIG_INVALID", "credential source is unreadable or invalid") from error
        if not isinstance(config, dict) or config.get("type") not in (None, "authorized_user"):
            raise GoogleAuthError("AUTH_CONFIG_INVALID", "credential source must be an authorized-user credential")

        scopes = config.get("scopes", config.get("scope"))
        if isinstance(scopes, str):
            scopes = scopes.split()
        if (not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes)
                or not SHEETS_WRITE_SCOPES.intersection(scopes)):
            raise GoogleAuthError("AUTH_SCOPE_INSUFFICIENT", "credential requires explicit Google Sheets write scope consent")

        required = ("client_id", "client_secret", "refresh_token")
        if any(not isinstance(config.get(field), str) or not config[field] for field in required):
            raise GoogleAuthError("AUTH_CONFIG_INVALID", "authorized-user credential is incomplete")
        token_uri = config.get("token_uri", "https://oauth2.googleapis.com/token")
        if not isinstance(token_uri, str):
            raise GoogleAuthError("AUTH_CONFIG_INVALID", "token endpoint is invalid")
        parsed = urlparse(token_uri)
        if parsed.scheme != "https" or parsed.hostname not in {"oauth2.googleapis.com", "accounts.google.com"}:
            raise GoogleAuthError("AUTH_CONFIG_INVALID", "token endpoint is not an approved Google OAuth endpoint")
        return {**config, "token_uri": token_uri, "scopes": scopes}

    def _refresh(self) -> str:
        config = self._configuration()
        payload = urlencode({
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "refresh_token": config["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()
        request = Request(
            config["token_uri"],
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode())
        except Exception:
            raise GoogleAuthError("AUTH_REFRESH_FAILED", "Google OAuth refresh failed") from None
        if not isinstance(result, dict):
            raise GoogleAuthError("AUTH_RESPONSE_INVALID", "Google OAuth response is not an object")
        token = result.get("access_token")
        expires_in = result.get("expires_in")
        if not isinstance(token, str) or not token or type(expires_in) not in (int, float) or expires_in <= 0:
            raise GoogleAuthError("AUTH_RESPONSE_INVALID", "Google OAuth response has no usable short-lived token")
        returned_scopes = result.get("scope")
        if returned_scopes is not None and not SHEETS_WRITE_SCOPES.intersection(str(returned_scopes).split()):
            raise GoogleAuthError("AUTH_SCOPE_INSUFFICIENT", "refreshed token lacks Google Sheets write scope")
        self._access_token = token
        self._expires_at = self.clock() + float(expires_in)
        return token

    def __call__(self) -> str:
        if self._access_token is not None and self.clock() < self._expires_at - 60:
            return self._access_token
        return self._refresh()
