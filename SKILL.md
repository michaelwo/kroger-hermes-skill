---
name: kroger-shopping
description: API-first Kroger shopping agent. Uses the official Kroger Developer APIs (Products + Cart) to resolve items and add them to a user's cart.
version: 2.0.0
category: shopping
---

# Kroger Shopping Agent (API)

**Professional, layered implementation** of the Kroger Developer APIs.

## Architecture

- `kroger_shopping/exceptions.py` — Custom exception hierarchy
- `kroger_shopping/models.py` — Domain models (`Product`, `CartItem`, `TokenSet`)
- `kroger_shopping/config.py` — Environment-based configuration
- `kroger_shopping/auth.py` — `KrogerAuthClient` (OAuth2 + token management)
- `kroger_shopping/client.py` — `KrogerClient` (high-level API usage)
- `commands/kroger.py` — Slash command handlers

## Features

- Automatic token refresh
- Strong input validation
- Typed error handling with retries
- Clean separation of concerns
- Slash command support (`/kroger search`, `/kroger add`, etc.)

## Status

**Status**: Mature and hardened. Ready for real use. Version 2.0.0 represents the professional refactor.

## Code Structure Preference

When extending this skill, use a layered architecture with clear separation between:
- Exceptions
- Domain models
- Configuration
- Authentication layer (`KrogerAuthClient`)
- API client layer (`KrogerClient`)
- Command handlers

Avoid long imperative functions. This structure was explicitly selected over simpler refactors.