# Kroger Products + Cart API Notes

These notes summarize behavior used by the client. The committed OpenAPI files in `references/openapi/` are the contract source for endpoint and schema checks.

## Products API

- Product search: `GET /v1/products`.
- Product detail: `GET /v1/products/{id}`.
- `filter.locationId` is required for price, fulfillment, aisle, and inventory fields.
- Search fulfillment filter values are `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment response fields are booleans: `curbside`, `delivery`, `instore`, `shiptohome`.
- Inventory stock levels are `HIGH`, `LOW`, and `TEMPORARILY_OUT_OF_STOCK`.
- Product detail may include typed nutrition, allergen, SNAP, warning, restriction, image, aisle, and item fields; raw payloads are preserved.

## Recommendations

- Recommended search fetches product details for candidates so it can inspect ingredient statements.
- Ranking uses the Simple Truth unwanted food ingredient list as a committed rule snapshot.
- Products with fewer matched unwanted ingredients rank higher.
- Missing ingredient data is represented as unknown, not clean.

## Cart API

- Cart add/increase endpoint: `PUT /v1/cart/add`.
- Payload shape: `{"items": [{"upc": "...", "quantity": N, "modality": "PICKUP"}]}`.
- `quantity` must be a positive integer.
- `upc` must be a 13-digit string.
- `modality` is `PICKUP` or `DELIVERY`; default is `PICKUP`.
- Cart writes require authorization-code user tokens with `cart.basic:write`.
- The referenced API does not document remove or decrement operations.

## Rate Limits

- Products API: 10,000 calls/day.
- Cart API: 5,000 calls/day.
