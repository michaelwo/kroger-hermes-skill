import argparse
import json
import sys
from typing import Callable, Optional, Sequence

from . import recommendations, validation
from .client import KrogerClient
from .exceptions import KrogerError, KrogerValidationError
from .hermes_command import buysave_marker
from .models import CartModality
from .public_payloads import RECOMMENDATIONS_SCHEMA, recommendation_products
from .unit_pricing import format_unit_price_for_products


ClientFactory = Callable[[], KrogerClient]


class KrogerArgumentParser(argparse.ArgumentParser):
    def error(self, message: str):
        raise KrogerValidationError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = KrogerArgumentParser(prog="python -m kroger_shopping")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=KrogerArgumentParser)

    search = subparsers.add_parser("search", help="Search Kroger products")
    search.add_argument("term", nargs="+")
    search.add_argument("--limit", type=int, default=10)

    recommend = subparsers.add_parser("recommend", help="Rank Kroger products by local preferences")
    recommend.add_argument("term", nargs="+")
    recommend.add_argument("--limit", type=int, default=10)
    recommend.add_argument("--json", action="store_true", dest="json_output")

    add = subparsers.add_parser("add", help="Add a UPC to the Kroger cart")
    add.add_argument("upc")
    add.add_argument("--quantity", default="1")
    add.add_argument("--modality", default=CartModality.PICKUP.value)

    subparsers.add_parser("status", help="Check Kroger user authentication status")
    subparsers.add_parser("pull", help="Export purchase history from a logged-in CDP Chrome tab")
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    client_factory: ClientFactory = KrogerClient,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "pull":
            return _pull()
        client = client_factory()

        if args.command == "search":
            return _search(client, " ".join(args.term), args.limit)
        if args.command == "recommend":
            return _recommend(client, " ".join(args.term), args.limit, json_output=args.json_output)
        if args.command == "add":
            return _add(client, args.upc, args.quantity, args.modality)
        if args.command == "status":
            return _status(client)

        parser.print_help()
        return 2
    except KrogerValidationError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        return 2
    except KrogerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _search(client: KrogerClient, term: str, limit: int) -> int:
    products = client.search_products(term, limit=limit)
    if not products:
        print("No products found.")
        return 0
    for product in products:
        print(_format_product_line(product.description, product.brand, product.price, product.upc))
    return 0


def _recommend(client: KrogerClient, term: str, limit: int, *, json_output: bool = False) -> int:
    ranked = client.ranked_search_products(term, limit=limit)
    if json_output:
        print(
            json.dumps(
                {
                    "schema": RECOMMENDATIONS_SCHEMA,
                    "success": True,
                    "query": term,
                    "products": recommendation_products(ranked),
                }
            )
        )
        return 0
    if not ranked:
        print("No products found.")
        return 0
    products = [item.product for item in ranked]
    blocks = []
    for item in ranked:
        product = item.product
        score = item.preference_score
        unwanted = (
            str(score.unwanted_ingredient_count)
            if score.unwanted_ingredient_count is not None
            else "unknown"
        )
        purchased = ""
        if item.previously_purchased and item.last_purchased_date:
            purchased += f" | lp: {item.last_purchased_date}"
        out_of_stock = (
            " | out of stock"
            if recommendations.is_temporarily_out_of_stock(item.detail)
            else ""
        )
        metadata = (
            f"{_format_price(product.price)} | {product.upc}{buysave_marker(item.on_buy_and_save)} "
            f"| sz: {_format_optional_text(product.size)} "
            f"| pu: {format_unit_price_for_products(product, products)} "
            f"| unwntd: {unwanted}{purchased}{out_of_stock}"
        )
        blocks.append(f"{product.description}\n{metadata}")
    print("\n\n".join(blocks))
    return 0


def _add(client: KrogerClient, upc: str, quantity_value: str, modality_value: str) -> int:
    try:
        quantity = int(quantity_value)
    except (TypeError, ValueError) as exc:
        raise KrogerValidationError("Quantity must be a whole number") from exc

    modality = validation.validate_cart_modality(modality_value)
    success = client.add_to_cart(upc, quantity=quantity, modality=modality)
    if not success:
        print("Failed to add to cart.")
        return 1

    print(f"Added to cart: UPC {upc.strip()}, quantity {quantity}, modality {modality.value}.")
    return 0


def _status(client: KrogerClient) -> int:
    if client.auth.has_valid_user_tokens():
        print("Kroger user authentication is active.")
    else:
        print("Kroger user authentication is missing or expired. Run /kroger login.")
    return 0


def _pull(fetcher=None) -> int:
    from .cdp_backend import CDPFetcher

    result = (fetcher or CDPFetcher()).pull_purchase_history()
    print(f"Wrote {result['orders']} orders to {result['path']}.")
    return 0


def _format_product_line(description: str, brand: Optional[str], price: Optional[float], upc: str) -> str:
    brand_text = f" - {brand}" if brand else ""
    return f"{description}{brand_text} | {_format_price(price)} | {upc}"


def _format_price(price: Optional[float]) -> str:
    if price is None:
        return "N/A"
    return f"${price:.2f}"


def _format_optional_text(value: Optional[str]) -> str:
    return value if value else "N/A"
