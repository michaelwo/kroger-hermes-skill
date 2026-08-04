"""Compatibility adapter for Hermes versions using ``hermes.commands``."""

import shlex

from hermes.commands import command
from kroger_shopping import hermes_command


get_client = hermes_command.get_client


@command("kroger")
async def kroger_command(ctx, subcommand: str = None, *args):
    """Delegate the legacy command API to the shared direct handler."""
    del ctx
    if not subcommand:
        return hermes_command.handle_kroger()

    raw_args = shlex.join([subcommand, *args])
    original_get_client = hermes_command.get_client
    try:
        # Preserve the legacy module's test/customization seam.
        hermes_command.get_client = get_client
        return hermes_command.handle_kroger(raw_args)
    finally:
        hermes_command.get_client = original_get_client
