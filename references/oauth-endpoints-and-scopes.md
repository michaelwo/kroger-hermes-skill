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
  `$HERMES_HOME/.kroger_tokens.json` (else `~/.kroger_tokens.json`) with `0600`
  permissions.
- `/kroger login` persists the OAuth `state` beside the token file
  (`<token-file>.login-state`, `0600`, 15-minute lifetime); `/kroger code`
  verifies it when the pasted redirect includes `state`.

## Configuration

- `KROGER_CLIENT_ID` and `KROGER_CLIENT_SECRET` are required for developer API
  operations. Local `receipts`, `buyagain`, and `version` commands need no
  credentials. Pull uses a signed-in CDP browser instead of developer OAuth.
- `KROGER_REDIRECT_URI` defaults to `http://localhost:8080/callback`.
- `KROGER_TOKEN_FILE` defaults to `$HERMES_HOME/.kroger_tokens.json`, or
  `~/.kroger_tokens.json` when `HERMES_HOME` is unset.

The environment belongs to the Python process running Hermes. In containerized
deployments, setting variables only in an interactive shell does not update the
gateway service environment.

## Container and Gateway Workflow

Use the manual code-paste flow:

1. Run `/kroger login`.
2. Open the returned Kroger authorization URL.
3. Sign in and approve scopes.
4. Copy the full redirect URL from the browser address bar.
5. Run `/kroger code <redirect-url>` (a bare `code` value also works).
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
- Committing `.env`, token files, purchase-history exports, or live output containing
  credentials
