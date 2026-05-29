---
name: kroger-shopping
description: API-first Kroger shopping agent. Uses the official Kroger Developer APIs for product search, recommendations, product detail, OAuth, and cart add operations.
version: 2.0.0
category: shopping
---

# Kroger Shopping Agent

Layered Kroger Developer API implementation for product discovery and cart adds.

This is an independent, unofficial integration and is not affiliated with, endorsed by, or sponsored by The Kroger Co., Kroger, or Simple Truth.

## Capabilities

- `/kroger search <term>` for compact product search
- `/kroger recommend <term>` for Simple Truth unwanted-ingredient ranking
- `/kroger add <UPC> [quantity]` for cart add/increase
- `/kroger login`, `/kroger code`, `/kroger status`, and `/kroger logout` for user OAuth setup
- `python -m kroger_shopping search <term>` for low-noise terminal search
- `python -m kroger_shopping recommend <term>` for low-noise terminal recommendations
- `python -m kroger_shopping add <UPC> [--quantity N] [--modality PICKUP|DELIVERY]` for low-noise cart adds
- `python -m kroger_shopping status` for low-noise auth checks
- Python client access through `KrogerClient`

## Normal Hermes Usage

For routine shopping actions, do not inspect source files or rediscover the package layout. Prefer one direct module CLI call after the user intent is clear. Use search or recommend first only when the user provides a product description instead of a UPC, then use the selected UPC with `python -m kroger_shopping add`. Inspect source and tests only when debugging or changing the skill.

When showing `python -m kroger_shopping recommend` results, preserve the CLI stdout line breaks and item formatting exactly. Do not convert recommendations into bullets, tables, prose summaries, or compact single-line items, because the CLI already formats product names, prices, sizes, unit prices, UPCs, and unwanted counts for scanning. It is fine to add one short lead-in sentence before the copied output and one short follow-up question after it.

Keep successful cart responses short: item or UPC, quantity, and modality are enough. Do not include token file paths, OAuth scope details, HTTP status internals, or implementation method names unless the operation fails and that detail helps the user fix it.

## Implementation Notes

- Keep the current layers: models, validation, parsers, recommendations, config, auth, client facade, command handlers, tests.
- Product search uses `GET /v1/products`; product detail uses `GET /v1/products/{id}`.
- Preserve `raw` payloads on major models so callers can inspect Kroger fields that are not yet typed.
- Keep request fulfillment filters (`ais`, `csp`, `dth`, `sth`) separate from item fulfillment response booleans (`curbside`, `delivery`, `instore`, `shiptohome`).
- Recommended search ranks by Simple Truth unwanted ingredient count first, existing score second, Kroger order third.
- Cart writes require user OAuth with `cart.basic:write` and send the documented `items` wrapper payload.

## Development

Use `python -m pytest` for the local unit suite. Do not run live Kroger smoke tests unless explicitly requested or needed for manual verification.
