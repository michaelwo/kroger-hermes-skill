# Telegram Alias for the Kroger Shopping Skill

Status: Deferred  
Target release: Unscheduled

## Goal

Provide a short Telegram entry point for the plugin-bundled
`kroger-shopping:shopping-assistant` skill:

```text
/shop lactose-free milk
```

The alias should begin a normal Hermes agent turn, explicitly load the bundled
skill, and preserve the existing structured Kroger tools. It must not change
the behavior of the direct, zero-LLM `/kroger` command.

## Background

Hermes plugin-provided skills are namespaced and opt-in. The current skill must
be loaded with `skill_view("kroger-shopping:shopping-assistant")`, normally by
asking Hermes to do so in a natural-language message. That is correct but
unnecessarily verbose in Telegram.

A normal plugin slash command is not sufficient for this workflow:

- `ctx.register_command()` dispatches directly to a command handler.
- Direct dispatch is desirable for `/kroger`, but it bypasses the conversational
  agent loop needed by the shopping-assistant skill.
- `ctx.inject_message()` is not available for starting agent turns in gateway
  mode.

Hermes's `pre_gateway_dispatch` plugin hook can instead rewrite a short incoming
message before normal gateway dispatch continues.

## Proposed User Experience

Support the following Telegram inputs:

```text
/shop lactose-free milk
/shop compare inexpensive olive oils
/shop find cereal without unwanted ingredient matches
```

Rewrite them internally to a prompt equivalent to:

```text
Load kroger-shopping:shopping-assistant using skill_view.
User request: lactose-free milk
```

For a bare alias:

```text
/shop
```

rewrite to a prompt asking Hermes to load the skill and ask the user what they
want to shop for.

The alias may not appear in Telegram's command suggestion menu because it is a
gateway rewrite rather than a conventional registered command. Typed
`/shop ...` usage is the initial scope. Menu exposure should be investigated
separately and must not compromise normal agent dispatch.

## Design

### Gateway rewrite hook

Add a small callback owned by the Hermes presentation layer, not by the Kroger
API client:

```python
def rewrite_shopping_alias(event, **kwargs):
    ...
```

Register it from the plugin entry point:

```python
ctx.register_hook("pre_gateway_dispatch", rewrite_shopping_alias)
```

The callback should:

1. Read `event.text` defensively.
2. Restrict rewriting to Telegram unless cross-gateway support is intentionally
   chosen later.
3. Recognize `/shop` as a complete command token, case-insensitively.
4. Recognize Telegram's group-chat form `/shop@bot_username`.
5. Preserve all text following the command as the user's request.
6. Return `{"action": "rewrite", "text": expanded_prompt}` for matches.
7. Return `None` for all unrelated messages.

Keep the expanded prompt constant in code and include the fully qualified skill
name. Do not interpolate the request into instructions that could blur the
boundary between the fixed directive and user text; label it explicitly as the
user request.

### Layering

Place the hook implementation in a Hermes-specific module, for example:

```text
kroger_shopping/hermes_gateway.py
```

Keep these responsibilities unchanged:

- `kroger_shopping/client.py`: Kroger API facade
- `kroger_shopping/hermes_tools.py`: structured read-only LLM tools
- `kroger_shopping/hermes_command.py`: direct `/kroger` handler
- root `__init__.py`: plugin registration only

The hook must not call Kroger APIs, load the skill itself, or execute an LLM.
It only rewrites the gateway message and lets Hermes perform normal dispatch.

## Safety and Behavioral Constraints

- Do not alter `/kroger` or its zero-LLM behavior.
- Do not add an LLM-accessible cart-write tool.
- Continue handing cart changes back to `/kroger add <UPC> [quantity]`.
- Do not rewrite ordinary prose containing `/shop` in the middle of a message.
- Do not rewrite similar commands such as `/shopping`, `/shopper`, or
  `/kroger`.
- Preserve the user's request verbatim after separating it from the command
  token.
- Avoid logging message contents because shopping prompts may contain personal
  preference information.
- Return `None` on malformed or unsupported events so gateway handling remains
  fail-open.

## Test Plan

Add unit tests covering:

- `/shop milk` rewrites to the qualified skill-loading prompt.
- `/SHOP milk` is accepted.
- `/shop@expected_bot milk` is accepted in Telegram group syntax.
- A bare `/shop` produces the shopping-assistant onboarding prompt.
- Leading and repeated whitespace are handled predictably.
- Multiline user requests are preserved.
- `/shopping milk`, `/shopper milk`, and embedded `/shop` text are untouched.
- Messages from non-Telegram platforms are untouched if the initial
  implementation is Telegram-only.
- Missing `event.text`, `None`, and non-string values do not raise.
- Plugin registration includes exactly one `pre_gateway_dispatch` hook.
- Existing command, tool, and skill registration tests continue to pass.

Run:

```bash
python -m pytest
```

No live Kroger credentials or API calls should be required.

## Manual Verification

After updating and restarting Hermes:

1. Confirm the plugin loads without warnings.
2. Start a fresh Telegram session with `/reset`.
3. Send `/shop lactose-free milk`.
4. Confirm Hermes enters a normal agent turn.
5. Confirm the agent loads `kroger-shopping:shopping-assistant`.
6. Confirm it invokes `kroger_recommend` or `kroger_search`.
7. Confirm the response uses conversational formatting and omits internal
   ranking reasons.
8. Confirm `/kroger recommend lactose-free milk` remains direct and terse.
9. Confirm an unrelated unknown slash command retains Hermes's normal
   unknown-command behavior.
10. Test `/shop@bot_username milk` in a group if group usage is enabled.

Useful diagnostics:

```bash
hermes plugins list
hermes logs --level WARNING | grep -i -E 'kroger|plugin|gateway'
```

## Rollout

1. Implement the hook and unit tests.
2. Update `plugin.yaml` to declare the provided hook if the active Hermes
   manifest schema expects `provides_hooks`.
3. Update the README with `/shop` examples and the Telegram-menu limitation.
4. Bump the plugin minor version.
5. Run the complete unit suite.
6. Deploy with `hermes plugins update kroger-shopping`.
7. Restart the gateway and use a fresh Telegram session.

No built-in tool-override permission should be required.

## Open Questions

- Should `/shop` work only on Telegram, or on every Hermes gateway?
- Is `/ks` preferable, or should both aliases be supported?
- Can Telegram command-menu metadata be registered independently from command
  dispatch in the installed Hermes version?
- Should a bare `/shop` ask a question, or immediately recommend common/recent
  products?
- Should the alias be configurable in `plugin.yaml` or remain a stable plugin
  convention?

## Acceptance Criteria

- `/shop <request>` starts an LLM-driven shopping-assistant turn in Telegram.
- The bundled skill is loaded by its qualified plugin name.
- The user's request reaches the skill unchanged.
- `/kroger` remains deterministic and unchanged.
- No cart-write tool is exposed to the LLM.
- Nonmatching gateway messages are unaffected.
- Unit tests and documented manual verification pass.
