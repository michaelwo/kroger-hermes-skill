"""Hermes plugin registration for Kroger Shopping."""

from .kroger_shopping.hermes_command import handle_kroger


def register(ctx):
    """Register the direct /kroger command with Hermes."""
    ctx.register_command(
        "kroger",
        handle_kroger,
        description="Search, recommend, and add Kroger products",
        args_hint="<search|recommend|add|login|code|status|logout> [args]",
    )
