# Kroger API Endpoints

Use this as a quick endpoint map. The committed OpenAPI documents in `references/openapi/` are the source of truth for schemas and validator contract tests.

## OAuth2

- Authorize: `GET https://api.kroger.com/v1/connect/oauth2/authorize`
- Token: `POST https://api.kroger.com/v1/connect/oauth2/token`

The `/oauth2/` path segment is required.

## Products

- Search: `GET https://api.kroger.com/v1/products`
- Detail: `GET https://api.kroger.com/v1/products/{id}`

Common search filters:

- `filter.term`
- `filter.brand`
- `filter.productId`
- `filter.locationId`
- `filter.fulfillment`
- `filter.limit`

## Cart

- Add/increase: `PUT https://api.kroger.com/v1/cart/add`

Required payload wrapper:

```json
{
  "items": [
    {"upc": "0001111060933", "quantity": 1, "modality": "PICKUP"}
  ]
}
```

## Locations

- List: `GET https://api.kroger.com/v1/locations`
- Detail: `GET https://api.kroger.com/v1/locations/{locationId}`
- Exists: `HEAD https://api.kroger.com/v1/locations/{locationId}`

## Chains and Departments

- Chains: `GET /v1/chains`, `GET /v1/chains/{name}`, `HEAD /v1/chains/{name}`
- Departments: `GET /v1/departments`, `GET /v1/departments/{departmentId}`, `HEAD /v1/departments/{departmentId}`
