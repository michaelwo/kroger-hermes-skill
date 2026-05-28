import requests
from typing import Any, List, Optional, Sequence, Union
from urllib.parse import quote

from . import parsers, recommendations, validation
from .auth import KrogerAuthClient
from .config import KrogerConfig
from .exceptions import KrogerAuthError, KrogerError, KrogerServerError, KrogerValidationError
from .models import (
    CartModality,
    Chain,
    Department,
    Location,
    PreferenceProfile,
    Product,
    ProductAllergen,
    ProductDetail,
    ProductFulfillment,
    ProductItemDetail,
    ProductItemFulfillment,
    ProductItemInventory,
    ProductNutritionInformation,
    ProductPreferenceScore,
    RankedProduct,
)


class KrogerClient:
    """High-level client for interacting with Kroger APIs."""

    BASE_URL = "https://api.kroger.com"
    MIN_PRODUCT_SEARCH_LIMIT = validation.MIN_PRODUCT_SEARCH_LIMIT
    MAX_PRODUCT_SEARCH_LIMIT = validation.MAX_PRODUCT_SEARCH_LIMIT
    MIN_LOCATION_LIMIT = validation.MIN_LOCATION_LIMIT
    MAX_LOCATION_LIMIT = validation.MAX_LOCATION_LIMIT
    MIN_LOCATION_RADIUS = validation.MIN_LOCATION_RADIUS
    MAX_LOCATION_RADIUS = validation.MAX_LOCATION_RADIUS

    def __init__(self, config: Optional[KrogerConfig] = None):
        self.config = config or KrogerConfig.from_env()
        self.auth = KrogerAuthClient(self.config)
        self.session = requests.Session()

    def _headers(self, token: str, content_type: Optional[str] = None) -> dict:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(
        self,
        method: str,
        path: str,
        auth_mode: str,
        retry_on_unauthorized: bool = True,
        **kwargs,
    ) -> requests.Response:
        token = self._token_for_mode(auth_mode)
        headers = {**self._headers(token), **kwargs.pop("headers", {})}
        resp = self.session.request(
            method,
            f"{self.BASE_URL}{path}",
            headers=headers,
            timeout=20,
            **kwargs,
        )

        if resp.status_code == 401 and retry_on_unauthorized:
            token = self._refresh_for_mode(auth_mode)
            headers["Authorization"] = f"Bearer {token}"
            resp = self.session.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=headers,
                timeout=20,
                **kwargs,
            )

        self._raise_for_response(resp)
        return resp

    def _token_for_mode(self, auth_mode: str) -> str:
        if auth_mode == "app":
            return self.auth.get_app_access_token()
        if auth_mode == "user":
            return self.auth.get_user_access_token()
        raise ValueError(f"Unknown auth mode: {auth_mode}")

    def _refresh_for_mode(self, auth_mode: str) -> str:
        if auth_mode == "app":
            self.auth._app_tokens = None
            return self.auth.get_app_access_token()
        if auth_mode == "user":
            return self.auth.force_refresh_user_access_token()
        raise ValueError(f"Unknown auth mode: {auth_mode}")

    def _raise_for_response(self, resp: requests.Response):
        if resp.status_code < 400:
            return
        body = resp.text[:1000] if resp.text else "<empty response>"
        if resp.status_code == 401:
            raise KrogerAuthError(f"Kroger authentication failed: {body}")
        if resp.status_code >= 500:
            raise KrogerServerError(f"Kroger server error {resp.status_code}: {body}")
        raise KrogerError(f"Kroger API request failed {resp.status_code}: {body}")

    def search_products(
        self,
        term: str,
        limit: int = 10,
        location_id: Optional[str] = None,
        fulfillment: Optional[Union[ProductFulfillment, Sequence[ProductFulfillment]]] = None,
        brand: Optional[str] = None,
    ) -> List[Product]:
        term = self._validate_search_term(term)
        self._validate_limit(limit)

        params = {"filter.term": term, "filter.limit": limit}
        loc = location_id or self.config.default_location_id
        if loc:
            params["filter.locationId"] = self._validate_location_id(loc)
        fulfillment_filter = fulfillment if fulfillment is not None else self.config.default_fulfillment
        if fulfillment_filter is not None:
            params["filter.fulfillment"] = self._validate_fulfillment(fulfillment_filter)
        if brand:
            params["filter.brand"] = brand.strip()

        resp = self._request("GET", "/v1/products", auth_mode="app", params=params)
        products = []
        for item in resp.json().get("data", []):
            try:
                products.append(parsers.product_from_response(item))
            except Exception:
                continue
        return products

    def get_product_detail(
        self,
        product_id: str,
        location_id: Optional[str] = None,
    ) -> Optional[ProductDetail]:
        product_id = self._validate_product_id(product_id)
        params = {}
        loc = location_id or self.config.default_location_id
        if loc:
            params["filter.locationId"] = self._validate_location_id(loc)

        resp = self._request("GET", f"/v1/products/{product_id}", auth_mode="app", params=params)
        data = resp.json().get("data")
        if not data:
            return None
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]
        return parsers.product_detail_from_response(data)

    def ranked_search_products(
        self,
        term: str,
        location_id: Optional[str] = None,
        limit: int = 10,
        candidate_limit: int = 25,
        preferences: Optional[PreferenceProfile] = None,
        fulfillment: Optional[Union[ProductFulfillment, Sequence[ProductFulfillment]]] = None,
    ) -> List[RankedProduct]:
        """Search Kroger products and rank candidates against local preferences."""
        self._validate_limit(limit)
        self._validate_limit(candidate_limit)
        if location_id:
            location_id = self._validate_location_id(location_id)

        profile = preferences or PreferenceProfile()
        candidates = self.search_products(
            term,
            limit=candidate_limit,
            location_id=location_id,
            fulfillment=fulfillment,
        )
        ranked = []
        for index, product in enumerate(candidates, start=1):
            detail = None
            detail_warning = None
            try:
                detail = self.get_product_detail(product.product_id, location_id=location_id)
            except Exception as exc:
                detail_warning = f"Product detail unavailable: {exc}"

            score = recommendations.score_product_preference(
                product,
                detail,
                original_rank=index,
                candidate_count=len(candidates),
                preferences=profile,
            )
            if detail_warning:
                score.warnings.insert(0, detail_warning)
            ranked.append(
                RankedProduct(
                    product=product,
                    detail=detail,
                    preference_score=score,
                    original_kroger_rank=index,
                )
            )

        ranked.sort(key=recommendations.ranked_product_sort_key)
        return ranked[:limit]

    def list_locations(
        self,
        zip_code_near: Optional[str] = None,
        lat_long_near: Optional[str] = None,
        lat_near: Optional[Union[str, float]] = None,
        lon_near: Optional[Union[str, float]] = None,
        radius_in_miles: Optional[int] = None,
        limit: int = 10,
        chain: Optional[str] = None,
        department_ids: Optional[Union[str, List[str]]] = None,
        location_ids: Optional[Union[str, List[str]]] = None,
    ) -> List[Location]:
        params = {
            "filter.limit": self._validate_int_range(
                limit,
                "Location limit",
                self.MIN_LOCATION_LIMIT,
                self.MAX_LOCATION_LIMIT,
            )
        }

        starting_filters = sum(
            bool(value)
            for value in (
                zip_code_near,
                lat_long_near,
                lat_near is not None or lon_near is not None,
            )
        )
        if starting_filters > 1:
            raise KrogerValidationError(
                "Use only one location starting filter: zip code, lat/long, or lat and lon"
            )

        if zip_code_near:
            params["filter.zipCode.near"] = self._validate_zip_code(zip_code_near)
        if lat_long_near:
            params["filter.latLong.near"] = self._validate_lat_long(lat_long_near)
        if lat_near is not None or lon_near is not None:
            if lat_near is None or lon_near is None:
                raise KrogerValidationError("Latitude and longitude must be provided together")
            params["filter.lat.near"] = self._validate_coordinate(lat_near, "Latitude")
            params["filter.lon.near"] = self._validate_coordinate(lon_near, "Longitude")
        if radius_in_miles is not None:
            params["filter.radiusInMiles"] = self._validate_int_range(
                radius_in_miles,
                "Location radius",
                self.MIN_LOCATION_RADIUS,
                self.MAX_LOCATION_RADIUS,
            )
        if chain:
            params["filter.chain"] = chain.strip()
        if department_ids:
            params["filter.department"] = self._validate_department_ids(department_ids)
        if location_ids:
            params["filter.locationId"] = self._validate_location_ids(location_ids)

        resp = self._request("GET", "/v1/locations", auth_mode="app", params=params)
        return [parsers.location_from_response(item) for item in resp.json().get("data", [])]

    def get_location(self, location_id: str) -> Optional[Location]:
        location_id = self._validate_location_id(location_id)
        resp = self._request("GET", f"/v1/locations/{location_id}", auth_mode="app")
        data = resp.json().get("data")
        return parsers.location_from_response(data) if data else None

    def location_exists(self, location_id: str) -> bool:
        location_id = self._validate_location_id(location_id)
        return self._resource_exists(f"/v1/locations/{location_id}")

    def list_chains(self) -> List[Chain]:
        resp = self._request("GET", "/v1/chains", auth_mode="app")
        return [parsers.chain_from_response(item) for item in resp.json().get("data", [])]

    def get_chain(self, name: str) -> Optional[Chain]:
        name = self._validate_required_name(name, "Chain name")
        resp = self._request("GET", f"/v1/chains/{quote(name, safe='')}", auth_mode="app")
        data = resp.json().get("data")
        return parsers.chain_from_response(data) if data else None

    def chain_exists(self, name: str) -> bool:
        name = self._validate_required_name(name, "Chain name")
        return self._resource_exists(f"/v1/chains/{quote(name, safe='')}")

    def list_departments(self) -> List[Department]:
        resp = self._request("GET", "/v1/departments", auth_mode="app")
        return [parsers.department_from_response(item) for item in resp.json().get("data", [])]

    def get_department(self, department_id: str) -> Optional[Department]:
        department_id = self._validate_department_id(department_id)
        resp = self._request("GET", f"/v1/departments/{department_id}", auth_mode="app")
        data = resp.json().get("data")
        return parsers.department_from_response(data) if data else None

    def department_exists(self, department_id: str) -> bool:
        department_id = self._validate_department_id(department_id)
        return self._resource_exists(f"/v1/departments/{department_id}")

    def _resource_exists(self, path: str) -> bool:
        try:
            resp = self._request("HEAD", path, auth_mode="app")
            return resp.status_code == 204
        except KrogerError as exc:
            if "404" in str(exc):
                return False
            raise

    def add_to_cart(
        self,
        upc: str,
        quantity: int = 1,
        modality: Union[CartModality, str] = CartModality.PICKUP,
    ) -> bool:
        upc = self._validate_product_id(upc, field_name="UPC")
        quantity = self._validate_quantity(quantity)
        modality = self._validate_cart_modality(modality)

        payload = {"items": [{"upc": upc, "quantity": quantity, "modality": modality.value}]}
        resp = self._request(
            "PUT",
            "/v1/cart/add",
            auth_mode="user",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        return resp.status_code in (200, 201, 204)

    def _validate_search_term(self, term: str) -> str:
        return validation.validate_search_term(term)

    def _validate_limit(self, limit: int) -> int:
        return validation.validate_limit(limit)

    def _validate_location_id(self, location_id: str) -> str:
        return validation.validate_location_id(location_id)

    def _validate_fulfillment(
        self,
        fulfillment: Union[ProductFulfillment, Sequence[ProductFulfillment]],
    ) -> str:
        return validation.validate_fulfillment(fulfillment)

    def _validate_product_id(self, product_id: str, field_name: str = "Product ID") -> str:
        return validation.validate_product_id(product_id, field_name=field_name)

    def _validate_quantity(self, quantity: int) -> int:
        return validation.validate_quantity(quantity)

    def _validate_cart_modality(self, modality: Union[CartModality, str]) -> CartModality:
        return validation.validate_cart_modality(modality)

    def _validate_int_range(
        self,
        value: int,
        field_name: str,
        minimum: int,
        maximum: int,
    ) -> int:
        return validation.validate_int_range(value, field_name, minimum, maximum)

    def _validate_zip_code(self, zip_code: str) -> str:
        return validation.validate_zip_code(zip_code)

    def _validate_coordinate(self, value: Union[str, float, int], field_name: str) -> str:
        return validation.validate_coordinate(value, field_name)

    def _validate_lat_long(self, lat_long: str) -> str:
        return validation.validate_lat_long(lat_long)

    def _validate_location_ids(self, location_ids: Union[str, List[str]]) -> str:
        return validation.validate_location_ids(location_ids)

    def _validate_department_id(self, department_id: str) -> str:
        return validation.validate_department_id(department_id)

    def _validate_department_ids(self, department_ids: Union[str, List[str]]) -> str:
        return validation.validate_department_ids(department_ids)

    def _split_filter_values(self, values: Union[str, List[str]]) -> List[str]:
        return validation.split_filter_values(values)

    def _validate_required_name(self, name: str, field_name: str) -> str:
        return validation.validate_required_name(name, field_name)

    def _product_detail_from_response(self, item: dict) -> ProductDetail:
        return parsers.product_detail_from_response(item)

    def _product_item_detail_from_response(self, item: dict) -> ProductItemDetail:
        return parsers.product_item_detail_from_response(item)

    def _item_fulfillment_from_response(self, fulfillment: Optional[dict]) -> Optional[ProductItemFulfillment]:
        return parsers.item_fulfillment_from_response(fulfillment)

    def _item_inventory_from_response(self, inventory: Optional[dict]) -> Optional[ProductItemInventory]:
        return parsers.item_inventory_from_response(inventory)

    def _nutrition_information_from_response(self, nutrition: Any) -> Optional[list[ProductNutritionInformation]]:
        return parsers.nutrition_information_from_response(nutrition)

    def _allergens_from_response(self, allergens: Any) -> Optional[list[ProductAllergen]]:
        return parsers.allergens_from_response(allergens)

    def _location_from_response(self, item: dict) -> Location:
        return parsers.location_from_response(item)

    def _chain_from_response(self, item: dict) -> Chain:
        return parsers.chain_from_response(item)

    def _department_from_response(self, item: dict) -> Department:
        return parsers.department_from_response(item)

    def _ranked_product_sort_key(self, item: RankedProduct) -> tuple:
        return recommendations.ranked_product_sort_key(item)

    def _score_product_preference(
        self,
        product: Product,
        detail: Optional[ProductDetail],
        original_rank: int,
        candidate_count: int,
        preferences: PreferenceProfile,
    ) -> ProductPreferenceScore:
        return recommendations.score_product_preference(
            product,
            detail,
            original_rank=original_rank,
            candidate_count=candidate_count,
            preferences=preferences,
        )

    def _match_unwanted_ingredients(
        self,
        ingredient_text: str,
        rules: Sequence,
    ) -> list[dict[str, Any]]:
        return recommendations.match_unwanted_ingredients(ingredient_text, rules)

    def _suppress_broad_unwanted_matches(self, matches: list[dict[str, Any]]) -> None:
        recommendations.suppress_broad_unwanted_matches(matches)

    def _normalize_ingredient_text(self, value: str) -> str:
        return recommendations.normalize_ingredient_text(value)

    def _extract_ingredient_text(
        self,
        raw: Optional[dict[str, Any]],
        nutrition_information: Optional[list[ProductNutritionInformation]] = None,
    ) -> tuple[str, list[str]]:
        return recommendations.extract_ingredient_text(raw, nutrition_information)

    def _stringify_ingredient_value(self, value: Any) -> str:
        return recommendations.stringify_ingredient_value(value)

    def _health_signal_points(self, nutrition: Any, weight: float) -> float:
        return recommendations.health_signal_points(nutrition, weight)
