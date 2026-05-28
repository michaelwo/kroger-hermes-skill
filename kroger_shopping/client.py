import requests
from typing import List, Optional

from .config import KrogerConfig
from .auth import KrogerAuthClient
from .models import Product, ProductDetail, ProductItemDetail
from .exceptions import (
    KrogerAuthError,
    KrogerError,
    KrogerValidationError,
    KrogerServerError,
)


class KrogerClient:
    """High-level client for interacting with Kroger APIs."""

    BASE_URL = "https://api.kroger.com"

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
        fulfillment: Optional[str] = None,
        brand: Optional[str] = None,
    ) -> List[Product]:
        if len(term) < 3:
            raise KrogerValidationError("Search term must be at least 3 characters")

        params = {"filter.term": term, "filter.limit": min(limit, 50)}
        loc = location_id or self.config.default_location_id
        if loc:
            params["filter.locationId"] = loc
        if fulfillment:
            params["filter.fulfillment"] = fulfillment
        if brand:
            params["filter.brand"] = brand

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
        if not product_id.strip():
            raise KrogerValidationError("Product ID is required")

        params = {"filter.productId": product_id.strip()}
        loc = location_id or self.config.default_location_id
        if loc:
            params["filter.locationId"] = loc

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
            nutrition=item.get("nutrition"),
            raw=item,
        )

    def add_to_cart(self, upc: str, quantity: int = 1, modality: str = "PICKUP") -> bool:
        if len(upc) != 13 or not upc.isdigit():
            raise KrogerValidationError("UPC must be exactly 13 digits")
        if quantity < 1:
            raise KrogerValidationError("Quantity must be at least 1")

        payload = {"items": [{"upc": upc, "quantity": quantity, "modality": modality}]}
        resp = self._request(
            "PUT",
            "/v1/cart/add",
            auth_mode="user",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        return resp.status_code in (200, 201, 204)
