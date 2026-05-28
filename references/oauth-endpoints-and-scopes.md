# Kroger OAuth2 Endpoint Reference

## Correct Endpoints (verified May 2026)

- **Authorization**: `https://api.kroger.com/v1/connect/oauth2/authorize`
- **Token**: `https://api.kroger.com/v1/connect/oauth2/token`

**Important**: The `/oauth2/` segment in the path is required. Using `/v1/connect/authorize` or `/v1/connect/token` returns 404.

## Working Scopes (for MW-H-Shopper app)

- `product.compact`
- `cart.basic:write`
- `profile.compact`

## Recommended Flow for Containerized Agents

1. Use `client_credentials` for product search and read operations.
2. Use Authorization Code grant only when cart write access is needed.
3. For container environments, implement manual code paste flow instead of local callback server.
4. Always store tokens in `~/.kroger_tokens.json` with 0600 permissions.
5. Implement token refresh using the `refresh_token` when available.

## Common Pitfalls Encountered

- Wrong authorize path (`/connect/authorize` vs `/connect/oauth2/authorize`)
- Using expired single-use authorization codes
- Truncated tokens saved to file
- Missing `jq` or `requests` in minimal container environments

## Token Response Shape

Authorization Code and Refresh responses return:
- `access_token`
- `refresh_token` (only on Authorization Code)
- `expires_in` (usually 1800)
- `token_type`: "bearer"