import requests
from typing import Any, List, Optional, Sequence, Union
from urllib.parse import quote

from .config import KrogerConfig
from .auth import KrogerAuthClient
from .models import (
    Product,
    ProductDetail,
    ProductItemDetail,
    Location,
    LocationAddress,
    GeoLocation,
    LocationDepartment,
    Chain,
    Department,
    CartModality,
    ProductFulfillment,
    PreferenceProfile,
    ProductPreferenceScore,
    RankedProduct,
)
from .exceptions import (
    KrogerAuthError,
    KrogerError,
    KrogerValidationError,
    KrogerServerError,
)


class KrogerClient:
    """High-level client for interacting with Kroger APIs."""

    BASE_URL = "https://api.kroger.com"
    MIN_PRODUCT_SEARCH_LIMIT = 1
    MAX_PRODUCT_SEARCH_LIMIT = 50
    MIN_LOCATION_LIMIT = 1
    MAX_LOCATION_LIMIT = 200
    MIN_LOCATION_RADIUS = 1
    MAX_LOCATION_RADIUS = 100

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

    def _validate_search_term(self, term: str) -> str:
        if term is None:
            raise KrogerValidationError("Search term is required")
        term = term.strip()
        if len(term) < 3:
            raise KrogerValidationError("Search term must be at least 3 characters")
        return term

    def _validate_limit(self, limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise KrogerValidationError("Search limit must be a whole number")
        if not self.MIN_PRODUCT_SEARCH_LIMIT <= limit <= self.MAX_PRODUCT_SEARCH_LIMIT:
            raise KrogerValidationError("Search limit must be between 1 and 50")
        return limit

    def _validate_location_id(self, location_id: str) -> str:
        location_id = location_id.strip()
        if len(location_id) != 8 or not location_id.isdigit():
            raise KrogerValidationError("Location ID must be exactly 8 digits")
        return location_id

    def _validate_fulfillment(
        self,
        fulfillment: Union[ProductFulfillment, Sequence[ProductFulfillment]],
    ) -> str:
        if isinstance(fulfillment, ProductFulfillment):
            return fulfillment.value
        if isinstance(fulfillment, str) or not isinstance(fulfillment, Sequence):
            allowed = ", ".join(item.name for item in ProductFulfillment)
            raise KrogerValidationError(f"Fulfillment must be ProductFulfillment enum values: {allowed}")

        values = []
        for item in fulfillment:
            if not isinstance(item, ProductFulfillment):
                allowed = ", ".join(value.name for value in ProductFulfillment)
                raise KrogerValidationError(f"Fulfillment must be ProductFulfillment enum values: {allowed}")
            values.append(item.value)
        if not values:
            raise KrogerValidationError("Fulfillment must include at least one ProductFulfillment value")
        return ",".join(values)

    def _validate_product_id(self, product_id: str, field_name: str = "Product ID") -> str:
        if product_id is None:
            raise KrogerValidationError(f"{field_name} is required")
        product_id = product_id.strip()
        if len(product_id) != 13 or not product_id.isdigit():
            raise KrogerValidationError(f"{field_name} must be exactly 13 digits")
        return product_id

    def _validate_quantity(self, quantity: int) -> int:
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise KrogerValidationError("Quantity must be a whole number")
        if quantity < 1:
            raise KrogerValidationError("Quantity must be at least 1")
        return quantity

    def _validate_cart_modality(self, modality: Union[CartModality, str]) -> CartModality:
        if isinstance(modality, CartModality):
            return modality
        if modality is None or not str(modality).strip():
            raise KrogerValidationError("Cart modality is required")

        value = str(modality).strip().upper()
        try:
            return CartModality(value)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in CartModality)
            raise KrogerValidationError(f"Cart modality must be one of: {allowed}") from exc

    def _validate_int_range(
        self,
        value: int,
        field_name: str,
        minimum: int,
        maximum: int,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise KrogerValidationError(f"{field_name} must be a whole number")
        if not minimum <= value <= maximum:
            raise KrogerValidationError(f"{field_name} must be between {minimum} and {maximum}")
        return value

    def _validate_zip_code(self, zip_code: str) -> str:
        zip_code = zip_code.strip()
        if len(zip_code) != 5 or not zip_code.isdigit():
            raise KrogerValidationError("ZIP code must be exactly 5 digits")
        return zip_code

    def _validate_coordinate(self, value: Union[str, float, int], field_name: str) -> str:
        try:
            coordinate = float(value)
        except (TypeError, ValueError) as exc:
            raise KrogerValidationError(f"{field_name} must be a number") from exc

        if field_name == "Latitude" and not -90 <= coordinate <= 90:
            raise KrogerValidationError("Latitude must be between -90 and 90")
        if field_name == "Longitude" and not -180 <= coordinate <= 180:
            raise KrogerValidationError("Longitude must be between -180 and 180")
        return str(value).strip()

    def _validate_lat_long(self, lat_long: str) -> str:
        parts = [part.strip() for part in lat_long.split(",")]
        if len(parts) != 2 or not all(parts):
            raise KrogerValidationError("Latitude/longitude must be formatted as 'lat,lon'")
        lat = self._validate_coordinate(parts[0], "Latitude")
        lon = self._validate_coordinate(parts[1], "Longitude")
        return f"{lat},{lon}"

    def _validate_location_ids(self, location_ids: Union[str, List[str]]) -> str:
        values = self._split_filter_values(location_ids)
        return ",".join(self._validate_location_id(value) for value in values)

    def _validate_department_id(self, department_id: str) -> str:
        department_id = department_id.strip()
        if len(department_id) != 2 or not department_id.isdigit():
            raise KrogerValidationError("Department ID must be exactly 2 digits")
        return department_id

    def _validate_department_ids(self, department_ids: Union[str, List[str]]) -> str:
        values = self._split_filter_values(department_ids)
        return ",".join(self._validate_department_id(value) for value in values)

    def _split_filter_values(self, values: Union[str, List[str]]) -> List[str]:
        if isinstance(values, str):
            items = [value.strip() for value in values.split(",")]
        else:
            items = [str(value).strip() for value in values]
        if not items or any(not item for item in items):
            raise KrogerValidationError("Filter values must be non-empty")
        return items

    def _validate_required_name(self, name: str, field_name: str) -> str:
        if name is None or not name.strip():
            raise KrogerValidationError(f"{field_name} is required")
        return name.strip()

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
        data = resp.json()
        products = []
        for item in data.get("data", []):
            try:
                product_items = item.get("items") or []
                first_item = product_items[0] if product_items else {}
                products.append(
                    Product(
                        upc=item.get("upc", ""),
                        product_id=item.get("productId", ""),
                        description=item.get("description", ""),
                        brand=item.get("brand"),
                        size=first_item.get("size"),
                        price=first_item.get("price", {}).get("regular"),
                        categories=item.get("categories"),
                    )
                )
            except Exception:
                continue
        return products

    def get_product_detail(
        self,
        product_id: str,
        location_id: Optional[str] = None,
    ) -> Optional[ProductDetail]:
        params = {"filter.productId": self._validate_product_id(product_id)}
        loc = location_id or self.config.default_location_id
        if loc:
            params["filter.locationId"] = self._validate_location_id(loc)

        resp = self._request("GET", "/v1/products", auth_mode="app", params=params)
        products = resp.json().get("data", [])
        if not products:
            return None
        return self._product_detail_from_response(products[0])

    def _product_detail_from_response(self, item: dict) -> ProductDetail:
        product_items = item.get("items") or []
        return ProductDetail(
            upc=item.get("upc", ""),
            product_id=item.get("productId", ""),
            description=item.get("description", ""),
            brand=item.get("brand"),
            categories=item.get("categories"),
            items=[
                ProductItemDetail(
                    item_id=product_item.get("itemId"),
                    size=product_item.get("size"),
                    sold_by=product_item.get("soldBy"),
                    price=product_item.get("price"),
                    fulfillment=product_item.get("fulfillment"),
                    inventory=product_item.get("inventory"),
                )
                for product_item in product_items
            ],
            images=item.get("images"),
            aisle_locations=item.get("aisleLocations"),
            temperature=item.get("temperature"),
            nutrition=item.get("nutrition") or item.get("nutritionInformation"),
            raw=item,
        )

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

            score = self._score_product_preference(
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

        ranked.sort(key=lambda item: (-item.preference_score.total, item.original_kroger_rank))
        return ranked[:limit]

    def _score_product_preference(
        self,
        product: Product,
        detail: Optional[ProductDetail],
        original_rank: int,
        candidate_count: int,
        preferences: PreferenceProfile,
    ) -> ProductPreferenceScore:
        score = 0.0
        reasons = []
        warnings = []
        inspected_fields = ["kroger_rank", "brand"]

        rank_points = max(candidate_count - original_rank + 1, 0) * preferences.kroger_rank_weight
        if rank_points:
            score += rank_points
            reasons.append(f"Kroger result order signal +{rank_points:.2f}")

        brand = (product.brand or (detail.brand if detail else None) or "").strip()
        if brand.lower().startswith("simple truth"):
            score += preferences.simple_truth_bonus
            reasons.append(f"Simple Truth brand +{preferences.simple_truth_bonus:.2f}")

        ingredients, ingredient_fields = self._extract_ingredient_text(detail.raw if detail else None)
        inspected_fields.extend(ingredient_fields)
        if ingredients:
            lowered = ingredients.lower()
            matched_labels = set()
            for rule in preferences.ingredient_rules:
                if rule.keyword.lower() in lowered and rule.label not in matched_labels:
                    score -= rule.penalty
                    matched_labels.add(rule.label)
                    reasons.append(f"Contains {rule.label} -{rule.penalty:.2f}")
        else:
            warnings.append("Ingredients not assessed; Kroger detail did not include ingredient data.")

        nutrition = detail.nutrition if detail and detail.nutrition else None
        if nutrition:
            inspected_fields.append("nutrition")
            score += preferences.nutrition_data_bonus
            reasons.append(f"Nutrition data available +{preferences.nutrition_data_bonus:.2f}")
            health_points = self._health_signal_points(nutrition, preferences.health_score_weight)
            if health_points:
                score += health_points
                reasons.append(f"Health/nutrition signal +{health_points:.2f}")
        else:
            warnings.append("Nutrition signals not assessed; Kroger detail did not include nutrition data.")

        return ProductPreferenceScore(
            total=round(score, 2),
            reasons=reasons,
            warnings=warnings,
            inspected_fields=sorted(set(inspected_fields)),
        )

    def _extract_ingredient_text(self, raw: Optional[dict[str, Any]]) -> tuple[str, list[str]]:
        if not raw:
            return "", []

        values = []
        fields = []

        def visit(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    next_path = f"{path}.{key}" if path else str(key)
                    if "ingredient" in str(key).lower():
                        extracted = self._stringify_ingredient_value(nested)
                        if extracted:
                            values.append(extracted)
                            fields.append(next_path)
                    visit(nested, next_path)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    visit(item, f"{path}[{index}]")

        visit(raw, "raw")
        return " ".join(values), fields

    def _stringify_ingredient_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(self._stringify_ingredient_value(item) for item in value)
        if isinstance(value, dict):
            return " ".join(self._stringify_ingredient_value(item) for item in value.values())
        return ""

    def _health_signal_points(self, nutrition: dict, weight: float) -> float:
        for key in ("healthScore", "nutritionScore", "score", "rating", "optUP"):
            if key not in nutrition:
                continue
            try:
                value = float(nutrition[key])
            except (TypeError, ValueError):
                continue
            if value > 5:
                value = value / 20
            return round(max(min(value, 5), 0) * weight, 2)
        return 0.0

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
        return [self._location_from_response(item) for item in resp.json().get("data", [])]

    def get_location(self, location_id: str) -> Optional[Location]:
        location_id = self._validate_location_id(location_id)
        resp = self._request("GET", f"/v1/locations/{location_id}", auth_mode="app")
        data = resp.json().get("data")
        return self._location_from_response(data) if data else None

    def location_exists(self, location_id: str) -> bool:
        location_id = self._validate_location_id(location_id)
        return self._resource_exists(f"/v1/locations/{location_id}")

    def list_chains(self) -> List[Chain]:
        resp = self._request("GET", "/v1/chains", auth_mode="app")
        return [self._chain_from_response(item) for item in resp.json().get("data", [])]

    def get_chain(self, name: str) -> Optional[Chain]:
        name = self._validate_required_name(name, "Chain name")
        resp = self._request("GET", f"/v1/chains/{quote(name, safe='')}", auth_mode="app")
        data = resp.json().get("data")
        return self._chain_from_response(data) if data else None

    def chain_exists(self, name: str) -> bool:
        name = self._validate_required_name(name, "Chain name")
        return self._resource_exists(f"/v1/chains/{quote(name, safe='')}")

    def list_departments(self) -> List[Department]:
        resp = self._request("GET", "/v1/departments", auth_mode="app")
        return [self._department_from_response(item) for item in resp.json().get("data", [])]

    def get_department(self, department_id: str) -> Optional[Department]:
        department_id = self._validate_department_id(department_id)
        resp = self._request("GET", f"/v1/departments/{department_id}", auth_mode="app")
        data = resp.json().get("data")
        return self._department_from_response(data) if data else None

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

    def _location_from_response(self, item: dict) -> Location:
        address = item.get("address") or {}
        geolocation = item.get("geolocation") or {}
        departments = item.get("departments") or []
        return Location(
            location_id=item.get("locationId", ""),
            name=item.get("name"),
            chain=item.get("chain"),
            phone=item.get("phone"),
            address=LocationAddress(
                address_line1=address.get("addressLine1"),
                address_line2=address.get("addressLine2"),
                city=address.get("city"),
                county=address.get("county"),
                state=address.get("state"),
                zip_code=address.get("zipCode"),
                raw=address,
            ) if address else None,
            geolocation=GeoLocation(
                lat_lng=geolocation.get("latLng"),
                latitude=geolocation.get("latitude"),
                longitude=geolocation.get("longitude"),
                raw=geolocation,
            ) if geolocation else None,
            departments=[
                LocationDepartment(
                    department_id=department.get("departmentId", ""),
                    name=department.get("name", ""),
                    phone=department.get("phone"),
                    hours=department.get("hours"),
                    raw=department,
                )
                for department in departments
            ],
            hours=item.get("hours"),
            store_number=item.get("storeNumber"),
            division_number=item.get("divisionNumber"),
            raw=item,
        )

    def _chain_from_response(self, item: dict) -> Chain:
        return Chain(
            name=item.get("name", ""),
            division_numbers=item.get("divisionNumbers"),
            domain=item.get("domain"),
            friendly_banner_name=item.get("friendlyBannerName"),
            default_title=item.get("defaultTitle"),
            title_extension=item.get("titleExtension"),
            apple_app_id=item.get("appleAppId"),
            google_app_id=item.get("googleAppId"),
            theme_color=item.get("themeColor"),
            description=item.get("description"),
            modality_capabilities=item.get("modalityCapabilities"),
            raw=item,
        )

    def _department_from_response(self, item: dict) -> Department:
        return Department(
            department_id=item.get("departmentId", ""),
            name=item.get("name", ""),
            raw=item,
        )

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
