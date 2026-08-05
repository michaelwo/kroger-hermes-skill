---
name: kroger-shopping
description: API-first Kroger shopping integration for deterministic Hermes commands, conversational read-only product discovery, OAuth, and cart adds.
version: 2.2.0
category: shopping
---

# Kroger Shopping Integration

Layered Kroger Developer API implementation for product discovery and cart
adds.

This is an independent, unofficial integration and is not affiliated with,
endorsed by, or sponsored by The Kroger Co., Kroger, or Simple Truth.

## Current Interfaces

- `/kroger search <term>` — compact direct search
- `/kroger recommend <term>` — compact receipt-aware recommendations
- `/kroger add <UPC> [quantity]` — deterministic cart add/increase
- `/kroger login`, `/kroger code`, `/kroger status`, `/kroger logout` — user
  OAuth
- `kroger-shopping:shopping-assistant` — explicitly loaded conversational skill
- `kroger_search`, `kroger_recommend`, `kroger_auth_status` — read-only agent
  tools
- `python -m kroger_shopping ...` — deterministic module CLI
- `KrogerClient` — Python API

There is no `/kroger-shopping` slash command and no LLM-accessible cart-write
tool. A shorter `/shop` Telegram alias is only a deferred proposal in
`docs/plans/telegram-shopping-skill-alias.md`.

## Normal Hermes Usage

Prefer `/kroger` for routine messaging and TUI actions. It dispatches directly,
without an LLM, shell command, or Hermes tool.

For LLM-guided comparison, explicitly load
`kroger-shopping:shopping-assistant`. Plugin-provided skills are namespaced and
do not appear in the normal skill index. The bundled skill uses structured
read-only tools and leaves cart writes to `/kroger add`.

When the plugin is unavailable, use one direct `python -m kroger_shopping`
operation after the user intent is clear. Search or recommend first when the
user provides a product description rather than a UPC.

Preserve module CLI recommendation blocks as emitted. Keep successful cart
responses concise. Do not expose token paths, OAuth internals, HTTP details,
score totals, internal score reasons, or warnings unless failure diagnostics
require them.

## Recommendation Rules

Rank in this order:

1. Previously purchased UPCs
2. Known/fewer unwanted ingredient matches
3. Known/lower unit price
4. Higher preference score
5. Original Kroger result order

Missing ingredient data is unknown, not zero. Ingredient matching is
explainable preference-rule matching, not medical advice or toxicity scoring.
Only explicit `TEMPORARILY_OUT_OF_STOCK` inventory is labeled out of stock.

Receipt history is loaded from repository-level `receipts/*.pdf`.

## Implementation Notes

- Preserve the current layers: models, validation, parsers, recommendations,
  unit pricing, receipts, config, auth, client, Hermes presentation, and tests.
- Root `plugin.yaml` and `__init__.py` register `/kroger`, three read-only tools,
  and `kroger-shopping:shopping-assistant`.
- `kroger_shopping/hermes_command.py` is the current direct command handler;
  `commands/kroger.py` is legacy compatibility only.
- Product search uses `GET /v1/products`; product detail uses
  `GET /v1/products/{id}`.
- Preserve raw payloads on major models.
- Keep request fulfillment filters (`ais`, `csp`, `dth`, `sth`) separate from
  response booleans (`curbside`, `delivery`, `instore`, `shiptohome`).
- Cart writes require user OAuth with `cart.basic:write` and the documented
  `items` wrapper.

## Development

Run `python -m pytest`. Tests must remain offline by default. Run live Kroger
smoke tests only when explicitly requested or necessary for manual verification.
