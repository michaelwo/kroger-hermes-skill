# Kroger API Endpoints (Authoritative)

## OAuth2 Authorization Code Flow

**Correct Authorize Endpoint** (from official tutorial):
```
https://api.kroger.com/v1/connect/oauth2/authorize
```

**Correct Token Endpoint**:
```
https://api.kroger.com/v1/connect/oauth2/token
```

**Token Request (Authorization Code)**:
```bash
curl -X POST 'https://api.kroger.com/v1/connect/oauth2/token' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Authorization: Basic {{base64(CLIENT_ID:CLIENT_SECRET)}}' \
  -d 'grant_type=authorization_code&code={{CODE}}&redirect_uri={{REDIRECT_URI}}'
```

**Scopes used**:
- `product.compact`
- `cart.basic:write`
- `profile.compact`

## Cart API

**Correct Endpoint**:
```
PUT https://api.kroger.com/v1/cart/add
```

**Correct Payload** (required structure):
```json
{
  "items": [
    {"upc": "0001111060933", "quantity": 12}
  ]
}
```

Error `CART-ADD-2102` ("No items to add") occurs when the `items` wrapper is missing.

## Client Credentials (Product Search)

Works with:
```
POST https://api.kroger.com/v1/connect/oauth2/token
grant_type=client_credentials
```

Products endpoint:
```
GET https://api.kroger.com/v1/products?filter.term=...&filter.limit=...
```