# Kroger Shopping Skill

Professional Hermes skill for interacting with the Kroger Developer APIs.

## Features

- Product search with rich filtering
- Add items to cart
- Automatic OAuth2 token management with refresh
- Input validation and typed error handling
- Slash command support (`/kroger`)

## Installation

The skill is located at:

```
/opt/data/skills/shopping/kroger-shopping/
```

## Configuration

Set the following environment variables:

```bash
export KROGER_CLIENT_ID=your_client_id
export KROGER_CLIENT_SECRET=your_client_secret
export KROGER_DEFAULT_LOCATION_ID=01400943   # optional
export KROGER_DEFAULT_FULFILLMENT=csp        # optional
```

## Usage

### Slash Commands

```
/kroger search <term>
/kroger add <UPC> [quantity]
/kroger login
```

### Python Usage

```python
from kroger_shopping import KrogerClient

client = KrogerClient()
results = client.search_products("milk", limit=5, location_id="01400943")
client.add_to_cart("0001111050434", quantity=2)
```

## Architecture

- Layered design (Auth → Client → Commands)
- Clean domain models
- Proper exception handling
- Rate limit awareness

## Limitations

- Cart API is currently add-only
- Daily rate limits apply (10k Products / 5k Cart)

## Version

2.0.0 — Professional refactor with layered architecture.