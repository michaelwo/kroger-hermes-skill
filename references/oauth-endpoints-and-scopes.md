# Kroger OAuth2 Notes

## Endpoints

- Authorization: `https://api.kroger.com/v1/connect/oauth2/authorize`
- Token: `https://api.kroger.com/v1/connect/oauth2/token`

The `/oauth2/` segment is required. Shorter `/connect/authorize` and
`/connect/token` paths return 404.

## Scopes

- `product.compact` for product search and detail reads
- `cart.basic:write` for cart add/increase
- `profile.compact` for profile access when available

## Flows

- Use client credentials for product and location reads.
- Use authorization code for cart writes.
- Use refresh tokens when available instead of asking the user to re-authorize.
- Store user tokens at `KROGER_TOKEN_FILE` or the default
  `~/.kroger_tokens.json` with `0600` permissions.

## Configuration

- `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` are required.
- `KROGER_REDIRECT_URI` defaults to `http://localhost:8080/callback`.
- `KROGER_TOKEN_FILE` defaults to `~/.kroger_tokens.json`.

The environment belongs to the Python process running Hermes. In containerized
deployments, setting variables only in an interactive shell does not update the
gateway service environment.

## Container and Gateway Workflow

Use the manual code-paste flow:

1. Run `/kroger login`.
2. Open the returned Kroger authorization URL.
3. Sign in and approve scopes.
4. Copy the `code` query parameter from the redirect URL.
5. Run `/kroger code <authorization-code>`.
6. Confirm with `/kroger status`.

The module CLI provides `status` but does not provide `login`, `code`, or
`logout`; those are direct `/kroger` commands.

## Common Pitfalls

- Missing `/oauth2/` in endpoint paths
- A redirect URI that differs from the Kroger application registration
- Reusing expired or single-use authorization codes
- Missing `cart.basic:write` for cart operations
- Saving truncated tokens
- Installing dependencies into a different Python environment than Hermes
- Committing `.env`, token files, receipt PDFs, or live output containing
  credentials
