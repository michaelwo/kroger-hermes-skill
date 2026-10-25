"""Public, presentation-safe payloads shared by Kroger integrations."""

from typing import Any, Sequence

from .recommendations import is_temporarily_out_of_stock
from .unit_pricing import format_unit_price_for_products


RECOMMENDATIONS_SCHEMA = "kroger.recommendations.v1"


def recommendation_products(ranked: Sequence[Any]) -> list[dict[str, Any]]:
    products = [item.product for item in ranked]
    payloads = []
    for item in ranked:
        product = item.product
        unwanted_count = item.preference_score.unwanted_ingredient_count
        payloads.append(
            {
                "description": product.description,
                "brand": product.brand,
                "upc": product.upc,
                "price": product.price,
                "size": product.size,
                "unit_price": format_unit_price_for_products(product, products),
                "unwanted_ingredient_count": unwanted_count,
                "unwanted_ingredients": item.preference_score.unwanted_ingredients,
                "ingredient_data_known": unwanted_count is not None,
                "previously_purchased": item.previously_purchased,
                "last_purchased_date": item.last_purchased_date,
                "buy_and_save": item.on_buy_and_save,
                "out_of_stock": is_temporarily_out_of_stock(item.detail),
            }
        )
    return payloads
