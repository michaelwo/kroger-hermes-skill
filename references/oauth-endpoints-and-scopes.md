# Kroger OAuth2 Notes

## Endpoints

- Authorization: `https://api.kroger.com/v1/connect/oauth2/authorize`
- Token: `https://api.kroger.com/v1/connect/oauth2/token`

The `/oauth2/` segment is required. Shorter `/connect/authorize` and `/connect/token` paths return 404.

## Scopes

- `product.compact` for product search and detail reads
- `cart.basic:write` for cart add/increase
- `profile.compact` for profile access when available

## Flows

- Use client credentials for product and location reads.
- Use authorization code for cart writes.
- Use refresh tokens when available instead of asking the user to re-authorize.
- Store user tokens in `~/.kroger_tokens.json` or `KROGER_TOKEN_FILE` with `0600` permissions.

## Container Workflow

Containerized agents should use the manual code-paste flow:

1. Run `/kroger login`.
2. Open the returned Kroger authorization URL.
3. Sign in and approve scopes.
4. Copy the `code` query parameter from the redirect URL.
5. Run `/kroger code <authorization-code>`.

## Common Pitfalls

- Missing `/oauth2/` in endpoint paths
- Reusing expired or single-use authorization codes
- Missing `cart.basic:write` for cart operations
- Saving truncated tokens
- Committing `.env` files or token files
