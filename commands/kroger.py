from hermes.commands import command
from kroger_shopping import KrogerClient, KrogerValidationError
from kroger_shopping.exceptions import KrogerError

_client = None


def get_client():
    global _client
    if _client is None:
        _client = KrogerClient()
    return _client


def _help_text():
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


@command("kroger")
async def kroger_command(ctx, subcommand: str = None, *args):
    """Kroger shopping commands"""
    client = get_client()

    if not subcommand:
        return _help_text()

    subcommand = subcommand.lower()

    if subcommand == "search":
        if not args:
            return "Usage: /kroger search <term>"
        term = " ".join(args)
        try:
            results = client.search_products(term, limit=6)
            if not results:
                return "No products found."
            lines = []
            for r in results:
                price = f"${r.price}" if r.price else "N/A"
                lines.append(f"**{r.description}** - {r.brand or ''} | {price} | `{r.upc}`")
            return "\n".join(lines)
        except KrogerError as e:
            return f"Error: {e}"

    if subcommand == "recommend":
        if not args:
            return "Usage: /kroger recommend <term>"
        term = " ".join(args)
        try:
            results = client.ranked_search_products(term, limit=6)
            if not results:
                return "No products found."
            lines = []
            for r in results:
                product = r.product
                score = r.preference_score
                price = f"${product.price}" if product.price else "N/A"
                unwanted = (
                    str(score.unwanted_ingredient_count)
                    if score.unwanted_ingredient_count is not None
                    else "unknown"
                )
                matches = "; ".join(score.unwanted_ingredients[:3])
                if len(score.unwanted_ingredients) > 3:
                    matches = f"{matches}; +{len(score.unwanted_ingredients) - 3} more"
                match_text = f" | matches: {matches}" if matches else ""
                reasons = "; ".join(score.reasons[:3]) or "No preference signals available"
                warnings = f" Warning: {'; '.join(score.warnings[:1])}" if score.warnings else ""
                lines.append(
                    f"**{product.description}** - {product.brand or ''} | {price} | `{product.upc}` "
                    f"| unwanted: {unwanted}{match_text} | score {score.total:.2f} | {reasons}{warnings}"
                )
            return "\n".join(lines)
        except KrogerValidationError as e:
            return f"Validation error: {e}"
        except KrogerError as e:
            return f"Error: {e}"


    if subcommand == "add":
        if not args:
            return "Usage: /kroger add <UPC> [quantity=1]"
        upc = args[0]
        try:
            qty = int(args[1]) if len(args) > 1 else 1
        except ValueError:
            return "Validation error: quantity must be a whole number"
        try:
            success = client.add_to_cart(upc, qty)
            return "Added to cart" if success else "Failed to add"
        except KrogerValidationError as e:
            return f"Validation error: {e}"
        except KrogerError as e:
            return f"Error: {e}"

    if subcommand == "login":
        try:
            url = client.auth.authorization_url()
            return (
                "Open this Kroger authorization URL, sign in, then copy the `code` "
                "query parameter from the redirect URL.\n"
                f"{url}\n\n"
                "Finish with: /kroger code <authorization-code>"
            )
        except KrogerError as e:
            return f"Error: {e}"

    if subcommand == "code":
        if not args:
            return "Usage: /kroger code <authorization-code>"
        code = " ".join(args).strip()
        try:
            tokens = client.auth.exchange_code_for_tokens(code)
            scope = f" Scope: {tokens.scope}." if tokens.scope else ""
            return f"Kroger authentication saved.{scope}"
        except KrogerError as e:
            return f"Authentication error: {e}"

    if subcommand == "status":
        try:
            if client.auth.has_valid_user_tokens():
                return "Kroger user authentication is active."
            return "Kroger user authentication is missing or expired. Run /kroger login."
        except KrogerError as e:
            return f"Authentication status error: {e}"

    if subcommand == "logout":
        client.auth.clear_user_tokens()
        return "Kroger user authentication cleared."

    return f"Unknown subcommand: {subcommand}\n{_help_text()}"
