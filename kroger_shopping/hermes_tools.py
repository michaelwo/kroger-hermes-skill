"""Structured, read-only Hermes tools backed by the Kroger client."""

import json
from typing import Any, Optional

from .exceptions import KrogerError, KrogerValidationError
from .hermes_command import get_client
from .recommendations import is_temporarily_out_of_stock
from .unit_pricing import format_unit_price_for_products


SEARCH_SCHEMA = {
    "name": "kroger_search",
    "description": "Search Kroger products without ranking them by local preferences.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Product search phrase"},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

RECOMMEND_SCHEMA = {
    "name": "kroger_recommend",
    "description": "Find and rank Kroger products using local shopping preferences.",
    "parameters": SEARCH_SCHEMA["parameters"],
}

AUTH_STATUS_SCHEMA = {
    "name": "kroger_auth_status",
    "description": "Check whether Kroger user authentication is active.",
    "parameters": {"type": "object", "properties": {}},
}


def handle_search(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    try:
        query, limit = _query_and_limit(params)
        products = get_client().search_products(query, limit=limit)
        return _success(
            query=query,
            products=[_product_payload(product) for product in products],
        )
    except (KrogerValidationError, KrogerError, TypeError, ValueError) as exc:
        return _error(exc)


def handle_recommend(params: dict[str, Any], **kwargs: Any) -> str:
    del kwargs
    try:
        query, limit = _query_and_limit(params)
        ranked = get_client().ranked_search_products(query, limit=limit)
        products = [item.product for item in ranked]
        payloads = []
        for item in ranked:
            payload = _product_payload(item.product, products)
            payload.update(
                {
                    "unwanted_ingredient_count": (
                        item.preference_score.unwanted_ingredient_count
                    ),
                    "unwanted_ingredients": item.preference_score.unwanted_ingredients,
                    "ingredient_data_known": (
                        item.preference_score.unwanted_ingredient_count is not None
                    ),
                    "previously_purchased": item.previously_purchased,
                    "out_of_stock": is_temporarily_out_of_stock(item.detail),
                }
            )
            payloads.append(payload)
        return _success(query=query, products=payloads)
    except (KrogerValidationError, KrogerError, TypeError, ValueError) as exc:
        return _error(exc)


def handle_auth_status(params: dict[str, Any], **kwargs: Any) -> str:
    del params, kwargs
    try:
        return json.dumps(
            {
                "success": True,
                "authenticated": get_client().auth.has_valid_user_tokens(),
            }
        )
    except (KrogerValidationError, KrogerError, TypeError, ValueError) as exc:
        return _error(exc)


def _query_and_limit(params: dict[str, Any]) -> tuple[str, int]:
    query = str(params.get("query", "")).strip()
    if not query:
        raise KrogerValidationError("query is required")
    limit = int(params.get("limit", 10))
    return query, limit


def _product_payload(product: Any, products: Optional[list[Any]] = None) -> dict[str, Any]:
    payload = {
        "description": product.description,
        "brand": product.brand,
        "upc": product.upc,
        "price": product.price,
        "size": product.size,
    }
    if products is not None:
        payload["unit_price"] = format_unit_price_for_products(product, products)
    return payload


def _success(**payload: Any) -> str:
    return json.dumps({"success": True, **payload})


def _error(exc: Exception) -> str:
    return json.dumps({"success": False, "error": str(exc)})
