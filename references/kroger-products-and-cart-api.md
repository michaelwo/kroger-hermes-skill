# Kroger Products, Recommendations, and Cart API Notes

These notes summarize behavior used by the client. The committed OpenAPI files
in `references/openapi/` are the contract source for endpoint and schema checks.

## Products API

- Product search: `GET /v1/products`
- Product detail: `GET /v1/products/{id}`
- `filter.locationId` is required for price, fulfillment, aisle, and inventory
  fields.
- Search fulfillment values are `ais`, `csp`, `dth`, and `sth`.
- Item fulfillment fields are booleans: `curbside`, `delivery`, `instore`, and
  `shiptohome`.
- Inventory levels are `HIGH`, `LOW`, and `TEMPORARILY_OUT_OF_STOCK`.
- Product detail may include typed nutrition, allergen, SNAP, warning,
  restriction, image, aisle, and item fields; raw payloads are preserved.

## Recommendations

- Recommended search requests up to 25 candidates by default and fetches
  product details for ingredient inspection.
- One product-detail failure does not abort other candidates; programmatic
  results retain a warning for the failed detail.
- Receipt purchase history is read from exact 13-digit `UPC:` lines in
  repository-level `receipts/*.pdf`.
- Previously purchased UPCs sort before unpurchased UPCs.
- Known ingredient data sorts before unknown data; fewer matched unwanted
  ingredients sort first.
- Known unit prices sort before unknown unit prices; lower comparable unit
  prices sort first.
- The existing preference score and original Kroger order are later
  tie-breakers.
- Missing ingredient data is unknown, not zero unwanted ingredients.
- Ingredient matching uses a committed Simple Truth rule snapshot and
  explainable aliases. It is not medical advice or toxicity scoring.
- Only explicit `TEMPORARILY_OUT_OF_STOCK` inventory is labeled out of stock;
  stock status does not currently alter ranking.
- Public slash-command and structured-tool output omits internal score reasons,
  warnings, and totals.

## Cart API

- Add/increase endpoint: `PUT /v1/cart/add`
- Payload:

  ```json
  {
    "items": [
      {"upc": "...", "quantity": 1, "modality": "PICKUP"}
    ]
  }
  ```

- `quantity` must be a positive integer.
- `upc` must be a 13-digit string.
- `modality` is `PICKUP` or `DELIVERY`; default is `PICKUP`.
- Cart writes require authorization-code user tokens with `cart.basic:write`.
- The referenced API does not document remove or decrement operations.
- The Hermes conversational skill does not receive a cart-write tool; it hands
  selected UPCs to deterministic `/kroger add`.

## Rate Limits

- Products API: 10,000 calls/day
- Cart API: 5,000 calls/day
