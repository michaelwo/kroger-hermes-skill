import importlib.util
import sys
from pathlib import Path

from kroger_shopping.hermes_command import handle_kroger
from kroger_shopping.models import Product


def test_plugin_registers_direct_kroger_command():
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

    registrations = []

    class Context:
        def register_command(self, name, handler, **kwargs):
            registrations.append((name, handler, kwargs))

        def dispatch_tool(self, *args, **kwargs):
            raise AssertionError("direct slash commands must not dispatch Hermes tools")

    plugin.register(Context())

    assert len(registrations) == 1
    name, handler, metadata = registrations[0]
    assert name == "kroger"
    assert handler.__name__ == "handle_kroger"
    assert metadata["description"] == "Search, recommend, and add Kroger products"
    assert metadata["args_hint"].startswith("<search|recommend|add|")


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
