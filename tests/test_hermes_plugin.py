import importlib.util
import json
import sys
import asyncio
from types import ModuleType
from unittest.mock import Mock

import pytest
from pathlib import Path

from kroger_shopping.hermes_command import handle_kroger
from kroger_shopping.receipts import ReceiptHistoryEntry
from kroger_shopping.models import (
    CartModality,
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
    assert "receipts" in metadata["args_hint"]
    assert "buyagain" in metadata["args_hint"]
    for shortcut in ("-s", "-r", "-a", "-h"):
        assert shortcut in metadata["args_hint"]

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
            "last_purchased_date": None,
            "buy_and_save": False,
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


def test_direct_recommend_json_uses_versioned_public_payload(monkeypatch):
    from kroger_shopping import hermes_command

    product = Product(
        upc="0001111050434",
        product_id="0001111050434",
        description="Simple Truth Milk",
        brand="Simple Truth",
        price=4.00,
        size="8 oz",
    )
    client = Mock()
    client.ranked_search_products.return_value = [
        RankedProduct(
            product=product,
            detail=None,
            preference_score=ProductPreferenceScore(
                total=42.0,
                reasons=["internal score reason"],
                warnings=["internal warning"],
                unwanted_ingredient_count=1,
                unwanted_ingredients=["Artificial colors"],
            ),
            original_kroger_rank=1,
            previously_purchased=True,
            last_purchased_date="2026-07-27",
        )
    ]
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)

    result = json.loads(handle_kroger("recommend --json whole milk"))

    assert result == {
        "schema": "kroger.recommendations.v1",
        "success": True,
        "query": "whole milk",
        "products": [
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
                "last_purchased_date": "2026-07-27",
                "buy_and_save": False,
                "out_of_stock": False,
            }
        ],
    }
    assert "internal score reason" not in json.dumps(result)
    assert "internal warning" not in json.dumps(result)
    client.ranked_search_products.assert_called_once_with("whole milk", limit=10)


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


def test_code_command_parses_pasted_redirect_and_passes_state(monkeypatch):
    from kroger_shopping import hermes_command

    exchanged = []

    class Auth:
        def exchange_code_for_tokens(self, code, state=None):
            exchanged.append((code, state))
            return Mock(scope="product.compact cart.basic:write")

    monkeypatch.setattr(hermes_command, "get_client", lambda: Mock(auth=Auth()))

    output = handle_kroger("code http://localhost:8080/callback?code=abc123&state=s1")

    assert exchanged == [("abc123", "s1")]
    assert output == "Kroger authentication saved. Scope: product.compact cart.basic:write."

    handle_kroger("code abc456")
    assert exchanged[-1] == ("abc456", None)


def test_code_command_reports_parse_errors_without_calling_kroger(monkeypatch):
    from kroger_shopping import hermes_command

    class Auth:
        def exchange_code_for_tokens(self, code, state=None):
            raise AssertionError("must not exchange an unparseable redirect")

    monkeypatch.setattr(hermes_command, "get_client", lambda: Mock(auth=Auth()))

    output = handle_kroger("code http://localhost:8080/callback?error=access_denied")

    assert output.startswith("Authentication error: Kroger authorization was not granted: access_denied")
    assert handle_kroger("code") == "Usage: /kroger code <redirect-url|authorization-code>"


def test_login_command_starts_a_stateful_login(monkeypatch):
    from kroger_shopping import hermes_command

    auth = Mock()
    auth.begin_login.return_value = "https://api.kroger.com/v1/connect/oauth2/authorize?state=s1"
    monkeypatch.setattr(hermes_command, "get_client", lambda: Mock(auth=auth))

    output = handle_kroger("login")

    auth.begin_login.assert_called_once_with()
    auth.authorization_url.assert_not_called()
    assert "https://api.kroger.com/v1/connect/oauth2/authorize?state=s1" in output
    assert "/kroger code <redirect-url>" in output


@pytest.fixture(params=["raw", "direct", "legacy"])
def dispatch_kroger(request, monkeypatch):
    from kroger_shopping import hermes_command
    import shlex

    if request.param == "raw":
        return hermes_command.handle_kroger
    if request.param == "direct":
        def dispatch(raw):
            try:
                tokens = shlex.split(raw)
            except ValueError as exc:
                return f"Validation error: {exc}"
            return hermes_command.handle_kroger_args(tokens[0], tokens[1:])
        return dispatch

    hermes = ModuleType("hermes")
    commands = ModuleType("hermes.commands")
    commands.command = lambda name: lambda handler: handler
    monkeypatch.setitem(sys.modules, "hermes", hermes)
    monkeypatch.setitem(sys.modules, "hermes.commands", commands)
    spec = importlib.util.spec_from_file_location(
        "legacy_kroger_test", Path(__file__).resolve().parents[1] / "commands/kroger.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def dispatch(raw):
        module.get_client = hermes_command.get_client
        return asyncio.run(module.kroger_command(None, *shlex.split(raw)))
    return dispatch


@pytest.mark.parametrize("alias,canonical,arguments,method,expected_args", [
    ("-s", "search", '"lactose free milk"', "search_products", ("lactose free milk",)),
    ("-r", "recommend", "lactose free milk", "ranked_search_products", ("lactose free milk",)),
    ("-a", "add", "0001111050434", "add_to_cart", ("0001111050434", 1)),
    ("-a", "add", "0001111050434 2", "add_to_cart", ("0001111050434", 2)),
])
def test_shortcuts_match_full_commands(monkeypatch, dispatch_kroger, alias, canonical,
                                       arguments, method, expected_args):
    from kroger_shopping import hermes_command

    product = Product(upc="0001111050434", product_id="0001111050434",
                      description="Milk", brand="Simple Truth", price=4.99, size="8 oz")
    client = Mock()
    client.search_products.return_value = [product]
    client.ranked_search_products.return_value = [RankedProduct(
        product=product, detail=None,
        preference_score=ProductPreferenceScore(total=42, reasons=[]),
        original_kroger_rank=1,
    )]
    client.add_to_cart.return_value = True
    client.get_product_detail.return_value = product
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)
    output = dispatch_kroger(f"{alias} {arguments}")
    operation = getattr(client, method)
    kwargs = {} if method == "add_to_cart" else {"limit": 10}
    operation.assert_called_once_with(*expected_args, **kwargs)
    operation.reset_mock()
    assert output == dispatch_kroger(f"{canonical} {arguments}")
    operation.assert_called_once_with(*expected_args, **kwargs)


def test_widget_install_copies_bundled_picker_into_active_hermes_home(monkeypatch, tmp_path):
    from kroger_shopping import widget_install

    source = tmp_path / "bundled-kroger-pick.mjs"
    source.write_text("export default function register() {}\n", encoding="utf-8")
    home = tmp_path / "profile"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(widget_install, "bundled_widget_path", lambda: source)

    output = handle_kroger("widget install")

    destination = home / "tui-widgets" / "kroger-pick.mjs"
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert output == f"Installed Kroger picker widget: `{destination}`"


def test_widget_status_and_remove_track_the_installed_picker(monkeypatch, tmp_path):
    from kroger_shopping import widget_install

    source = tmp_path / "bundled-kroger-pick.mjs"
    source.write_text("export default function register() {}\n", encoding="utf-8")
    home = tmp_path / "profile"
    destination = home / "tui-widgets" / "kroger-pick.mjs"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(widget_install, "bundled_widget_path", lambda: source)

    assert "not installed" in handle_kroger("widget status")
    handle_kroger("widget install")
    assert handle_kroger("widget status") == f"Kroger picker widget is current: `{destination}`"

    destination.write_text("stale\n", encoding="utf-8")
    assert "needs an update" in handle_kroger("widget status")
    assert handle_kroger("widget remove") == f"Removed Kroger picker widget: `{destination}`"
    assert not destination.exists()


def test_widget_command_rejects_unknown_action_without_touching_client(monkeypatch):
    from kroger_shopping import hermes_command

    monkeypatch.setattr(hermes_command, "get_client", Mock(side_effect=AssertionError("client created")))
    assert handle_kroger("widget nope") == "Usage: /kroger widget <install|status|remove>"


@pytest.mark.parametrize("raw,expected", [
    ("-s", "Usage: /kroger search <term>"),
    ("-r", "Usage: /kroger recommend <term>"),
    ("-a", "Usage: /kroger add <UPC> [quantity=1]"),
])
def test_shortcut_missing_arguments(monkeypatch, dispatch_kroger, raw, expected):
    from kroger_shopping import hermes_command
    monkeypatch.setattr(hermes_command, "get_client", Mock(side_effect=AssertionError("client created")))
    assert dispatch_kroger(raw) == expected


@pytest.mark.parametrize("quantity", ["no", "1.5", "0", "-1"])
def test_shortcut_invalid_quantities(monkeypatch, dispatch_kroger, quantity):
    from kroger_shopping import hermes_command
    from kroger_shopping.exceptions import KrogerValidationError
    client = Mock()
    client.add_to_cart.side_effect = KrogerValidationError("quantity must be positive")
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)
    assert dispatch_kroger(f"-a 0001111050434 {quantity}") == dispatch_kroger(f"add 0001111050434 {quantity}")
    if quantity in ("no", "1.5"):
        client.add_to_cart.assert_not_called()
    else:
        assert client.add_to_cart.call_count == 2


def test_shortcut_help_unknown_and_bad_quotes_remain_lazy(monkeypatch):
    from kroger_shopping import hermes_command
    monkeypatch.setattr(hermes_command, "get_client", Mock(side_effect=AssertionError("client created")))
    assert handle_kroger("-h") == handle_kroger("") == hermes_command.help_text()
    assert hermes_command.handle_kroger_args("-h", []) == hermes_command.help_text()
    for raw in ("-x", "-sr", "help"):
        assert handle_kroger(raw) == f"Unknown subcommand: {raw}\n{hermes_command.help_text()}"
    for alias in ("-s", "-r", "-a", "-h"):
        assert handle_kroger(f'{alias} "unterminated') == "Validation error: No closing quotation"


def test_help_shortcut_through_all_adapters(monkeypatch, dispatch_kroger):
    from kroger_shopping import hermes_command
    monkeypatch.setattr(hermes_command, "get_client", Mock(side_effect=AssertionError("client created")))
    assert dispatch_kroger("-h") == hermes_command.help_text()


@pytest.mark.parametrize("quantity", [1, 3])
def test_add_confirms_product_title_upc_and_quantity(monkeypatch, dispatch_kroger, quantity):
    from kroger_shopping import hermes_command

    client = Mock()
    client.add_to_cart.return_value = True
    client.get_product_detail.return_value = Product(
        upc="0001111050434", product_id="0001111050434",
        description="Simple Truth Milk",
    )
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)
    args = "0001111050434" if quantity == 1 else f"0001111050434 {quantity}"

    assert dispatch_kroger(f"add {args}") == (
        f"Added to cart: Simple Truth Milk | UPC: `0001111050434` | Quantity: {quantity}"
    )
    client.add_to_cart.assert_called_once_with("0001111050434", quantity)
    client.get_product_detail.assert_called_once_with("0001111050434")


def test_add_accepts_delivery_modality_and_confirms_it(monkeypatch):
    from kroger_shopping import hermes_command

    client = Mock()
    client.add_to_cart.return_value = True
    client.get_product_detail.return_value = Product(
        upc="0001111050434",
        product_id="0001111050434",
        description="Simple Truth Milk",
    )
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)

    assert handle_kroger("add 0001111050434 1 --modality DELIVERY") == (
        "Added to cart: Simple Truth Milk | UPC: `0001111050434` | Quantity: 1 | Modality: DELIVERY"
    )
    client.add_to_cart.assert_called_once_with(
        "0001111050434",
        1,
        modality=CartModality.DELIVERY,
    )


@pytest.mark.parametrize("lookup_error", [False, True])
def test_add_preserves_success_when_title_unavailable(monkeypatch, lookup_error):
    from kroger_shopping import hermes_command
    from kroger_shopping.exceptions import KrogerError

    client = Mock()
    client.add_to_cart.return_value = True
    client.get_product_detail.return_value = None
    if lookup_error:
        client.get_product_detail.side_effect = KrogerError("Catalog unavailable")
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)

    assert handle_kroger("add 0001111050434 2") == (
        "Added to cart: Title unavailable | UPC: `0001111050434` | Quantity: 2"
    )
    client.add_to_cart.assert_called_once()


def test_failed_add_does_not_lookup_title(monkeypatch):
    from kroger_shopping import hermes_command

    client = Mock()
    client.add_to_cart.return_value = False
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)

    assert handle_kroger("add 0001111050434") == "Failed to add"
    client.get_product_detail.assert_not_called()


def test_receipts_through_adapters(monkeypatch, dispatch_kroger):
    from kroger_shopping import hermes_command, receipts

    history = (
        ReceiptHistoryEntry("z.json", frozenset({"0001111050434"}), True,
                            "1261107276344089802", "April 21, 2026"),
        ReceiptHistoryEntry("a.json", frozenset(), True,
                            "021~00998~2026-05-13~515~491117", "May 13, 2026"),
        ReceiptHistoryEntry("bad.json", frozenset(), False),
        ReceiptHistoryEntry("empty.json", frozenset(), True),
    )
    monkeypatch.setattr(receipts, "load_receipt_history", lambda: history)
    factory = Mock(side_effect=AssertionError("client created"))
    monkeypatch.setattr(hermes_command, "get_client", factory)
    assert dispatch_kroger("receipts") == (
        "- Order number: 021~00998~2026-05-13~515~491117 | Order date: May 13, 2026\n"
        "- bad.json: Unreadable receipt.\n"
        "- Order number: Unavailable | Order date: Unavailable (empty.json)\n"
        "- Order number: 1261107276344089802 | Order date: April 21, 2026"
    )
    assert dispatch_kroger("receipts extra") == "Usage: /kroger receipts"
    monkeypatch.setattr(receipts, "load_receipt_history", lambda: ())
    assert dispatch_kroger("receipts") == "No local purchase history found."
    factory.assert_not_called()


@pytest.mark.parametrize("missing_name", [False, True])
def test_buyagain_uses_local_names_without_client(monkeypatch, dispatch_kroger, missing_name):
    from kroger_shopping import hermes_command, receipts

    first, second = "0001111050434", "0001111050435"
    monkeypatch.setattr(receipts, "load_receipt_history", lambda directory: (
        ReceiptHistoryEntry("history.json", frozenset({first, second}), True,
                            product_names=((first, "Milk"),) if missing_name else
                            ((first, "Milk"), (second, "Bread"))),
        ReceiptHistoryEntry("history.json", frozenset({first}), True),
    ))
    factory = Mock(side_effect=AssertionError("No catalog client needed"))
    monkeypatch.setattr(hermes_command, "get_client", factory)
    output = dispatch_kroger("buyagain")
    assert output.startswith("Previously purchased products: 2\n")
    assert output.count(first) == output.count(second) == 1
    assert output.index(first) < output.index(second)
    assert "Milk" in output
    if missing_name:
        assert "Name unavailable" in output
        assert "Run /kroger pull" in output
    else:
        assert "Bread" in output
        assert "Name unavailable" not in output
    factory.assert_not_called()


def test_buyagain_empty_and_usage_remain_lazy(monkeypatch, dispatch_kroger):
    from kroger_shopping import hermes_command, receipts
    loader = Mock(return_value=frozenset())
    factory = Mock(side_effect=AssertionError("client created"))
    monkeypatch.setattr(receipts, "load_purchase_upcs", loader)
    monkeypatch.setattr(hermes_command, "get_client", factory)
    assert dispatch_kroger("buyagain extra") == "Usage: /kroger buyagain"
    loader.assert_not_called()
    assert dispatch_kroger("buyagain") == "No purchased UPCs found in local receipts."
    assert "/kroger buyagain" in hermes_command.help_text()
    factory.assert_not_called()


@pytest.mark.parametrize("date", [None, "2026-07-27"])
def test_recommend_shows_last_bought(monkeypatch, dispatch_kroger, date):
    from kroger_shopping import hermes_command
    product = Product(upc="0001111050434", product_id="0001111050434", description="Milk")
    client = Mock()
    client.ranked_search_products.return_value = [RankedProduct(
        product=product, detail=None, preference_score=ProductPreferenceScore(total=0),
        original_kroger_rank=1, previously_purchased=True, last_purchased_date=date,
    )]
    monkeypatch.setattr(hermes_command, "get_client", lambda: client)
    output = dispatch_kroger("recommend milk")
    assert "purchased:" not in output
    if date:
        assert "lp: 2026-07-27" in output
    else:
        assert "lp:" not in output


def test_buysave_marker_is_empty_unless_flagged():
    from kroger_shopping.hermes_command import buysave_marker

    assert buysave_marker(True) == " | buysave"
    assert buysave_marker(False) == ""


def test_version_reads_manifest_without_client(monkeypatch, tmp_path):
    from kroger_shopping import hermes_command

    package = tmp_path / "kroger_shopping"
    package.mkdir()
    monkeypatch.setattr(hermes_command, "__file__", str(package / "hermes_command.py"))
    monkeypatch.setattr(
        hermes_command, "get_client", Mock(side_effect=AssertionError("No client needed"))
    )
    (tmp_path / "plugin.yaml").write_text('name: kroger-shopping\nversion: "9.8.7"\n')

    assert handle_kroger("version") == "9.8.7"
    assert handle_kroger("version extra") == "Usage: /kroger version"
    assert "/kroger version" in handle_kroger()
