# Kroger Shopping Skill

API-first Kroger shopping client and Hermes slash-command skill. It supports product search, product detail parsing, local recommendation ranking, OAuth token management, and adding items to a Kroger cart.

## Disclaimer

This project is an independent, unofficial client and is not affiliated with, endorsed by, sponsored by, or approved by The Kroger Co., Kroger, or Simple Truth. Kroger and Simple Truth are trademarks of their respective owners.

## Features

- Product search with location, brand, limit, and fulfillment filters
- Product detail lookup through `GET /v1/products/{id}` with typed price, availability, inventory, nutrition, allergen, and raw payload access
- Recommended search that ranks by Simple Truth unwanted ingredient count first, then local preference score, then Kroger result order
- Cart add/increase support through `PUT /v1/cart/add`
- OAuth2 authorization-code flow for cart writes, with token refresh and secure token file permissions
- Slash commands under `/kroger`

## Configuration

Set these environment variables before using the live Kroger APIs:

```bash
export KROGER_CLIENT_ID=your_client_id
export KROGER_CLIENT_SECRET=your_client_secret
export KROGER_DEFAULT_LOCATION_ID=02100998   # optional
export KROGER_DEFAULT_FULFILLMENT=csp        # optional: ais, csp, dth, sth
export KROGER_TOKEN_FILE=~/.kroger_tokens.json # optional
```

`KROGER_DEFAULT_LOCATION_ID` is used when a search/detail call does not pass `location_id`. Location-specific product calls are needed for price, fulfillment, aisle, and inventory fields. `KROGER_TOKEN_FILE` stores user OAuth tokens for cart writes and should never be committed.

## Slash Commands

```text
/kroger search <term>
/kroger recommend <term>
/kroger add <UPC> [quantity]
/kroger login
/kroger code <authorization-code>
/kroger status
/kroger logout
```

`/kroger recommend` returns product summaries with an `unwanted` count. The count is based on a committed snapshot of Kroger Simple Truth food ingredient exclusions. Products with fewer detected unwanted ingredients rank higher; products with missing ingredient data show `unwanted: unknown`.

## Python Usage

```python
from kroger_shopping import KrogerClient, CartModality

client = KrogerClient()

products = client.search_products("ranch", limit=5, location_id="02100998")
ranked = client.ranked_search_products("ranch", limit=5, candidate_limit=10)
detail = client.get_product_detail(products[0].product_id, location_id="02100998")

client.add_to_cart("0001111050434", quantity=2, modality=CartModality.PICKUP)
```

Recommended results include `preference_score.unwanted_ingredient_count`, `unwanted_ingredients`, `ingredient_match_details`, `reasons`, `warnings`, and inspected source fields.

## Architecture

- `kroger_shopping/models.py` - domain models, enums, scoring metadata, Simple Truth exclusion rules
- `kroger_shopping/validation.py` - input validators and API limit constants
- `kroger_shopping/parsers.py` - Kroger response-to-model mapping
- `kroger_shopping/recommendations.py` - ingredient extraction, Simple Truth matching, and ranking helpers
- `kroger_shopping/auth.py` - OAuth2 token requests, refresh, storage, and authorization URL generation
- `kroger_shopping/client.py` - public Kroger API facade, request handling, and auth retry behavior
- `commands/kroger.py` - Hermes slash-command handlers
- `tests/test_basic.py` - unit and contract tests
- `references/openapi/*.openapi.json` - committed Kroger OpenAPI source documents

## Development

Run the unit suite:

```bash
python -m pytest
```

The unit suite uses fakes and OpenAPI contract fixtures; it does not require live Kroger credentials. Live smoke tests are useful for manual verification but should be run intentionally because they call the Kroger API.

## API Constraints

- Product search stays on `GET /v1/products`.
- Product detail uses `GET /v1/products/{id}`.
- Product search fulfillment filters use `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment response fields are booleans: `curbside`, `delivery`, `instore`, and `shiptohome`.
- Cart add payload is `{"items": [{"upc": "...", "quantity": N, "modality": "PICKUP"}]}`.
- Cart modality values are `PICKUP` and `DELIVERY`.

## Limitations

- Cart support is add/increase only; Kroger does not expose a documented remove/decrement endpoint in the referenced API.
- Ingredient ranking is keyword/alias matching against Kroger ingredient text, not medical, nutrition, or toxicology scoring.
- Raw Kroger payloads remain available for fields that are not yet modeled.
