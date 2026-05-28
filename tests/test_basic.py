import json
import stat
import time
from urllib.parse import parse_qs, urlparse

import pytest

from kroger_shopping import KrogerAuthError, KrogerValidationError
from kroger_shopping.auth import KrogerAuthClient
from kroger_shopping.client import KrogerClient
from kroger_shopping.config import KrogerConfig
from kroger_shopping.models import TokenSet


def make_config(tmp_path):
    return KrogerConfig(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://localhost:8080/callback",
        token_file=str(tmp_path / "tokens.json"),
    )


def test_upc_validation():
    client = KrogerClient.__new__(KrogerClient)  # Avoid needing config
    with pytest.raises(KrogerValidationError):
        client.add_to_cart("12345", 1)  # Too short


def test_quantity_validation():
    client = KrogerClient.__new__(KrogerClient)
    with pytest.raises(KrogerValidationError):
        client.add_to_cart("0001111050434", 0)


def test_authorization_url_contains_required_oauth_params(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))

    url = auth.authorization_url(state="state-token")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.path == "/v1/connect/oauth2/authorize"
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["http://localhost:8080/callback"]
    assert params["state"] == ["state-token"]
    assert "cart.basic:write" in params["scope"][0].split()


def test_token_file_round_trip_preserves_expiry_and_permissions(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))
    expires_at = time.time() + 900
    tokens = TokenSet(
        access_token="access",
        refresh_token="refresh",
        expires_in=1800,
        expires_at=expires_at,
        scope="product.compact cart.basic:write profile.compact",
    )

    auth._save_user_tokens(tokens)
    loaded = auth._load_user_tokens()
    mode = stat.S_IMODE((tmp_path / "tokens.json").stat().st_mode)

    assert loaded.access_token == "access"
    assert loaded.refresh_token == "refresh"
    assert loaded.expires_at == pytest.approx(expires_at)
    assert mode == 0o600


def test_corrupt_token_file_raises_auth_error(tmp_path):
    config = make_config(tmp_path)
    with open(config.token_file, "w") as f:
        f.write("not-json")

    auth = KrogerAuthClient(config)

    with pytest.raises(KrogerAuthError, match="not valid JSON"):
        auth.get_user_access_token()


def test_missing_required_scope_raises_auth_error(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))

    with pytest.raises(KrogerAuthError, match="cart.basic:write"):
        auth._tokens_from_response(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "scope": "product.compact",
            },
            required_scopes=("cart.basic:write",),
            require_refresh=True,
        )


def test_long_tokens_round_trip_without_truncation(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))
    access_token = "access-" + ("a" * 2048)
    refresh_token = "refresh-" + ("r" * 2048)
    tokens = TokenSet(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1800,
        expires_at=time.time() + 900,
        scope="product.compact cart.basic:write profile.compact",
    )

    auth._save_user_tokens(tokens)
    loaded = auth._load_user_tokens()

    assert loaded.access_token == access_token
    assert loaded.refresh_token == refresh_token
    assert len(loaded.access_token) == len(access_token)
    assert len(loaded.refresh_token) == len(refresh_token)


def test_token_response_computes_expires_at_with_safety_skew(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))
    before = time.time()

    tokens = auth._tokens_from_response(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 1800,
            "scope": "product.compact cart.basic:write profile.compact",
        },
        required_scopes=("cart.basic:write",),
        require_refresh=True,
    )

    after = time.time()
    assert before + 1500 <= tokens.expires_at <= after + 1500
    assert tokens.expires_in == 1800


def test_refresh_response_preserves_existing_refresh_token_when_omitted(tmp_path):
    auth = KrogerAuthClient(make_config(tmp_path))

    tokens = auth._tokens_from_response(
        {
            "access_token": "new-access",
            "expires_in": 1800,
            "scope": "product.compact cart.basic:write profile.compact",
        },
        fallback_refresh_token="old-refresh",
        required_scopes=("cart.basic:write",),
        require_refresh=True,
    )

    assert tokens.access_token == "new-access"
    assert tokens.refresh_token == "old-refresh"


def test_expired_saved_user_token_refreshes_and_persists_new_access_token(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    auth = KrogerAuthClient(config)
    auth._save_user_tokens(
        TokenSet(
            access_token="expired-access",
            refresh_token="saved-refresh",
            expires_in=1800,
            expires_at=time.time() - 1,
            scope="product.compact cart.basic:write profile.compact",
        )
    )

    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "fresh-access",
                "expires_in": 1800,
                "scope": "product.compact cart.basic:write profile.compact",
            }

    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        calls.append(data)
        return Response()

    monkeypatch.setattr("kroger_shopping.auth.requests.post", fake_post)

    assert auth.get_user_access_token() == "fresh-access"
    loaded = auth._load_user_tokens()
    assert loaded.access_token == "fresh-access"
    assert loaded.refresh_token == "saved-refresh"
    assert calls == [{"grant_type": "refresh_token", "refresh_token": "saved-refresh"}]


def test_search_uses_app_token(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            calls.append("app")
            return "app-token"

        def get_user_access_token(self):
            calls.append("user")
            return "user-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            assert headers["Authorization"] == "Bearer app-token"
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.search_products("milk") == []
    assert calls == ["app"]


def test_cart_401_refreshes_user_token_once(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    tokens = []

    class Auth:
        def get_user_access_token(self):
            tokens.append("old")
            return "old-token"

        def force_refresh_user_access_token(self):
            tokens.append("new")
            return "new-token"

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = ""

    class Session:
        def __init__(self):
            self.auth_headers = []

        def request(self, method, url, headers=None, **kwargs):
            self.auth_headers.append(headers["Authorization"])
            return Response(401 if len(self.auth_headers) == 1 else 204)

    session = Session()
    client.auth = Auth()
    client.session = session

    assert client.add_to_cart("0001111050434", 1) is True
    assert tokens == ["old", "new"]
    assert session.auth_headers == ["Bearer old-token", "Bearer new-token"]
