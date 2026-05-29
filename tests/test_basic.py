import json
import stat
import time
from urllib.parse import parse_qs, urlparse

import pytest

from kroger_shopping import KrogerAuthError, KrogerValidationError
from kroger_shopping import parsers, recommendations, unit_pricing, validation
from kroger_shopping.auth import KrogerAuthClient
from kroger_shopping.client import KrogerClient
from kroger_shopping.config import KrogerConfig
from kroger_shopping.models import (
    CartItem,
    CartModality,
    PreferenceProfile,
    Product,
    ProductDetail,
    ProductFulfillment,
    ProductNutritionInformation,
    TokenSet,
)


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
    with pytest.raises(KrogerValidationError, match="whole number"):
        client.add_to_cart("0001111050434", 1.5)
    with pytest.raises(KrogerValidationError, match="whole number"):
        client.add_to_cart("0001111050434", True)


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


def test_config_defaults_to_nora_csp(tmp_path):
    config = make_config(tmp_path)

    assert config.default_location_id == "02100998"
    assert config.default_fulfillment is ProductFulfillment.CSP


def test_config_from_env_parses_default_fulfillment(monkeypatch, tmp_path):
    monkeypatch.setenv("KROGER_CLIENT_ID", "client-id")
    monkeypatch.setenv("KROGER_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("KROGER_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("KROGER_DEFAULT_LOCATION_ID", "01400943")
    monkeypatch.setenv("KROGER_DEFAULT_FULFILLMENT", "ais")

    config = KrogerConfig.from_env()

    assert config.default_location_id == "01400943"
    assert config.default_fulfillment is ProductFulfillment.AIS


def test_config_from_env_rejects_invalid_default_fulfillment(monkeypatch):
    monkeypatch.setenv("KROGER_CLIENT_ID", "client-id")
    monkeypatch.setenv("KROGER_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("KROGER_DEFAULT_FULFILLMENT", "pickup")

    with pytest.raises(ValueError, match="KROGER_DEFAULT_FULFILLMENT"):
        KrogerConfig.from_env()


def test_search_products_defaults_to_nora_csp(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append(kwargs["params"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.search_products("milk") == []
    assert calls == [
        {
            "filter.term": "milk",
            "filter.limit": 10,
            "filter.locationId": "02100998",
            "filter.fulfillment": "csp",
        }
    ]


def test_search_products_serializes_multiple_fulfillment_enums(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append(kwargs["params"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.search_products(
        "milk",
        fulfillment=[ProductFulfillment.AIS, ProductFulfillment.CSP],
    ) == []
    assert calls[0]["filter.fulfillment"] == "ais,csp"


def test_search_products_validates_limit_before_request(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="between 1 and 50"):
        client.search_products("milk", limit=0)

    with pytest.raises(KrogerValidationError, match="between 1 and 50"):
        client.search_products("milk", limit=51)

    with pytest.raises(KrogerValidationError, match="whole number"):
        client.search_products("milk", limit=1.5)

    with pytest.raises(KrogerValidationError, match="whole number"):
        client.search_products("milk", limit=True)


def test_search_products_validates_location_id_before_request(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Location ID"):
        client.search_products("milk", location_id="1400943")

    with pytest.raises(KrogerValidationError, match="Location ID"):
        client.search_products("milk", location_id="abcdefgh")


def test_search_products_validates_fulfillment_before_request(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="ProductFulfillment enum"):
        client.search_products("milk", fulfillment="pickup")

    with pytest.raises(KrogerValidationError, match="ProductFulfillment enum"):
        client.search_products("milk", fulfillment="csp")


def test_search_products_strips_and_normalizes_filters(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append(kwargs["params"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.search_products(
        "  milk  ",
        limit=50,
        location_id=" 01400943 ",
        fulfillment=ProductFulfillment.CSP,
        brand=" Kroger ",
    ) == []
    assert calls == [
        {
            "filter.term": "milk",
            "filter.limit": 50,
            "filter.locationId": "01400943",
            "filter.fulfillment": "csp",
            "filter.brand": "Kroger",
        }
    ]


def test_get_product_detail_uses_product_id_and_maps_rich_fields(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "data": {
                    "upc": "0001111040101",
                    "productId": "0001111040101",
                    "description": "Kroger Vitamin D Whole Milk Gallon",
                    "brand": "Kroger",
                    "categories": ["Dairy"],
                    "countryOrigin": "United States",
                    "snapEligible": True,
                    "organicClaimName": "ORGANIC CLAIM AND PRINTED ON PACKAGE",
                    "allergensDescription": "Contains Milk.",
                    "allergens": [
                        {"name": "Milk and its Derivatives", "levelOfContainmentName": "Contains"}
                    ],
                    "warnings": "KEEP REFRIGERATED",
                    "restrictions": {"minimumOrderQuantity": 1},
                    "items": [
                        {
                            "itemId": "0001111040101",
                            "size": "1 gal",
                            "soldBy": "UNIT",
                            "price": {"regular": 3.29},
                            "nationalPrice": {"regular": 3.49},
                            "favorite": True,
                            "fulfillment": {
                                "curbside": True,
                                "delivery": False,
                                "instore": True,
                                "shiptohome": False,
                            },
                            "inventory": {"stockLevel": "HIGH"},
                        }
                    ],
                    "images": [{"perspective": "front"}],
                    "aisleLocations": [{"description": "Dairy"}],
                    "temperature": {"indicator": "Refrigerated"},
                    "nutritionInformation": {
                        "ingredientStatement": "Milk, high fructose corn syrup",
                        "servingSize": {"description": "8 fl oz"},
                        "nutrients": [
                            {
                                "code": "CA",
                                "displayName": "Calcium",
                                "quantity": 290,
                                "unitOfMeasure": {"abbreviation": "mg"},
                                "percentDailyIntake": 25,
                            }
                        ],
                        "nutritionalRating": "73",
                    },
                }
            }

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url, headers, kwargs))
            return Response()

    client.auth = Auth()
    client.session = Session()

    detail = client.get_product_detail("0001111040101", location_id="01400943")

    assert detail.product_id == "0001111040101"
    assert detail.description == "Kroger Vitamin D Whole Milk Gallon"
    assert detail.brand == "Kroger"
    assert detail.categories == ["Dairy"]
    assert detail.items[0].size == "1 gal"
    assert detail.items[0].price == {"regular": 3.29}
    assert detail.items[0].national_price == {"regular": 3.49}
    assert detail.items[0].favorite is True
    assert detail.items[0].fulfillment.curbside is True
    assert detail.items[0].fulfillment.delivery is False
    assert detail.items[0].fulfillment.instore is True
    assert detail.items[0].fulfillment.shiptohome is False
    assert detail.items[0].inventory.stock_level == "HIGH"
    assert detail.images == [{"perspective": "front"}]
    assert detail.aisle_locations == [{"description": "Dairy"}]
    assert detail.temperature == {"indicator": "Refrigerated"}
    assert detail.country_origin == "United States"
    assert detail.snap_eligible is True
    assert detail.organic_claim_name == "ORGANIC CLAIM AND PRINTED ON PACKAGE"
    assert detail.allergens_description == "Contains Milk."
    assert detail.allergens[0].name == "Milk and its Derivatives"
    assert detail.allergens[0].level_of_containment_name == "Contains"
    assert detail.warnings == "KEEP REFRIGERATED"
    assert detail.restrictions == {"minimumOrderQuantity": 1}
    assert detail.nutrition_information[0].ingredient_statement == "Milk, high fructose corn syrup"
    assert detail.nutrition_information[0].serving_size == {"description": "8 fl oz"}
    assert detail.nutrition_information[0].nutrients[0].display_name == "Calcium"
    assert detail.nutrition_information[0].nutrients[0].percent_daily_intake == 25
    ingredients, fields = client._extract_ingredient_text(detail.raw, detail.nutrition_information)
    assert "high fructose corn syrup" in ingredients
    assert fields == ["nutrition_information[0].ingredient_statement"]
    assert detail.raw["upc"] == "0001111040101"

    method, url, headers, kwargs = calls[0]
    assert method == "GET"
    assert url == "https://api.kroger.com/v1/products/0001111040101"
    assert headers["Authorization"] == "Bearer app-token"
    assert kwargs["params"] == {"filter.locationId": "01400943"}


def test_product_detail_parses_list_nutrition_and_documented_stock_levels():
    client = KrogerClient.__new__(KrogerClient)

    detail = client._product_detail_from_response(
        {
            "upc": "0001111040101",
            "productId": "0001111040101",
            "description": "Test",
            "items": [
                {"inventory": {"stockLevel": "LOW"}},
                {"inventory": {"stockLevel": "TEMPORARILY_OUT_OF_STOCK"}},
            ],
            "nutritionInformation": [
                {"ingredientStatement": "Water", "nutritionalRating": "40"}
            ],
        }
    )

    assert detail.nutrition_information[0].ingredient_statement == "Water"
    assert detail.items[0].inventory.stock_level == "LOW"
    assert detail.items[1].inventory.stock_level == "TEMPORARILY_OUT_OF_STOCK"


def test_ingredient_extraction_prefers_typed_nutrition_statement_over_raw_fallback():
    client = KrogerClient.__new__(KrogerClient)
    typed = [ProductNutritionInformation(ingredient_statement="Milk, red 40")]
    raw = {"food": {"ingredients": "Milk, high fructose corn syrup"}}

    ingredients, fields = client._extract_ingredient_text(raw, typed)

    assert ingredients == "Milk, red 40"
    assert fields == ["nutrition_information[0].ingredient_statement"]


def test_openapi_contract_values_match_client_validators():
    with open("references/openapi/kroger-products.openapi.json", encoding="utf-8") as fh:
        products = json.load(fh)
    with open("references/openapi/kroger-cart.openapi.json", encoding="utf-8") as fh:
        cart = json.load(fh)
    with open("references/openapi/kroger-location.openapi.json", encoding="utf-8") as fh:
        locations = json.load(fh)

    assert "/v1/products" in products["paths"]
    assert "/v1/products/{id}" in products["paths"]
    assert "/v1/cart/add" in cart["paths"]
    assert "/v1/locations" in locations["paths"]

    search_params = {
        parameter["name"]: parameter
        for parameter in products["paths"]["/v1/products"]["get"]["parameters"]
    }
    assert search_params["filter.fulfillment"]["schema"]["enum"] == [item.value for item in ProductFulfillment]
    assert search_params["filter.limit"]["schema"]["minimum"] == KrogerClient.MIN_PRODUCT_SEARCH_LIMIT
    assert search_params["filter.limit"]["schema"]["maximum"] == KrogerClient.MAX_PRODUCT_SEARCH_LIMIT

    product_id_schema = products["components"]["schemas"]["productId"]
    assert product_id_schema["minLength"] == 13
    assert product_id_schema["maxLength"] == 13

    modality = cart["components"]["schemas"]["cart.cartItemModel"]["properties"]["modality"]
    assert modality["enum"] == [item.value for item in CartModality]


def test_openapi_product_item_response_values_match_models():
    with open("references/openapi/kroger-products.openapi.json", encoding="utf-8") as fh:
        products = json.load(fh)

    schemas = products["components"]["schemas"]
    fulfillment_fields = schemas["products.productItemFulfillmentModel"]["properties"]
    inventory_stock = schemas["products.productItemInventoryModel"]["properties"]["stockLevel"]

    assert list(fulfillment_fields) == ["curbside", "delivery", "instore", "shiptohome"]
    assert inventory_stock["enum"] == ["HIGH", "LOW", "TEMPORARILY_OUT_OF_STOCK"]



def test_get_product_detail_returns_none_when_not_found(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.get_product_detail("0001111040101") is None


def test_get_product_detail_validates_product_id(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Product ID must be exactly 13 digits"):
        client.get_product_detail("   ")


def test_get_product_detail_validates_product_id_format(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Product ID must be exactly 13 digits"):
        client.get_product_detail("12345")

    with pytest.raises(KrogerValidationError, match="Product ID must be exactly 13 digits"):
        client.get_product_detail("000111104010X")


def test_get_product_detail_validates_location_id(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Location ID"):
        client.get_product_detail("0001111040101", location_id="bad")


def test_list_locations_maps_params_and_response(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "data": [
                    {
                        "locationId": "01400943",
                        "name": "Kroger Landen",
                        "chain": "KROGER",
                        "phone": "5551234567",
                        "storeNumber": "00943",
                        "divisionNumber": "014",
                        "address": {
                            "addressLine1": "2900 W State Route 22",
                            "city": "Maineville",
                            "state": "OH",
                            "zipCode": "45039",
                        },
                        "geolocation": {
                            "latLng": "39.3110881,-84.2751167",
                            "latitude": 39.3110881,
                            "longitude": -84.2751167,
                        },
                        "departments": [
                            {
                                "departmentId": "01",
                                "name": "Drug & General Merchandise",
                                "phone": "5551112222",
                                "hours": {"Open24": False},
                            }
                        ],
                        "hours": {"timezone": "America/New_York"},
                    }
                ]
            }

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url, headers, kwargs))
            return Response()

    client.auth = Auth()
    client.session = Session()

    locations = client.list_locations(
        zip_code_near=" 45044 ",
        radius_in_miles=25,
        limit=25,
        chain=" Kroger ",
        department_ids=["01", "13"],
        location_ids="01400943,01400390",
    )

    assert len(locations) == 1
    location = locations[0]
    assert location.location_id == "01400943"
    assert location.name == "Kroger Landen"
    assert location.address.city == "Maineville"
    assert location.geolocation.latitude == 39.3110881
    assert location.departments[0].department_id == "01"
    assert location.hours == {"timezone": "America/New_York"}
    assert location.raw["storeNumber"] == "00943"

    method, url, headers, kwargs = calls[0]
    assert method == "GET"
    assert url == "https://api.kroger.com/v1/locations"
    assert headers["Authorization"] == "Bearer app-token"
    assert kwargs["params"] == {
        "filter.limit": 25,
        "filter.zipCode.near": "45044",
        "filter.radiusInMiles": 25,
        "filter.chain": "Kroger",
        "filter.department": "01,13",
        "filter.locationId": "01400943,01400390",
    }


def test_list_locations_validates_filters(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Location limit must be between 1 and 200"):
        client.list_locations(limit=201)
    with pytest.raises(KrogerValidationError, match="Location radius must be between 1 and 100"):
        client.list_locations(radius_in_miles=0)
    with pytest.raises(KrogerValidationError, match="ZIP code"):
        client.list_locations(zip_code_near="1234")
    with pytest.raises(KrogerValidationError, match="Latitude/longitude"):
        client.list_locations(lat_long_near="39.1")
    with pytest.raises(KrogerValidationError, match="Latitude must be between"):
        client.list_locations(lat_near=91, lon_near=-84)
    with pytest.raises(KrogerValidationError, match="Longitude must be between"):
        client.list_locations(lat_near=39, lon_near=-181)
    with pytest.raises(KrogerValidationError, match="provided together"):
        client.list_locations(lat_near=39)
    with pytest.raises(KrogerValidationError, match="Use only one location starting filter"):
        client.list_locations(zip_code_near="45044", lat_long_near="39,-84")
    with pytest.raises(KrogerValidationError, match="Department ID"):
        client.list_locations(department_ids="1")
    with pytest.raises(KrogerValidationError, match="Location ID"):
        client.list_locations(location_ids=["0140094"])


def test_list_locations_maps_lat_lon_filters(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": []}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append(kwargs["params"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.list_locations(lat_near=39.306346, lon_near=-84.278902) == []
    assert calls == [
        {
            "filter.limit": 10,
            "filter.lat.near": "39.306346",
            "filter.lon.near": "-84.278902",
        }
    ]


def test_get_location_and_location_exists(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        text = ""

        def __init__(self, status_code=200):
            self.status_code = status_code

        def json(self):
            return {"data": {"locationId": "01400943", "name": "Kroger Landen"}}

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url))
            return Response(204 if method == "HEAD" else 200)

    client.auth = Auth()
    client.session = Session()

    assert client.get_location("01400943").name == "Kroger Landen"
    assert client.location_exists("01400943") is True
    assert calls == [
        ("GET", "https://api.kroger.com/v1/locations/01400943"),
        ("HEAD", "https://api.kroger.com/v1/locations/01400943"),
    ]


def test_resource_exists_returns_false_on_404(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        status_code = 404
        text = "not found"

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.location_exists("01400943") is False


def test_chain_methods_map_responses_and_paths(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        text = ""

        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url))
            if method == "HEAD":
                return Response({}, 204)
            if url.endswith("/v1/chains"):
                return Response({"data": [{"name": "KROGER", "domain": "kroger.com"}]})
            return Response({"data": {"name": "Baker's", "friendlyBannerName": "Baker's"}})

    client.auth = Auth()
    client.session = Session()

    assert client.list_chains()[0].domain == "kroger.com"
    assert client.get_chain("Baker's").friendly_banner_name == "Baker's"
    assert client.chain_exists("Baker's") is True
    assert calls == [
        ("GET", "https://api.kroger.com/v1/chains"),
        ("GET", "https://api.kroger.com/v1/chains/Baker%27s"),
        ("HEAD", "https://api.kroger.com/v1/chains/Baker%27s"),
    ]


def test_department_methods_map_responses_and_validate_ids(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    calls = []

    class Auth:
        def get_app_access_token(self):
            return "app-token"

    class Response:
        text = ""

        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url))
            if method == "HEAD":
                return Response({}, 204)
            if url.endswith("/v1/departments"):
                return Response({"data": [{"departmentId": "13", "name": "Pharmacy"}]})
            return Response({"data": {"departmentId": "01", "name": "Grocery"}})

    client.auth = Auth()
    client.session = Session()

    assert client.list_departments()[0].department_id == "13"
    assert client.get_department("01").name == "Grocery"
    assert client.department_exists("01") is True
    with pytest.raises(KrogerValidationError, match="Department ID"):
        client.get_department("1")
    assert calls == [
        ("GET", "https://api.kroger.com/v1/departments"),
        ("GET", "https://api.kroger.com/v1/departments/01"),
        ("HEAD", "https://api.kroger.com/v1/departments/01"),
    ]


def test_cart_item_defaults_to_pickup_modality():
    item = CartItem(upc="0001111050434", quantity=1)

    assert item.modality is CartModality.PICKUP


def test_add_to_cart_accepts_cart_modality_enum(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    payloads = []

    class Auth:
        def get_user_access_token(self):
            return "user-token"

    class Response:
        status_code = 204
        text = ""

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            payloads.append(kwargs["json"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.add_to_cart("0001111050434", 1, CartModality.DELIVERY) is True
    assert payloads == [
        {"items": [{"upc": "0001111050434", "quantity": 1, "modality": "DELIVERY"}]}
    ]


def test_add_to_cart_normalizes_cart_modality_string(tmp_path):
    client = KrogerClient(make_config(tmp_path))
    payloads = []

    class Auth:
        def get_user_access_token(self):
            return "user-token"

    class Response:
        status_code = 204
        text = ""

    class Session:
        def request(self, method, url, headers=None, **kwargs):
            payloads.append(kwargs["json"])
            return Response()

    client.auth = Auth()
    client.session = Session()

    assert client.add_to_cart("0001111050434", 1, " pickup ") is True
    assert payloads == [
        {"items": [{"upc": "0001111050434", "quantity": 1, "modality": "PICKUP"}]}
    ]


def test_add_to_cart_rejects_unknown_modality_before_request(tmp_path):
    client = KrogerClient(make_config(tmp_path))

    with pytest.raises(KrogerValidationError, match="Cart modality must be one of"):
        client.add_to_cart("0001111050434", 1, "SHIP")

    with pytest.raises(KrogerValidationError, match="Cart modality is required"):
        client.add_to_cart("0001111050434", 1, "   ")


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



def make_product(product_id, brand="Kroger", description="Test Product"):
    return Product(
        upc=product_id,
        product_id=product_id,
        description=description,
        brand=brand,
        price=1.99,
    )


def make_detail(product, ingredients=None, nutrition=None):
    raw = {
        "upc": product.upc,
        "productId": product.product_id,
        "description": product.description,
        "brand": product.brand,
    }
    if ingredients is not None:
        raw["food"] = {"ingredients": ingredients}
    nutrition_information = None
    if nutrition is not None:
        raw["nutritionInformation"] = nutrition
        nutrition_information = [
            ProductNutritionInformation(
                ingredient_statement=nutrition.get("ingredientStatement") if isinstance(nutrition, dict) else None,
                nutritional_rating=str(nutrition.get("score")) if isinstance(nutrition, dict) and nutrition.get("score") is not None else None,
                raw=nutrition if isinstance(nutrition, dict) else None,
            )
        ]
    return ProductDetail(
        upc=product.upc,
        product_id=product.product_id,
        description=product.description,
        brand=product.brand,
        nutrition_information=nutrition_information,
        raw=raw,
    )


def test_validation_module_rejects_invalid_product_id():
    with pytest.raises(KrogerValidationError, match="Product ID must be exactly 13 digits"):
        validation.validate_product_id("12345")


def test_parsers_module_maps_product_search_item_price_metadata():
    product = parsers.product_from_response(
        {
            "upc": "0001111040101",
            "productId": "0001111040101",
            "description": "Milk",
            "items": [
                {
                    "size": "1 gal",
                    "price": {
                        "regular": 4.99,
                        "regularPerUnitEstimate": 4.99,
                    },
                }
            ],
        }
    )

    assert product.size == "1 gal"
    assert product.price == 4.99
    assert product.regular_per_unit_estimate == 4.99


def test_unit_pricing_parses_supported_size_values():
    cases = {
        "11 oz": (11.0, "oz", 11.0, "oz"),
        "12 fl oz": (12.0, "fl oz", 12.0, "fl oz"),
        "1 gal": (1.0, "gal", 128.0, "fl oz"),
        "2 lb": (2.0, "lb", 32.0, "oz"),
        "1 kg": (1.0, "kg", 1000.0, "g"),
        "16 ct": (16.0, "ct", 16.0, "ct"),
    }

    for size, expected in cases.items():
        parsed = unit_pricing.parse_size_for_unit_price(size)
        assert parsed is not None
        assert (parsed.quantity, parsed.unit, parsed.base_quantity, parsed.base_unit) == expected


def test_unit_pricing_rejects_ambiguous_size_values():
    for size in ("6 ct / 12 fl oz", "2 pk", "12 x 5 oz", "about 1 lb", "10-12 oz"):
        assert unit_pricing.parse_size_for_unit_price(size) is None


def test_unit_pricing_prefers_api_estimate_and_computes_fallback():
    api_product = Product(
        upc="0001111040101",
        product_id="0001111040101",
        description="Milk",
        price=3.99,
        size="11 oz",
        regular_per_unit_estimate=0.42,
    )
    computed_product = Product(
        upc="0001111040102",
        product_id="0001111040102",
        description="Sauce",
        price=3.99,
        size="11 oz",
    )

    assert unit_pricing.unit_price_for_product(api_product).source == "api"
    assert unit_pricing.format_unit_price(api_product) == "$0.42/oz"
    assert unit_pricing.unit_price_for_product(computed_product).source == "computed"
    assert unit_pricing.format_unit_price(computed_product) == "$0.36/oz"


def test_unit_pricing_normalizes_convertible_units_to_smallest_common_unit():
    one_pound = Product(
        upc="0001111040101",
        product_id="0001111040101",
        description="Cheddar",
        price=5.99,
        size="1 lb",
    )
    one_gallon = Product(
        upc="0001111040102",
        product_id="0001111040102",
        description="Milk",
        price=4.99,
        size="1 gal",
    )
    one_kilogram = Product(
        upc="0001111040103",
        product_id="0001111040103",
        description="Flour",
        price=2.99,
        size="1 kg",
    )
    api_pound = Product(
        upc="0001111040104",
        product_id="0001111040104",
        description="Cheddar",
        price=5.99,
        size="1 lb",
        regular_per_unit_estimate=5.99,
    )

    assert unit_pricing.format_unit_price(one_pound) == "$0.37/oz"
    assert unit_pricing.format_unit_price(one_gallon) == "$0.04/fl oz"
    assert unit_pricing.format_unit_price(one_kilogram) == "$0.00/g"
    assert unit_pricing.format_unit_price(api_pound) == "$0.37/oz"


def test_unit_pricing_formats_missing_or_unparseable_values_as_na():
    assert unit_pricing.format_unit_price(
        Product(
            upc="0001111040101",
            product_id="0001111040101",
            description="Sauce",
            price=3.99,
            size="6 ct / 12 fl oz",
        )
    ) == "N/A"
    assert unit_pricing.format_unit_price(
        Product(
            upc="0001111040102",
            product_id="0001111040102",
            description="Sauce",
            size="11 oz",
        )
    ) == "N/A"


def test_parsers_module_maps_product_detail_without_client_instance():
    detail = parsers.product_detail_from_response(
        {
            "upc": "0001111040101",
            "productId": "0001111040101",
            "description": "Milk",
            "items": [{"fulfillment": {"curbside": True}, "inventory": {"stockLevel": "HIGH"}}],
            "nutritionInformation": {"ingredientStatement": "Milk"},
        }
    )

    assert detail.items[0].fulfillment.curbside is True
    assert detail.items[0].inventory.stock_level == "HIGH"
    assert detail.nutrition_information[0].ingredient_statement == "Milk"


def test_recommendations_module_scores_without_client_instance():
    product = make_product("0001111040101")

    score = recommendations.score_product_preference(
        product,
        make_detail(product, ingredients="Water, sodium benzoate"),
        original_rank=1,
        candidate_count=1,
        preferences=PreferenceProfile(),
    )

    assert score.unwanted_ingredient_count == 1
    assert score.unwanted_ingredients == ["Sodium benzoate"]



def test_preference_scoring_prefers_simple_truth_over_equivalent_product():
    client = KrogerClient.__new__(KrogerClient)
    simple_truth = make_product("0001111040101", brand="Simple Truth Organic")
    kroger = make_product("0001111040102", brand="Kroger")

    simple_score = client._score_product_preference(
        simple_truth,
        make_detail(simple_truth, ingredients="Organic milk"),
        original_rank=2,
        candidate_count=2,
        preferences=PreferenceProfile(),
    )
    kroger_score = client._score_product_preference(
        kroger,
        make_detail(kroger, ingredients="Milk"),
        original_rank=1,
        candidate_count=2,
        preferences=PreferenceProfile(),
    )

    assert simple_score.total > kroger_score.total
    assert "Simple Truth brand" in " ".join(simple_score.reasons)


def test_preference_scoring_penalizes_unwanted_ingredients_with_explanation():
    client = KrogerClient.__new__(KrogerClient)
    product = make_product("0001111040101")

    score = client._score_product_preference(
        product,
        make_detail(product, ingredients="Water, high fructose corn syrup, red 40"),
        original_rank=1,
        candidate_count=1,
        preferences=PreferenceProfile(),
    )

    reasons = " ".join(score.reasons)
    assert score.total < 0
    assert "High-fructose corn syrup" in reasons
    assert "Artificial colors" in reasons
    assert score.unwanted_ingredient_count == 2
    assert score.unwanted_ingredients == ["Artificial colors", "High-fructose corn syrup"]
    assert not any("Ingredients not assessed" in warning for warning in score.warnings)


def test_preference_scoring_warns_without_penalizing_when_ingredients_missing():
    client = KrogerClient.__new__(KrogerClient)
    product = make_product("0001111040101")

    score = client._score_product_preference(
        product,
        make_detail(product, ingredients=None),
        original_rank=1,
        candidate_count=1,
        preferences=PreferenceProfile(),
    )

    assert score.total == 0.25
    assert score.unwanted_ingredient_count is None
    assert score.unwanted_ingredients == []
    assert any("Ingredients not assessed" in warning for warning in score.warnings)



def test_simple_truth_unwanted_matching_counts_unique_aliases():
    client = KrogerClient.__new__(KrogerClient)

    matches = client._match_unwanted_ingredients(
        "Water, FD&C Red 40, red 40, BHA, butylated hydroxyanisole, potassium sorbate",
        PreferenceProfile().ingredient_rules,
    )

    assert [match["label"] for match in matches] == [
        "Artificial colors",
        "BHA (butylated hydroxyanisole)",
        "Potassium sorbate",
    ]



def test_simple_truth_unwanted_matching_suppresses_broad_family_duplicates():
    client = KrogerClient.__new__(KrogerClient)

    matches = client._match_unwanted_ingredients(
        "Water, calcium disodium EDTA, sodium nitrate, sodium propionate",
        PreferenceProfile().ingredient_rules,
    )

    assert [match["label"] for match in matches] == [
        "Calcium disodium EDTA",
        "Sodium nitrate/nitrite",
        "Sodium propionate",
    ]


def test_preference_scoring_reports_zero_unwanted_ingredients_when_known_clean():
    client = KrogerClient.__new__(KrogerClient)
    product = make_product("0001111040101")

    score = client._score_product_preference(
        product,
        make_detail(product, ingredients="Cultured buttermilk, garlic, onion, sea salt"),
        original_rank=1,
        candidate_count=1,
        preferences=PreferenceProfile(),
    )

    assert score.unwanted_ingredient_count == 0
    assert score.unwanted_ingredients == []
    assert "Simple Truth unwanted ingredients: 0" in score.reasons


def test_ranked_search_sorts_by_unwanted_ingredient_count_before_score():
    class FakeClient(KrogerClient):
        def __init__(self):
            pass

        def search_products(self, term, limit=10, location_id=None, fulfillment=None, brand=None):
            return [
                make_product("0001111040101", brand="Simple Truth", description="Penalty"),
                make_product("0001111040102", brand="Kroger", description="Clean"),
                make_product("0001111040103", brand="Kroger", description="Unknown"),
            ]

        def get_product_detail(self, product_id, location_id=None):
            product = make_product(product_id)
            if product_id == "0001111040101":
                return make_detail(product, ingredients="Water, sodium benzoate, potassium sorbate")
            if product_id == "0001111040102":
                return make_detail(product, ingredients="Cultured buttermilk, garlic, onion")
            return make_detail(product, ingredients=None)

    results = FakeClient().ranked_search_products("ranch", limit=3, candidate_limit=3)

    assert [item.product.description for item in results] == ["Clean", "Penalty", "Unknown"]
    assert [item.preference_score.unwanted_ingredient_count for item in results] == [0, 2, None]


def test_ranked_search_uses_original_kroger_order_to_break_ties(tmp_path):
    class FakeClient(KrogerClient):
        def __init__(self):
            pass

        def search_products(self, term, limit=10, location_id=None, fulfillment=None, brand=None):
            return [
                make_product("0001111040101", description="First"),
                make_product("0001111040102", description="Second"),
            ]

        def get_product_detail(self, product_id, location_id=None):
            product = make_product(product_id)
            return make_detail(product, ingredients="Milk")

    results = FakeClient().ranked_search_products("milk", limit=2, candidate_limit=2)

    assert [item.product.product_id for item in results] == ["0001111040101", "0001111040102"]
    assert results[0].preference_score.total > results[1].preference_score.total


def test_health_nutrition_signal_improves_rank():
    class FakeClient(KrogerClient):
        def __init__(self):
            pass

        def search_products(self, term, limit=10, location_id=None, fulfillment=None, brand=None):
            return [
                make_product("0001111040101", description="No Nutrition"),
                make_product("0001111040102", description="Nutrition"),
            ]

        def get_product_detail(self, product_id, location_id=None):
            product = make_product(product_id)
            nutrition = {"score": "100"} if product_id == "0001111040102" else None
            return make_detail(product, ingredients="Milk", nutrition=nutrition)

    results = FakeClient().ranked_search_products("milk", limit=2, candidate_limit=2)

    assert results[0].product.product_id == "0001111040102"
    assert "Health/nutrition signal" in " ".join(results[0].preference_score.reasons)


def test_ranked_search_fetches_details_for_candidates_and_survives_one_failure():
    class FakeClient(KrogerClient):
        def __init__(self):
            self.searched_limits = []
            self.detail_calls = []

        def search_products(self, term, limit=10, location_id=None, fulfillment=None, brand=None):
            self.searched_limits.append(limit)
            return [
                make_product("0001111040101", brand="Simple Truth", description="First"),
                make_product("0001111040102", description="Second"),
                make_product("0001111040103", description="Third"),
            ]

        def get_product_detail(self, product_id, location_id=None):
            self.detail_calls.append(product_id)
            if product_id == "0001111040102":
                raise RuntimeError("detail timeout")
            product = make_product(product_id)
            return make_detail(product, ingredients="Milk")

    client = FakeClient()
    results = client.ranked_search_products("milk", limit=2, candidate_limit=3)

    assert client.searched_limits == [3]
    assert client.detail_calls == ["0001111040101", "0001111040102", "0001111040103"]
    assert len(results) == 2
    failed = [item for item in results if item.product.product_id == "0001111040102"]
    assert not failed or any("Product detail unavailable" in warning for warning in failed[0].preference_score.warnings)
    assert any(item.product.brand == "Simple Truth" for item in results)


def test_cli_add_defaults_to_pickup_quantity_one(capsys):
    from kroger_shopping import cli

    calls = []

    class Client:
        def add_to_cart(self, upc, quantity=1, modality=CartModality.PICKUP):
            calls.append((upc, quantity, modality))
            return True

    exit_code = cli.main(["add", "0001111050434"], client_factory=Client)

    assert exit_code == 0
    assert calls == [("0001111050434", 1, CartModality.PICKUP)]
    assert capsys.readouterr().out == (
        "Added to cart: UPC 0001111050434, quantity 1, modality PICKUP.\n"
    )


def test_cli_add_passes_quantity_and_delivery_modality(capsys):
    from kroger_shopping import cli

    calls = []

    class Client:
        def add_to_cart(self, upc, quantity=1, modality=CartModality.PICKUP):
            calls.append((upc, quantity, modality))
            return True

    exit_code = cli.main(
        ["add", "0001111050434", "--quantity", "3", "--modality", "delivery"],
        client_factory=Client,
    )

    assert exit_code == 0
    assert calls == [("0001111050434", 3, CartModality.DELIVERY)]
    assert "quantity 3, modality DELIVERY" in capsys.readouterr().out


def test_cli_add_rejects_invalid_quantity_concisely(capsys):
    from kroger_shopping import cli

    class Client:
        def add_to_cart(self, upc, quantity=1, modality=CartModality.PICKUP):
            raise AssertionError("add_to_cart should not be called")

    exit_code = cli.main(
        ["add", "0001111050434", "--quantity", "1.5"],
        client_factory=Client,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "Validation error: Quantity must be a whole number\n"


def test_cli_search_formats_compact_product_lines(capsys):
    from kroger_shopping import cli

    calls = []

    class Client:
        def search_products(self, term, limit=10):
            calls.append((term, limit))
            return [
                Product(
                    upc="0001111050434",
                    product_id="0001111050434",
                    description="Simple Truth Milk",
                    brand="Simple Truth",
                    price=4.99,
                    size="1 gal",
                    regular_per_unit_estimate=4.99,
                )
            ]

    exit_code = cli.main(["search", "whole", "milk", "--limit", "1"], client_factory=Client)

    assert exit_code == 0
    assert calls == [("whole milk", 1)]
    assert capsys.readouterr().out == "Simple Truth Milk - Simple Truth | $4.99 | 0001111050434\n"


def test_cli_recommend_formats_compact_ranked_lines(capsys):
    from kroger_shopping import cli
    from kroger_shopping.models import ProductPreferenceScore, RankedProduct

    products = [
        Product(
            upc="0001111050434",
            product_id="0001111050434",
            description="Kroger Cheddar Block",
            brand="Kroger",
            price=4.00,
            size="8 oz",
        ),
        Product(
            upc="0001111050435",
            product_id="0001111050435",
            description="Simple Truth Cheddar Block",
            brand="Simple Truth",
            price=5.99,
            size="1 lb",
        ),
    ]

    class Client:
        def ranked_search_products(self, term, limit=10):
            assert (term, limit) == ("cheddar", 2)
            return [
                RankedProduct(
                    product=product,
                    detail=None,
                    preference_score=ProductPreferenceScore(
                        total=92.5,
                        unwanted_ingredient_count=0,
                    ),
                    original_kroger_rank=index,
                )
                for index, product in enumerate(products, start=1)
            ]

    exit_code = cli.main(["recommend", "cheddar", "--limit", "2"], client_factory=Client)

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "Kroger Cheddar Block - Kroger | $4.00 | 0001111050434 | size: 8 oz | unit: $0.50/oz | unwanted: 0\n"
        "Simple Truth Cheddar Block - Simple Truth | $5.99 | 0001111050435 | size: 1 lb | unit: $0.37/oz | unwanted: 0\n"
    )


def test_hermes_recommend_formats_size_unit_and_omits_score(monkeypatch):
    import asyncio
    import importlib
    import sys
    import types

    from kroger_shopping.models import ProductPreferenceScore, RankedProduct

    hermes_module = types.ModuleType("hermes")
    hermes_commands = types.ModuleType("hermes.commands")

    def command(_name):
        def decorator(func):
            return func
        return decorator

    hermes_commands.command = command
    monkeypatch.setitem(sys.modules, "hermes", hermes_module)
    monkeypatch.setitem(sys.modules, "hermes.commands", hermes_commands)

    kroger_command_module = importlib.import_module("commands.kroger")

    products = [
        Product(
            upc="0001111050434",
            product_id="0001111050434",
            description="Kroger Cheddar Block",
            brand="Kroger",
            price=4.00,
            size="8 oz",
        ),
        Product(
            upc="0001111050435",
            product_id="0001111050435",
            description="Simple Truth Cheddar Block",
            brand="Simple Truth",
            price=5.99,
            size="1 lb",
        ),
    ]

    class Client:
        def ranked_search_products(self, term, limit=6):
            assert (term, limit) == ("cheddar", 6)
            return [
                RankedProduct(
                    product=product,
                    detail=None,
                    preference_score=ProductPreferenceScore(
                        total=92.5,
                        unwanted_ingredient_count=0,
                        reasons=["Simple Truth unwanted ingredients: 0"],
                    ),
                    original_kroger_rank=index,
                )
                for index, product in enumerate(products, start=1)
            ]

    monkeypatch.setattr(kroger_command_module, "get_client", lambda: Client())

    output = asyncio.run(kroger_command_module.kroger_command(None, "recommend", "cheddar"))

    assert output == (
        "**Kroger Cheddar Block** - Kroger | $4.0 | `0001111050434` "
        "| size: 8 oz | unit: $0.50/oz | unwanted: 0 | Simple Truth unwanted ingredients: 0\n"
        "**Simple Truth Cheddar Block** - Simple Truth | $5.99 | `0001111050435` "
        "| size: 1 lb | unit: $0.37/oz | unwanted: 0 | Simple Truth unwanted ingredients: 0"
    )
    assert "score" not in output.lower()


def test_cli_status_reports_auth_state(capsys):
    from kroger_shopping import cli

    class Auth:
        def __init__(self, active):
            self.active = active

        def has_valid_user_tokens(self):
            return self.active

    class ActiveClient:
        auth = Auth(True)

    class MissingClient:
        auth = Auth(False)

    assert cli.main(["status"], client_factory=ActiveClient) == 0
    assert capsys.readouterr().out == "Kroger user authentication is active.\n"

    assert cli.main(["status"], client_factory=MissingClient) == 0
    assert capsys.readouterr().out == (
        "Kroger user authentication is missing or expired. Run /kroger login.\n"
    )
