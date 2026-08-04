import shlex
from typing import Optional, Sequence

from .client import KrogerClient
from .exceptions import KrogerError, KrogerValidationError
from .recommendations import is_temporarily_out_of_stock
from .unit_pricing import format_unit_price_for_products


_client: Optional[KrogerClient] = None


def get_client() -> KrogerClient:
    global _client
    if _client is None:
        _client = KrogerClient()
    return _client


def help_text() -> str:
    return (
        "Kroger commands:\n"
        "- /kroger search <term>\n"
        "- /kroger recommend <term>\n"
        "- /kroger add <UPC> [qty]\n"
        "- /kroger login\n"
        "- /kroger code <authorization-code>\n"
        "- /kroger status\n"
        "- /kroger logout"
    )


def handle_kroger(raw_args: str = "") -> str:
    """Handle /kroger without invoking an agent tool or shell command."""
    try:
        argv = shlex.split(raw_args or "")
    except ValueError as exc:
        return f"Validation error: {exc}"

    if not argv:
        return help_text()

    return handle_kroger_args(argv[0], argv[1:])


def handle_kroger_args(subcommand: str, args: Sequence[str]) -> str:
    subcommand = subcommand.lower()

    if subcommand == "search":
        if not args:
            return "Usage: /kroger search <term>"
        client = get_client()
        term = " ".join(args)
        try:
            results = client.search_products(term, limit=10)
            if not results:
                return "No products found."
            lines = []
            for result in results:
                price = f"${result.price}" if result.price else "N/A"
                lines.append(
                    f"**{result.description}** - {result.brand or ''} "
                    f"| {price} | `{result.upc}`"
                )
            return "\n".join(lines)
        except KrogerError as exc:
            return f"Error: {exc}"

    if subcommand == "recommend":
        if not args:
            return "Usage: /kroger recommend <term>"
        client = get_client()
        term = " ".join(args)
        try:
            results = client.ranked_search_products(term, limit=10)
            if not results:
                return "No products found."
            lines = []
            products = [item.product for item in results]
            for result in results:
                product = result.product
                score = result.preference_score
                price = f"${product.price}" if product.price else "N/A"
                size = product.size or "N/A"
                unit = format_unit_price_for_products(product, products)
                unwanted = (
                    str(score.unwanted_ingredient_count)
                    if score.unwanted_ingredient_count is not None
                    else "unknown"
                )
                matches = "; ".join(score.unwanted_ingredients[:3])
                if len(score.unwanted_ingredients) > 3:
                    matches = f"{matches}; +{len(score.unwanted_ingredients) - 3} more"
                match_text = f" | matches: {matches}" if matches else ""
                purchased = " | purchased: yes" if result.previously_purchased else ""
                out_of_stock = (
                    " | out of stock"
                    if is_temporarily_out_of_stock(result.detail)
                    else ""
                )
                metadata = (
                    f"{price} | `{product.upc}` "
                    f"| size: {size} | unit: {unit} | unwanted: {unwanted}"
                    f"{purchased}{out_of_stock}{match_text}"
                )
                lines.append(f"**{product.description}**\n{metadata}")
            return "\n\n".join(lines)
        except KrogerValidationError as exc:
            return f"Validation error: {exc}"
        except KrogerError as exc:
            return f"Error: {exc}"

    if subcommand == "add":
        if not args:
            return "Usage: /kroger add <UPC> [quantity=1]"
        client = get_client()
        upc = args[0]
        try:
            quantity = int(args[1]) if len(args) > 1 else 1
        except ValueError:
            return "Validation error: quantity must be a whole number"
        try:
            success = client.add_to_cart(upc, quantity)
            return "Added to cart" if success else "Failed to add"
        except KrogerValidationError as exc:
            return f"Validation error: {exc}"
        except KrogerError as exc:
            return f"Error: {exc}"

    if subcommand == "login":
        client = get_client()
        try:
            url = client.auth.authorization_url()
            return (
                "Open this Kroger authorization URL, sign in, then copy the `code` "
                "query parameter from the redirect URL.\n"
                f"{url}\n\n"
                "Finish with: /kroger code <authorization-code>"
            )
        except KrogerError as exc:
            return f"Error: {exc}"

    if subcommand == "code":
        if not args:
            return "Usage: /kroger code <authorization-code>"
        client = get_client()
        code = " ".join(args).strip()
        try:
            tokens = client.auth.exchange_code_for_tokens(code)
            scope = f" Scope: {tokens.scope}." if tokens.scope else ""
            return f"Kroger authentication saved.{scope}"
        except KrogerError as exc:
            return f"Authentication error: {exc}"

    if subcommand == "status":
        client = get_client()
        try:
            if client.auth.has_valid_user_tokens():
                return "Kroger user authentication is active."
            return "Kroger user authentication is missing or expired. Run /kroger login."
        except KrogerError as exc:
            return f"Authentication status error: {exc}"

    if subcommand == "logout":
        client = get_client()
        client.auth.clear_user_tokens()
        return "Kroger user authentication cleared."

    return f"Unknown subcommand: {subcommand}\n{help_text()}"
