import re
import shlex
from pathlib import Path
from typing import Optional, Sequence

from . import receipts
from .client import KrogerClient
from .exceptions import KrogerError, KrogerValidationError
from .recommendations import is_temporarily_out_of_stock
from .unit_pricing import format_unit_price_for_products


_SHORTCUTS = {"-s": "search", "-r": "recommend", "-a": "add"}

_client: Optional[KrogerClient] = None


def get_client() -> KrogerClient:
    global _client
    if _client is None:
        _client = KrogerClient()
    return _client


def help_text() -> str:
    return (
        "Kroger commands:\n"
        "- /kroger search <term> (shortcut: -s)\n"
        "- /kroger recommend <term> (shortcut: -r)\n"
        "- /kroger add <UPC> [qty] (shortcut: -a)\n"
        "- /kroger receipts\n"
        "- /kroger pull\n"
        "- /kroger buyagain\n"
        "- /kroger clipcoupon all\n"
        "- /kroger clipcoupon all --dry-run\n"
        "- /kroger version\n"
        "- /kroger login\n"
        "- /kroger code <authorization-code>\n"
        "- /kroger status\n"
        "- /kroger logout\n"
        "- /kroger -h (help)"
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
    if subcommand == "-h":
        return help_text()
    subcommand = _SHORTCUTS.get(subcommand, subcommand)

    if subcommand == "version":
        if args:
            return "Usage: /kroger version"
        manifest = Path(__file__).resolve().parents[1] / "plugin.yaml"
        match = re.search(r'^version:\s*[\"\']?([^\s\"\']+)', manifest.read_text(encoding="utf-8"), re.MULTILINE)
        if match is None:
            return "Plugin version is unavailable."
        return match.group(1)

    if subcommand == "buyagain":
        if args:
            return "Usage: /kroger buyagain"
        return _buy_again_text()

    if subcommand == "receipts":
        if args:
            return "Usage: /kroger receipts"
        return _receipt_history_text()

    if subcommand == "pull":
        if args:
            return "Usage: /kroger pull"
        return _pull_purchase_history_text()

    if subcommand == "clipcoupon":
        return _clipcoupon_text(args)

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
                purchased = ""
                if result.previously_purchased and result.last_purchased_date:
                    purchased += f" | lp: {result.last_purchased_date}"
                out_of_stock = (
                    " | out of stock"
                    if is_temporarily_out_of_stock(result.detail)
                    else ""
                )
                metadata = (
                    f"{price} | `{product.upc}` "
                    f"| sz: {size} | pu: {unit} | unwntd: {unwanted}"
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
            if not success:
                return "Failed to add"
        except KrogerValidationError as exc:
            return f"Validation error: {exc}"
        except KrogerError as exc:
            return f"Error: {exc}"
        title = "Title unavailable"
        try:
            product = client.get_product_detail(upc.strip())
            if product and product.description:
                title = product.description
        except KrogerError:
            pass
        return f"Added to cart: {title} | UPC: `{upc.strip()}` | Quantity: {quantity}"

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


def _pull_purchase_history_text() -> str:
    from .purchase_history import CdpError, pull_purchase_history

    try:
        result = pull_purchase_history()
    except CdpError as exc:
        return str(exc)
    return (
        f"Wrote {result['orders']} orders to `{result['path']}`.{chr(10)}"
        f"Titles on {result.get('titled', 0)} orders.{chr(10)}"
        "Open `/kroger receipts` to list them."
    )


def _clipcoupon_text(args: Sequence[str]) -> str:
    from .clipcoupon import clip, dry_run
    from .purchase_history import CdpError

    wanted = list(args)
    if wanted == ["all", "--dry-run"]:
        runner = dry_run
    elif wanted == ["all"]:
        runner = clip
    else:
        return "Usage: /kroger clipcoupon all [--dry-run]"
    try:
        return runner()
    except CdpError as exc:
        return str(exc)


def _receipt_history_text() -> str:
    history = receipts.load_receipt_history()
    if not history:
        return "No local purchase history found."
    lines = []
    for receipt in sorted(history, key=lambda item: item.filename):
        if not receipt.readable:
            lines.append(f"- {receipt.filename}: Unreadable receipt.")
        else:
            number = receipt.order_number or "Unavailable"
            date = receipt.order_date or "Unavailable"
            line = f"- Order number: {number} | Order date: {date}"
            if not receipt.order_number or not receipt.order_date:
                line += f" ({receipt.filename})"
            lines.append(line)
    return "\n".join(lines)


def _buy_again_text() -> str:
    upcs = sorted(receipts.load_purchase_upcs())
    if not upcs:
        return "No purchased UPCs found in local receipts."

    names = receipts.load_purchase_names()

    lines = [f"Previously purchased products: {len(upcs)}"]
    if len(names) != len(upcs):
        lines.append("Some product names are missing from local history. Run /kroger pull to refresh.")
    lines.extend(f"- {names.get(upc, 'Name unavailable')} | UPC: `{upc}`" for upc in upcs)
    return "\n".join(lines)
