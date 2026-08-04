"""Hermes plugin registration for Kroger Shopping."""

from pathlib import Path

from .kroger_shopping.hermes_command import handle_kroger
from .kroger_shopping.hermes_tools import (
    AUTH_STATUS_SCHEMA,
    RECOMMEND_SCHEMA,
    SEARCH_SCHEMA,
    handle_auth_status,
    handle_recommend,
    handle_search,
)


def register(ctx):
    """Register direct commands, read-only tools, and the shopping skill."""
    ctx.register_command(
        "kroger",
        handle_kroger,
        description="Search, recommend, and add Kroger products",
        args_hint="<search|recommend|add|login|code|status|logout> [args]",
    )
    ctx.register_tool(
        name="kroger_search",
        toolset="kroger",
        schema=SEARCH_SCHEMA,
        handler=handle_search,
        description="Search Kroger products.",
    )
    ctx.register_tool(
        name="kroger_recommend",
        toolset="kroger",
        schema=RECOMMEND_SCHEMA,
        handler=handle_recommend,
        description="Rank Kroger products using local preferences.",
    )
    ctx.register_tool(
        name="kroger_auth_status",
        toolset="kroger",
        schema=AUTH_STATUS_SCHEMA,
        handler=handle_auth_status,
        description="Check Kroger user authentication status.",
    )
    ctx.register_skill(
        "shopping-assistant",
        Path(__file__).parent / "skills" / "shopping-assistant" / "SKILL.md",
        description="Conversational Kroger product discovery and comparison.",
    )
