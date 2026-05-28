import os
import json
import time
import base64
import secrets
import threading
import fcntl
import requests
from contextlib import contextmanager
from urllib.parse import urlencode
from typing import Optional

from .config import KrogerConfig
from .models import TokenSet
from .exceptions import KrogerAuthError


class KrogerAuthClient:
    """Handles OAuth2 authentication and token management for Kroger."""

    AUTH_URL = "https://api.kroger.com/v1/connect/oauth2/authorize"
    TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
    USER_SCOPES = ("product.compact", "cart.basic:write", "profile.compact")
    APP_SCOPES = ("product.compact",)
    EXPIRY_SKEW_SECONDS = 300

    def __init__(self, config: KrogerConfig):
        self.config = config
        self._user_tokens: Optional[TokenSet] = None
        self._app_tokens: Optional[TokenSet] = None
        self._lock = threading.Lock()

    @property
    def _basic_auth_header(self) -> str:
        encoded = base64.b64encode(
            f"{self.config.client_id}:{self.config.client_secret}".encode()
        ).decode()
        return f"Basic {encoded}"

    def authorization_url(self, state: Optional[str] = None) -> str:
        """Build the user authorization URL for manual login flows."""
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.USER_SCOPES),
            "state": state or secrets.token_urlsafe(24),
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def get_valid_access_token(self) -> str:
        """Get a valid user access token, refreshing if necessary."""
        return self.get_user_access_token()

    def get_user_access_token(self) -> str:
        if self._user_tokens is None:
            self._user_tokens = self._load_user_tokens()

        if self._is_valid(self._user_tokens):
            return self._user_tokens.access_token

        if self._user_tokens and self._user_tokens.refresh_token:
            return self.refresh_user_access_token()

        raise KrogerAuthError(
            "No valid Kroger user tokens available. Run /kroger login, then /kroger code <code>."
        )

    def get_app_access_token(self) -> str:
        """Get an application token for product search/read operations."""
        if self._is_valid(self._app_tokens):
            return self._app_tokens.access_token

        resp = self._post_token(
            {
                "grant_type": "client_credentials",
                "scope": " ".join(self.APP_SCOPES),
            }
        )
        self._app_tokens = self._tokens_from_response(resp.json())
        return self._app_tokens.access_token

    def refresh_user_access_token(self) -> str:
        with self._lock, self._token_file_lock():
            self._user_tokens = self._load_user_tokens()
            if self._is_valid(self._user_tokens):
                return self._user_tokens.access_token

            if not self._user_tokens or not self._user_tokens.refresh_token:
                raise KrogerAuthError(
                    "No refresh token available. Run /kroger login, then /kroger code <code>."
                )

            return self._refresh_access_token(self._user_tokens.refresh_token)

    def force_refresh_user_access_token(self) -> str:
        """Refresh a user token even if the local expiry says it is valid."""
        with self._lock, self._token_file_lock():
            self._user_tokens = self._load_user_tokens()
            if not self._user_tokens or not self._user_tokens.refresh_token:
                raise KrogerAuthError(
                    "No refresh token available. Run /kroger login, then /kroger code <code>."
                )

            return self._refresh_access_token(self._user_tokens.refresh_token)

    def exchange_code_for_tokens(self, code: str) -> TokenSet:
        """Exchange an authorization code for tokens."""
        resp = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code.strip(),
                "redirect_uri": self.config.redirect_uri,
            }
        )
        tokens = self._tokens_from_response(
            resp.json(),
            required_scopes=("cart.basic:write",),
            require_refresh=True,
        )
        with self._lock, self._token_file_lock():
            self._save_user_tokens(tokens)
        return tokens

    def has_valid_user_tokens(self) -> bool:
        if self._user_tokens is None:
            self._user_tokens = self._load_user_tokens()
        return self._is_valid(self._user_tokens)

    def clear_user_tokens(self):
        self._user_tokens = None
        try:
            os.remove(self.config.token_file)
        except FileNotFoundError:
            pass

    @contextmanager
    def _token_file_lock(self):
        lock_file = f"{self.config.token_file}.lock"
        directory = os.path.dirname(os.path.abspath(lock_file))
        os.makedirs(directory, exist_ok=True)
        with open(lock_file, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _refresh_access_token(self, refresh_token: str) -> str:
        resp = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )
        new_tokens = self._tokens_from_response(
            resp.json(),
            fallback_refresh_token=refresh_token,
            required_scopes=("cart.basic:write",),
            require_refresh=True,
        )
        self._save_user_tokens(new_tokens)
        return new_tokens.access_token

    def _load_user_tokens(self) -> Optional[TokenSet]:
        if not os.path.exists(self.config.token_file):
            return None
        try:
            with open(self.config.token_file) as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise KrogerAuthError(
                f"Token file is not valid JSON: {self.config.token_file}"
            ) from exc
        except OSError as exc:
            raise KrogerAuthError(
                f"Could not read token file {self.config.token_file}: {exc}"
            ) from exc

        return self._tokens_from_response(data, require_refresh=True)

    def _save_user_tokens(self, tokens: TokenSet):
        data = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "expires_at": tokens.expires_at,
            "scope": tokens.scope,
        }
        directory = os.path.dirname(os.path.abspath(self.config.token_file))
        os.makedirs(directory, exist_ok=True)

        temp_file = f"{self.config.token_file}.tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(temp_file, 0o600)
        os.replace(temp_file, self.config.token_file)
        self._user_tokens = tokens

    def _post_token(self, data: dict) -> requests.Response:
        resp = requests.post(
            self.TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": self._basic_auth_header,
            },
            data=data,
            timeout=20,
        )

        if resp.status_code != 200:
            raise KrogerAuthError(
                f"Token request failed with status {resp.status_code}: {self._safe_error_body(resp)}"
            )

        return resp

    def _tokens_from_response(
        self,
        data: dict,
        fallback_refresh_token: Optional[str] = None,
        required_scopes: tuple = (),
        require_refresh: bool = False,
    ) -> TokenSet:
        access_token = data.get("access_token")
        if not access_token:
            raise KrogerAuthError("Token response did not include an access_token")

        refresh_token = data.get("refresh_token", fallback_refresh_token)
        if require_refresh and not refresh_token:
            raise KrogerAuthError("Token response did not include a refresh_token")

        scope = data.get("scope")
        self._validate_scopes(scope, required_scopes)

        expires_in = int(data.get("expires_in", 1800))
        expires_at = data.get("expires_at")
        if expires_at is None:
            expires_at = time.time() + expires_in - self.EXPIRY_SKEW_SECONDS

        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=data.get("token_type", "bearer"),
            expires_in=expires_in,
            expires_at=float(expires_at),
            scope=scope,
        )

    def _validate_scopes(self, scope: Optional[str], required_scopes: tuple):
        if not scope or not required_scopes:
            return

        granted = set(scope.split())
        missing = set(required_scopes) - granted
        if missing:
            raise KrogerAuthError(
                "Kroger token is missing required scope(s): "
                + ", ".join(sorted(missing))
            )

    def _is_valid(self, tokens: Optional[TokenSet]) -> bool:
        return bool(
            tokens
            and tokens.access_token
            and tokens.expires_at
            and time.time() < tokens.expires_at
        )

    def _safe_error_body(self, resp: requests.Response) -> str:
        body = resp.text[:1000] if resp.text else "<empty response>"
        redactions = [
            self.config.client_id,
            self.config.client_secret,
        ]
        for value in redactions:
            if value:
                body = body.replace(value, "[redacted]")
        return body
