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
- Python client access through `KrogerClient`

## Implementation Notes

- Keep the current layers: models, validation, parsers, recommendations, config, auth, client facade, command handlers, tests.
- Product search uses `GET /v1/products`; product detail uses `GET /v1/products/{id}`.
- Preserve `raw` payloads on major models so callers can inspect Kroger fields that are not yet typed.
- Keep request fulfillment filters (`ais`, `csp`, `dth`, `sth`) separate from item fulfillment response booleans (`curbside`, `delivery`, `instore`, `shiptohome`).
- Recommended search ranks by Simple Truth unwanted ingredient count first, existing score second, Kroger order third.
- Cart writes require user OAuth with `cart.basic:write` and send the documented `items` wrapper payload.

## Development

Use `python -m pytest` for the local unit suite. Do not run live Kroger smoke tests unless explicitly requested or needed for manual verification.
