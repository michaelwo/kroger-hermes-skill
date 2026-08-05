# Kroger Shopping for Hermes

API-first Kroger shopping client with a Hermes plugin, deterministic slash
commands, structured read-only agent tools, and a bundled conversational skill.
It supports product discovery, local recommendation ranking, OAuth token
management, and Kroger cart adds.

## Disclaimer

This project is an independent, unofficial client and is not affiliated with,
endorsed by, sponsored by, or approved by The Kroger Co., Kroger, or Simple
Truth. Kroger and Simple Truth are trademarks of their respective owners.

## Interaction Paths

| Path | LLM turn | Purpose |
| --- | --- | --- |
| `/kroger ...` | No | Fast, deterministic search, recommendations, authentication, and cart adds |
| `kroger-shopping:shopping-assistant` | Yes | Conversational product discovery and comparison through read-only tools |
| `python -m kroger_shopping ...` | No | Predictable terminal and automation interface |

The plugin registers one slash command, three read-only tools
(`kroger_search`, `kroger_recommend`, and `kroger_auth_status`), and the
namespaced `kroger-shopping:shopping-assistant` skill. It deliberately does not
expose a cart-write tool to the LLM.

## Features

- Product search with location, brand, limit, and fulfillment filters
- Product detail mapping with typed price, availability, inventory, nutrition,
  allergen, and raw payload access
- Receipt-aware recommendations with unwanted-ingredient and unit-price ranking
- Cart add/increase support through `PUT /v1/cart/add`
- OAuth2 authorization-code flow for cart writes, including refresh and
  token-file persistence with restrictive permissions
- Direct `/kroger` commands for Hermes TUI and messaging gateways
- Optional conversational shopping through plugin-bundled skill and tools
- Low-noise module CLI for terminal and automation use

## Installation

### Python dependencies

Install the runtime dependencies into the same Python environment that runs
Hermes:

```bash
python -m pip install -r requirements.txt
```

When Hermes uses a dedicated virtual environment, target it explicitly. For
example:

```bash
uv pip install \
  --python /opt/hermes/.venv/bin/python \
  -r /opt/data/plugins/kroger-shopping/requirements.txt
```

Receipt parsing requires `pypdf`; OCR is not used.

### Hermes plugin

Install and enable the repository plugin:

```bash
hermes plugins install michaelwo/kroger-hermes-skill --enable
```

For a local checkout, place or symlink the complete repository at
`~/.hermes/plugins/kroger-shopping`, then enable it:

```bash
hermes plugins enable kroger-shopping
```

Update an existing Git-based installation with:

```bash
hermes plugins update kroger-shopping
```

Restart the gateway process or container after installing, updating, enabling,
or changing the plugin. Existing agent sessions may cache their tool prompt, so
start a fresh TUI or gateway session with `/reset` after tool or skill changes.

Verify from the host or TUI:

```bash
hermes plugins list
hermes logs --level WARNING
```

In a running TUI session, `/plugins` should show the loaded plugin. Telegram
does not necessarily expose management commands such as `/plugins`.

The Kroger plugin defines new tool names and does not need permission to
override Hermes built-in tools.

### Telegram command access

The plugin registers `/kroger` with the gateway. If Telegram command tiers are
enabled, add `kroger` to `user_allowed_commands` and/or
`group_user_allowed_commands` for the intended non-admin users.

The conversational skill does not create `/kroger-shopping` or another
Telegram slash command. Plugin-provided skills are explicitly loaded by their
qualified name and do not appear in Hermes `skills_list`. In a fresh session,
send a normal message such as:

```text
Load kroger-shopping:shopping-assistant using skill_view, then help me compare lactose-free milk.
```

A proposed short `/shop` Telegram alias is documented but not implemented in
`docs/plans/telegram-shopping-skill-alias.md`.

## Configuration

Set the Kroger credentials in the environment used by the Hermes process:

```bash
export KROGER_CLIENT_ID=your_client_id
export KROGER_CLIENT_SECRET=your_client_secret
```

Optional settings:

```bash
export KROGER_REDIRECT_URI=http://localhost:8080/callback
export KROGER_DEFAULT_LOCATION_ID=02100998
export KROGER_DEFAULT_FULFILLMENT=csp
export KROGER_TOKEN_FILE=~/.kroger_tokens.json
```

`KROGER_DEFAULT_FULFILLMENT` accepts `ais`, `csp`, `dth`, or `sth`.
Location-specific product calls are needed for price, fulfillment, aisle, and
inventory data. The token file contains user OAuth credentials, is written with
`0600` permissions, and must never be committed.

## Direct Slash Commands

```text
/kroger search <term>
/kroger recommend <term>
/kroger add <UPC> [quantity]
/kroger login
/kroger code <authorization-code>
/kroger status
/kroger logout
```

These commands dispatch directly without an agent turn or shell command.
`/kroger recommend` returns compact product blocks with price, UPC, size, unit
price, unwanted count, purchase history, stock status, and up to three actual
unwanted-ingredient matches. It intentionally omits internal score reasons,
warnings, and aggregate scores.

The manual OAuth workflow for containerized gateways is:

1. Run `/kroger login`.
2. Open the returned Kroger authorization URL and approve access.
3. Copy the `code` query parameter from the redirect URL.
4. Run `/kroger code <authorization-code>`.
5. Confirm with `/kroger status`.

## Conversational Skill and Tools

The read-only skill uses:

- `kroger_recommend` for ranked discovery
- `kroger_search` for ordinary product lookup
- `kroger_auth_status` when authentication state is relevant

Structured recommendation results expose product identity, price, size, unit
price, unwanted count and matches, whether ingredient data is known, purchase
history, and explicit temporary out-of-stock status. They do not expose
internal ranking reasons. After product selection, the skill gives the user a
deterministic `/kroger add <UPC> [quantity]` command rather than modifying the
cart itself.

## Recommendation Behavior

Recommended search fetches up to 25 candidates by default and attempts product
detail reads so ingredient data can be inspected. Detail failures do not abort
the whole recommendation.

The final ordering is:

1. Previously purchased UPCs before unpurchased UPCs
2. Known ingredient data before unknown data, then fewer unwanted matches
3. Known unit prices before unknown unit prices, then lower unit price
4. Higher local preference score
5. Original Kroger result order

Ingredient data that is absent is `unknown`, never zero unwanted ingredients.
Matching is explainable keyword/alias matching against a committed snapshot of
Simple Truth unwanted food ingredients; it is not medical advice, toxicity
scoring, or a claim that a product is unsafe.

Place local Kroger receipt PDFs in:

```text
receipts/*.pdf
```

The loader extracts exact 13-digit `UPC:` lines, deduplicates them, and refreshes
its cache when PDF metadata changes. Invalid PDFs produce warnings while valid
receipts continue to load. Receipt PDFs are local-only and ignored by Git.

Only `TEMPORARILY_OUT_OF_STOCK` is rendered as `out of stock`. `HIGH`, `LOW`,
missing, and unavailable inventory states remain unmarked and do not affect
ranking.

## Module CLI

```text
python -m kroger_shopping search <term> [--limit N]
python -m kroger_shopping recommend <term> [--limit N]
python -m kroger_shopping add <UPC> [--quantity N] [--modality PICKUP|DELIVERY]
python -m kroger_shopping status
```

The module CLI is deterministic. It does not include the interactive
authorization-code commands; use `/kroger login` and `/kroger code` for that
workflow.

## Python Usage

```python
from kroger_shopping import CartModality, KrogerClient

client = KrogerClient()

products = client.search_products("ranch", limit=5, location_id="02100998")
ranked = client.ranked_search_products("ranch", limit=5, candidate_limit=25)
detail = client.get_product_detail(products[0].product_id, location_id="02100998")

client.add_to_cart(
    "0001111050434",
    quantity=2,
    modality=CartModality.PICKUP,
)
```

Major product and detail models preserve raw Kroger payloads for fields that are
not yet typed. Ranked results retain score reasons, warnings, inspected fields,
unwanted matches, and ingredient-match details for programmatic callers even
though public command and skill output hides internal score mechanics.

## Architecture

- `kroger_shopping/models.py` — domain models, enums, scoring metadata, and
  Simple Truth rules
- `kroger_shopping/validation.py` — validators and API limit constants
- `kroger_shopping/parsers.py` — Kroger response-to-model mapping
- `kroger_shopping/recommendations.py` — ingredient matching and ranking
- `kroger_shopping/unit_pricing.py` — size parsing and comparable unit prices
- `kroger_shopping/receipts.py` — local PDF UPC extraction and caching
- `kroger_shopping/auth.py` — OAuth requests, refresh, and token persistence
- `kroger_shopping/client.py` — public API facade, HTTP handling, and auth retry
- `kroger_shopping/hermes_command.py` — current direct `/kroger` presentation
- `kroger_shopping/hermes_tools.py` — structured read-only agent tools
- `skills/shopping-assistant/SKILL.md` — plugin-bundled conversational workflow
- root `plugin.yaml` and `__init__.py` — Hermes manifest and registration
- `commands/kroger.py` — legacy Hermes command compatibility adapter
- `tests/test_basic.py` — unit, output, and OpenAPI contract tests
- `tests/test_hermes_plugin.py` — plugin registration and tool contract tests
- `references/openapi/*.openapi.json` — committed Kroger OpenAPI references
- `docs/plans/` — deferred, explicitly unimplemented design plans

## Development and Verification

Run the offline unit suite:

```bash
python -m pytest
```

Tests use fakes and committed OpenAPI fixtures and should not require live
Kroger credentials. Run live smoke tests only when explicitly intended because
they call Kroger APIs.

When public behavior changes, update command output, structured tool contracts,
tests, and documentation together.

## API Constraints

- Product search uses `GET /v1/products`.
- Product detail uses `GET /v1/products/{id}`.
- Search fulfillment filters are `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment booleans are `curbside`, `delivery`, `instore`, and
  `shiptohome`.
- Cart add uses `PUT /v1/cart/add` with
  `{"items": [{"upc": "...", "quantity": N, "modality": "PICKUP"}]}`.
- Cart modality is `PICKUP` or `DELIVERY`.
- Cart writes require user OAuth with `cart.basic:write`.

## Limitations

- Cart support is add/increase only; the referenced API does not document
  remove or decrement operations.
- The plugin exposes no LLM-accessible cart-write tool.
- The bundled skill requires an explicit qualified-name load.
- The proposed short Telegram `/shop` alias is deferred and not implemented.
- Raw Kroger payloads remain necessary for fields not yet modeled.
