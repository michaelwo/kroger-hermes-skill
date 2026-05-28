# Kroger Products + Cart API Notes (from official specs)

## Products API (`/v1/products`)
- Primary search via `filter.term` (fuzzy) or `filter.productId`.
- `filter.locationId` is required to return price, fulfillment types, aisle location, and inventory.
- `filter.fulfillment` values: `ais`, `csp`, `dth`, `sth`.
- Rich response includes `items[].price`, `fulfillment`, `inventory.stockLevel`, `aisleLocations`, images, nutrition.
- Rate limit: 10,000 calls/day.

## Cart API (`PUT /v1/cart/add`)
- **Only supported operation**: Add/increase quantity.
- Payload must be `{"items": [{"upc": "...", "quantity": N, "modality": "PICKUP"}]}`.
- `quantity` must be ≥ 1 (negative values and 0 are rejected with `CART-2012`).
- No documented remove or decrement operation in v1.2.3.
- Requires Authorization Code grant + `cart.basic:write` scope.
- Rate limit: 5,000 calls/day.

## Key Limitations Discovered
- Cart API is strictly additive. There is no remove endpoint.
- To "reduce" quantity, the only option is to re-add the item with the desired final quantity.
- OAuth endpoints must include `/oauth2/` segment: `/v1/connect/oauth2/authorize` and `/v1/connect/oauth2/token`.