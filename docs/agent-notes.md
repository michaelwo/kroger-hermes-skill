# Contributor notes for coding agents

Guidance for coding agents working in this repository.

## Project Shape

- `kroger_shopping/models.py` contains public domain models, enums,
  recommendation score metadata, and Simple Truth unwanted ingredient rules.
- `kroger_shopping/validation.py` owns validators and API limit constants.
- `kroger_shopping/parsers.py` owns Kroger response-to-model mapping.
- `kroger_shopping/recommendations.py` owns ingredient extraction, Simple Truth
  matching, and recommendation ordering.
- `kroger_shopping/unit_pricing.py` owns size parsing and comparable unit-price
  calculations.
- `kroger_shopping/receipts.py` owns local JSON order metadata, UPC ingestion,
  latest purchase dates, and caching.
- `kroger_shopping/auth.py` owns OAuth requests, token refresh, and token file
  persistence.
- `kroger_shopping/client.py` owns the public API facade, request handling, and
  auth retry behavior.
- `kroger_shopping/hermes_command.py` owns current direct `/kroger`
  presentation.
- `kroger_shopping/hermes_tools.py` owns structured, read-only Hermes agent
  tools.
- `skills/shopping-assistant/SKILL.md` owns the plugin-bundled conversational
  workflow.
- Root `plugin.yaml` and `__init__.py` own Hermes plugin declaration and
  registration.
- `commands/kroger.py` is a compatibility adapter for legacy Hermes versions.
- `tests/test_basic.py` is the main unit, output, and contract test suite.
- `tests/test_hermes_plugin.py` covers plugin registration and structured tool
  contracts.
- `tests/test_receipt_history.py` covers receipt metadata, cache refresh, and
  latest purchase dates.
- `references/openapi/*.openapi.json` are committed Kroger OpenAPI references
  used by contract tests.
- `docs/plans/` contains deferred proposals, not current behavior.

## Working Rules

- Inspect existing code and tests before editing.
- Preserve user changes in the working tree; do not revert unrelated files.
- Do not commit `.env`, token files, credentials, purchase history exports, or live API
  output containing secrets or personal data.
- Preserve the Kroger/Simple Truth non-affiliation disclaimer in public-facing
  docs.
- Prefer focused changes that follow the existing layered architecture.
- Keep raw Kroger payloads available on major models when adding typed fields.
- Keep docs, tests, direct command output, and structured tool output aligned
  when public behavior changes.
- Keep deferred plans explicitly labeled and do not describe them as shipped.

## Hermes Integration Invariants

- `/kroger` is a plugin-registered direct command and must not invoke an LLM,
  shell command, or Hermes tool.
- The bundled skill is registered as
  `kroger-shopping:shopping-assistant`; plugin skills are explicit,
  namespaced loads rather than standalone slash commands.
- `kroger_search`, `kroger_recommend`, and `kroger_auth_status` are read-only
  LLM tools.
- Do not expose cart writes as an LLM tool. The skill hands selected UPCs to
  `/kroger add <UPC> [quantity]`.
- Internal recommendation score totals, reasons, and warnings remain available
  to programmatic callers but are omitted from public command and tool output.
- No built-in tool-override permission is required.

## Kroger API Invariants

- Product search uses `GET /v1/products`.
- Product detail uses `GET /v1/products/{id}`.
- Search fulfillment filters are `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment response booleans are `curbside`, `delivery`, `instore`, and
  `shiptohome`.
- Cart add uses `PUT /v1/cart/add` with
  `{"items": [{"upc": ..., "quantity": ..., "modality": ...}]}`.
- Cart modality values are `PICKUP` and `DELIVERY`.
- Cart writes require user OAuth with `cart.basic:write`.

## Recommendation Invariants

Recommended ordering is:

1. Previously purchased UPCs first.
2. Known ingredient data before unknown data, then lower unwanted ingredient
   count.
3. Known unit prices before unknown unit prices, then lower unit price.
4. Higher existing preference score.
5. Original Kroger result order.

Additional constraints:

- Ingredient data that is missing is `unknown`, not zero unwanted ingredients.
- Ingredient matching is explainable keyword/alias matching, not medical advice
  or toxicity scoring.
- Only explicit `TEMPORARILY_OUT_OF_STOCK` inventory is presented as out of
  stock; availability does not currently change ranking.
- Receipt purchase history comes from exact 13-digit strings in each order’s `upcs` array in
  repository-level `receipts/purchase-history.json`, falling back to
  `kroger_shopping/receipts/purchase-history.json` only when the root directory does not exist.
- `load_purchase_upcs()` remains the source of purchase membership for
  recommendations and `/kroger buyagain`. Preserve deduplication and metadata
  cache invalidation across receipt consumers.
- Latest purchase dates use the maximum valid `orderDate` across receipts for
  each UPC, accepting `Month D, YYYY` and ISO dates. Do not infer dates from
  filenames or filesystem timestamps. Recency does not affect ranking.
- `RankedProduct.last_purchased_date` and the structured recommendation payload
  use an ISO date or None/null. Direct and CLI output adds
  `last bought: YYYY-MM-DD` when known; missing dates retain `purchased: yes`.
- `/kroger receipts` lists order numbers and dates without constructing a client.
  `/kroger buyagain` lists every distinct UPC with a catalog name, retaining UPCs
  when configuration or individual lookups fail. Neither modifies the cart.
  Both reject extra arguments and are unavailable as module CLI or agent tools.

## Verification

- Run `python -m pytest` for the full unit suite.
- Unit tests should not require live Kroger credentials.
- Validate the bundled skill when it changes.
- Run live Kroger smoke tests only when explicitly requested or when manual API
  verification is necessary.
