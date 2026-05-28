# AGENTS.md

Guidance for coding agents working in this repository.

## Project Shape

- `kroger_shopping/models.py` contains public domain models, enums, recommendation score metadata, and Simple Truth unwanted ingredient rules.
- `kroger_shopping/validation.py` owns validators and API limit constants.
- `kroger_shopping/parsers.py` owns Kroger response-to-model mapping.
- `kroger_shopping/recommendations.py` owns ingredient extraction, Simple Truth matching, and ranking helpers.
- `kroger_shopping/auth.py` owns OAuth requests, token refresh, and token file persistence.
- `kroger_shopping/client.py` owns the public API facade, request handling, and auth retry behavior.
- `commands/kroger.py` owns Hermes slash-command presentation.
- `tests/test_basic.py` is the main unit and contract test suite.
- `references/openapi/*.openapi.json` are committed Kroger OpenAPI references used by contract tests.

## Working Rules

- Inspect existing code and tests before editing.
- Preserve user changes in the working tree; do not revert unrelated files.
- Do not commit `.env`, token files, credentials, or live API output containing secrets.
- Preserve the Kroger/Simple Truth non-affiliation disclaimer in public-facing docs.
- Prefer focused changes that follow the existing layered architecture.
- Keep raw Kroger payloads available on major models when adding typed fields.
- Keep docs, tests, and command output aligned when public behavior changes.

## Kroger API Invariants

- Product search uses `GET /v1/products`.
- Product detail uses `GET /v1/products/{id}`.
- Search fulfillment filters are `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment response booleans are `curbside`, `delivery`, `instore`, and `shiptohome`.
- Cart add uses `PUT /v1/cart/add` with `{"items": [{"upc": ..., "quantity": ..., "modality": ...}]}`.
- Cart modality values are `PICKUP` and `DELIVERY`.
- Cart writes require user OAuth with `cart.basic:write`.

## Recommendation Invariants

- Recommended search ranks by Simple Truth unwanted ingredient count first.
- Existing preference score is a tie-breaker after unwanted count.
- Original Kroger result order is the final tie-breaker.
- Ingredient data that is missing is `unknown`, not zero unwanted ingredients.
- Ingredient matching is explainable keyword/alias matching, not medical advice or toxicity scoring.

## Verification

- Run `python -m pytest` for the unit suite.
- Unit tests should not require live Kroger credentials.
- Run live Kroger smoke tests only when explicitly requested or when manual API verification is necessary.
