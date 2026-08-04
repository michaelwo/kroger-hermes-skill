import importlib.util
import json
import sys
from pathlib import Path

from kroger_shopping.hermes_command import handle_kroger
from kroger_shopping.models import (
    Product,
    ProductPreferenceScore,
    RankedProduct,
)


def test_plugin_registers_command_read_only_tools_and_skill():
    plugin_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "kroger_shopping_plugin",
        plugin_root / "__init__.py",
        submodule_search_locations=[str(plugin_root)],
    )
    plugin = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)

    commands = []
    tools = []
    skills = []

    class Context:
        def register_command(self, name, handler, **kwargs):
            commands.append((name, handler, kwargs))

        def register_tool(self, **kwargs):
            tools.append(kwargs)

        def register_skill(self, name, path, **kwargs):
            skills.append((name, path, kwargs))

        def dispatch_tool(self, *args, **kwargs):
            raise AssertionError("direct slash commands must not dispatch Hermes tools")

    plugin.register(Context())

    assert len(commands) == 1
    name, handler, metadata = commands[0]
    assert name == "kroger"
    assert handler.__name__ == "handle_kroger"
    assert metadata["description"] == "Search, recommend, and add Kroger products"
    assert metadata["args_hint"].startswith("<search|recommend|add|")

    assert {tool["name"] for tool in tools} == {
        "kroger_search",
        "kroger_recommend",
        "kroger_auth_status",
    }
    assert {tool["toolset"] for tool in tools} == {"kroger"}
    assert "kroger_add" not in {tool["name"] for tool in tools}

    assert len(skills) == 1
    skill_name, skill_path, skill_metadata = skills[0]
    assert skill_name == "shopping-assistant"
    assert skill_path == plugin_root / "skills" / "shopping-assistant" / "SKILL.md"
    assert skill_path.is_file()
    assert "Conversational Kroger" in skill_metadata["description"]


def test_read_only_recommend_tool_returns_structured_product_data(monkeypatch):
    from kroger_shopping import hermes_tools

    product = Product(
        upc="0001111050434",
        product_id="0001111050434",
        description="Simple Truth Milk",
        brand="Simple Truth",
        price=4.00,
        size="8 oz",
    )

    class Client:
        def ranked_search_products(self, query, limit=10):
            assert (query, limit) == ("whole milk", 3)
            return [
                RankedProduct(
                    product=product,
                    detail=None,
                    preference_score=ProductPreferenceScore(
                        total=42.0,
                        reasons=["Kroger result order signal +6.25"],
                        unwanted_ingredient_count=1,
                        unwanted_ingredients=["Artificial colors"],
                    ),
                    original_kroger_rank=1,
                    previously_purchased=True,
                )
            ]

    monkeypatch.setattr(hermes_tools, "get_client", lambda: Client())

    result = json.loads(
        hermes_tools.handle_recommend({"query": "whole milk", "limit": 3})
    )

    assert result["success"] is True
    assert result["query"] == "whole milk"
    assert result["products"] == [
        {
            "description": "Simple Truth Milk",
            "brand": "Simple Truth",
            "upc": "0001111050434",
            "price": 4.0,
            "size": "8 oz",
            "unit_price": "$0.50/oz",
            "unwanted_ingredient_count": 1,
            "unwanted_ingredients": ["Artificial colors"],
            "ingredient_data_known": True,
            "previously_purchased": True,
            "out_of_stock": False,
        }
    ]
    assert "Kroger result order signal" not in json.dumps(result)


def test_read_only_tools_return_structured_validation_errors():
    from kroger_shopping import hermes_tools

    assert json.loads(hermes_tools.handle_search({"query": ""})) == {
        "success": False,
        "error": "query is required",
    }


def test_direct_kroger_handler_parses_quoted_search(monkeypatch):
    from kroger_shopping import hermes_command

    calls = []

    class Client:
        def search_products(self, term, limit=10):
            calls.append((term, limit))
            return [
                Product(
                    upc="0001111050434",
                    product_id="0001111050434",
                    description="Simple Truth Milk",
                    brand="Simple Truth",
                    price=4.99,
                )
            ]

    monkeypatch.setattr(hermes_command, "get_client", lambda: Client())

    output = handle_kroger('search "whole milk"')

    assert calls == [("whole milk", 10)]
    assert output == (
        "**Simple Truth Milk** - Simple Truth | $4.99 | `0001111050434`"
    )


def test_direct_kroger_handler_returns_usage_without_constructing_client(monkeypatch):
    from kroger_shopping import hermes_command

    monkeypatch.setattr(
        hermes_command,
        "get_client",
        lambda: (_ for _ in ()).throw(AssertionError("client should remain lazy")),
    )

    assert handle_kroger("").startswith("Kroger commands:")
    assert handle_kroger("search") == "Usage: /kroger search <term>"
    assert handle_kroger('search "unterminated') == "Validation error: No closing quotation"
