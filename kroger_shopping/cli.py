import argparse
import sys
from typing import Callable, Optional, Sequence

from . import validation
from .client import KrogerClient
from .exceptions import KrogerError, KrogerValidationError
from .models import CartModality
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
    search.add_argument("--limit", type=int, default=6)

    recommend = subparsers.add_parser("recommend", help="Rank Kroger products by local preferences")
    recommend.add_argument("term", nargs="+")
    recommend.add_argument("--limit", type=int, default=6)

    add = subparsers.add_parser("add", help="Add a UPC to the Kroger cart")
    add.add_argument("upc")
    add.add_argument("--quantity", default="1")
    add.add_argument("--modality", default=CartModality.PICKUP.value)

    subparsers.add_parser("status", help="Check Kroger user authentication status")
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    client_factory: ClientFactory = KrogerClient,
) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        client = client_factory()

        if args.command == "search":
            return _search(client, " ".join(args.term), args.limit)
        if args.command == "recommend":
            return _recommend(client, " ".join(args.term), args.limit)
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


def _recommend(client: KrogerClient, term: str, limit: int) -> int:
    ranked = client.ranked_search_products(term, limit=limit)
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
        metadata = (
            f"{_format_price(product.price)} | {product.upc} "
            f"| size: {_format_optional_text(product.size)} "
            f"| unit: {format_unit_price_for_products(product, products)} | unwanted: {unwanted}"
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


def _format_product_line(description: str, brand: Optional[str], price: Optional[float], upc: str) -> str:
    brand_text = f" - {brand}" if brand else ""
    return f"{description}{brand_text} | {_format_price(price)} | {upc}"


def _format_price(price: Optional[float]) -> str:
    if price is None:
        return "N/A"
    return f"${price:.2f}"


def _format_optional_text(value: Optional[str]) -> str:
    return value if value else "N/A"
