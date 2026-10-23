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
| `/kroger ...` | No | Fast, deterministic search, recommendations, receipt history, buy-again lists, authentication, and cart adds |
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
- Receipt order listings and deduplicated buy-again lists
- Latest purchase dates on previously purchased recommendations
- Cart add/increase support through `PUT /v1/cart/add`
- OAuth2 authorization-code flow for cart writes, including refresh and
  token-file persistence with restrictive permissions
- Direct `/kroger` commands for Hermes TUI and messaging gateways
- Optional conversational shopping through plugin-bundled skill and tools
- Low-noise module CLI for terminal and automation use

## Installation

### Python dependencies

The runtime dependencies are listed in `requirements.txt`. Install that file
into the same Python environment that runs Hermes. When Hermes uses a dedicated
virtual environment, make sure your dependency installer targets that
environment rather than the system Python environment.

For the standard `/opt/hermes` deployment, the interpreter to target is
`/opt/hermes/.venv/bin/python`. After cloning, the dependency manifest is under
the installed plugin directory as `requirements.txt`.

Purchase history ingestion uses the Python standard library.

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
A reset does not reload Python modules: fully restart the TUI or gateway to
activate code changes. `/kroger version` reads the manifest from disk, so its
version alone does not prove the running handler has reloaded.

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
/kroger receipts
/kroger pull
/kroger buyagain
/kroger version
/kroger login
/kroger code <authorization-code>
/kroger status
/kroger logout
```

These commands dispatch directly without an agent turn or shell command.
Successful adds confirm the product title, UPC, and quantity (default: 1).
If the catalog lookup fails or returns no title, the confirmation shows
`Title unavailable` alongside the UPC and quantity.
Shopping shortcuts occupy the subcommand position and cannot be combined:

```text
/kroger -s lactose free milk
/kroger -r "lactose free milk"
/kroger -a 0001111050434 2
/kroger -h
```

`-s`, `-r`, and `-a` are aliases for `search`, `recommend`, and `add`.
`/kroger version` returns only the version from the installed `plugin.yaml`.

Bare `/kroger` and `/kroger -h` show help. Authentication commands remain
`login`, `code`, `status`, and `logout`; these shortcuts apply only to `/kroger`,
not the standalone Python CLI or structured tools.

Previously purchased recommendations include `lp: YYYY-MM-DD` using the
most recent valid receipt order date for that UPC. Missing or invalid dates omit
the purchase-date label. The structured recommendation tool also returns
`last_purchased_date` (ISO date or null). Dates do not change ranking.

`/kroger recommend` uses `sz:`, `pu:`, `unwntd:`, and `lp:` labels and returns
compact product blocks with price, UPC, size, unit price, unwanted count, purchase
date, stock status, and up to three actual unwanted-ingredient matches. The
`purchased: yes` marker is omitted. For example:

```text
Milk
$4.00 | 0001111050434 | sz: 8 oz | pu: $0.50/oz | unwntd: 0 | lp: 2026-05-31
```

These labels apply to the direct command and module CLI. Conversational replies
from `kroger_recommend` are formatted by the agent. Public recommendation
output omits internal score reasons, warnings, and aggregate scores.

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
history (`previously_purchased` and `last_purchased_date`), and explicit temporary
out-of-stock status. They do not expose
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

Place the Kroger purchase history export at `receipts/purchase-history.json`.
When the root `receipts/` directory does not exist, the loader uses
`kroger_shopping/receipts/purchase-history.json` instead. An existing root
directory takes precedence even when empty.

`/kroger pull` writes the root `receipts/purchase-history.json` (creating the
root directory even when a bundled export exists) from a Chrome tab already
signed in on Purchase History (`https://www.kroger.com/mypurchases`) with remote debugging
on `127.0.0.1:9222`. It does not type credentials, export cookies, or call the
developer API. It fetches all search pages, then receipt details in batches of
eight to obtain product titles and sizes. The command accepts no arguments.
Equivalent CLI:
`python -m kroger_shopping pull`. If DevTools is down or the tab is missing, it
prints a short error and does not write a file. Set `CDP_HOST` and `CDP_PORT`
in the Hermes process environment to override the default connection. The CDP
address must be reachable from that process; in a container, loopback refers
to the container. Pull reports the file path, order count, and number of orders
with titles. The CLI reports the path and order count.

The JSON must contain an `orders` array. Each order uses `receiptKey` as its
order number, `orderDate` as its purchase date, and `upcs` as an array of
13-digit strings. Leading zeros are preserved and duplicate UPCs are removed.
The shared cache refreshes when the file size or modification time changes.
Malformed JSON or orders produce warnings; valid orders remain usable when
individual orders are malformed. Keep personal purchase history local.

`/kroger receipts` lists order numbers and dates in export order without
credentials or API calls. Missing details appear as `Unavailable`; unreadable
history is identified by filename. Missing or empty history returns
`No local purchase history found.` This command accepts no arguments and is
available only through `/kroger`.

`/kroger buyagain` lists every distinct purchased UPC from the same local receipt
cache used by `recommend`, sorted by UPC, with names saved by `/kroger pull`.
The pull stores receipt-detail titles in each order's `productNames` mapping
alongside `upcs`. Receipt-detail names combine `description` and size when
available, and are saved only for UPCs already on that order.
When an individual detail response is missing or fails, pull can retain titles
from the previous root export if the new search row has no names. A detail that
returns and shares no UPC with the list row stays untitled. Each UPC appears
once, even when purchased on multiple orders; the latest ISO-dated order with
a name takes precedence. Buy-again makes no catalog requests
and requires no API credentials. Missing names show `Name unavailable` with a
reminder to run `/kroger pull`; older exports containing only UPCs still work.
The command accepts no arguments and lists all products. Use
`/kroger add <UPC> [quantity]` to add an item to your cart. If no UPCs are recognized,
it returns `No purchased UPCs found in local receipts.`

The full list is returned in one response; large histories can exceed a messaging
gateway's response limits. Pagination is not implemented.

Example with a single purchased product:

```text
Previously purchased products: 1
- Simple Truth Organic® Lactose Free Vitamin D Whole Milk Half Gallon | UPC: `0001111050434`
```

Purchase dates come from each order's `orderDate`, using the latest valid date
across orders containing each UPC. Supported formats are `YYYY-MM-DD` and
`Month D, YYYY`. Export timestamps, receipt keys, and file modification times
are not purchase dates. Recommendation metadata can include:

```text
lp: 2026-05-31
```

Only `TEMPORARILY_OUT_OF_STOCK` is rendered as `out of stock`. `HIGH`, `LOW`,
missing, and unavailable inventory states remain unmarked and do not affect
ranking.

## Module CLI

```text
python -m kroger_shopping search <term> [--limit N]
python -m kroger_shopping recommend <term> [--limit N]
python -m kroger_shopping add <UPC> [--quantity N] [--modality PICKUP|DELIVERY]
python -m kroger_shopping status
python -m kroger_shopping pull
```

The module CLI is deterministic. It does not include the interactive
authorization-code commands; use `/kroger login` and `/kroger code` for that
workflow. The receipt inspection commands `receipts` and `buyagain` are also
exclusive to `/kroger`. Module CLI recommendations include the same
`lp: YYYY-MM-DD` metadata when a purchase date is known.

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

Each `RankedProduct` also exposes `previously_purchased` and
`last_purchased_date` (an ISO date string or `None`). The shared receipt interfaces
are `load_receipt_history()`, `load_purchase_upcs()`, `load_purchase_names()`,
and `load_last_purchase_dates()` in `kroger_shopping.receipts`.

## Architecture

- `kroger_shopping/models.py` — domain models, enums, scoring metadata, and
  Simple Truth rules
- `kroger_shopping/validation.py` — validators and API limit constants
- `kroger_shopping/parsers.py` — Kroger response-to-model mapping
- `kroger_shopping/recommendations.py` — ingredient matching and ranking
- `kroger_shopping/unit_pricing.py` — size parsing and comparable unit prices
- `kroger_shopping/receipts.py` — local JSON order metadata, UPC ingestion, latest purchase dates, and caching
- `kroger_shopping/purchase_history.py` — CDP history export and receipt-detail titles
- `kroger_shopping/auth.py` — OAuth requests, refresh, and token persistence
- `kroger_shopping/client.py` — public API facade, HTTP handling, and auth retry
- `kroger_shopping/hermes_command.py` — current direct `/kroger` presentation
- `kroger_shopping/hermes_tools.py` — structured read-only agent tools
- `skills/shopping-assistant/SKILL.md` — plugin-bundled conversational workflow
- root `plugin.yaml` and `__init__.py` — Hermes manifest and registration
- `commands/kroger.py` — legacy Hermes command compatibility adapter
- `tests/test_basic.py` — unit, output, and OpenAPI contract tests
- `tests/test_hermes_plugin.py` — plugin registration, command adapters, and tool contract tests
- `tests/test_receipt_history.py` — receipt metadata, caching, and latest purchase date tests
- `tests/test_purchase_history.py` — CDP pulls, title matching, and title preservation
- `references/openapi/*.openapi.json` — committed Kroger OpenAPI references
- `docs/plans/` — deferred, explicitly unimplemented design plans

## Development and Verification

Run the offline unit suite from the repository root:

```bash
python -m pytest tests
```

GitHub Actions runs that same command on Python 3.12 and 3.13 for pushes to
`main` and for pull requests. `tests/pytest.ini` puts the repo on `pythonpath`
so pytest does not import the Hermes plugin `__init__.py` as a test package.
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
