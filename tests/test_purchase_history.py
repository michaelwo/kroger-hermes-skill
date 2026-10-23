from pathlib import Path
from unittest.mock import Mock

from kroger_shopping.hermes_command import handle_kroger
from kroger_shopping.purchase_history import CdpError, normalize_order, unique_upcs


def test_unique_upcs_keep_thirteen_digit_order():
    order = {
        "lineItems": [
            {"upc": "0001111050434"},
            {"upc": "0001111050434"},
            {"upc": "123"},
            {"upc": "0001111050435"},
            "nope",
        ]
    }
    assert unique_upcs(order) == ["0001111050434", "0001111050435"]


def test_normalize_order_uses_created_date_prefix():
    order = normalize_order({
        "receiptKey": "540~00013~2026-10-20~1460~1",
        "createdDateTime": {"value": "2026-10-21T00:21:17Z"},
        "purchaseType": "DELIVERY",
        "total": "USD 1.00",
        "status": "COMPLETED",
        "handoffStoreId": "54000013",
        "lineItems": [{"upc": "0001111050434"}],
    })
    assert order["orderDate"] == "2026-10-21"
    assert order["upcs"] == ["0001111050434"]
    assert order["receiptKey"].startswith("540~")


def test_pull_command_writes_summary(monkeypatch, tmp_path):
    from kroger_shopping import hermes_command, purchase_history

    path = tmp_path / "purchase-history.json"
    monkeypatch.setattr(
        purchase_history,
        "pull_purchase_history",
        lambda: {"path": path, "orders": 65, "pageTotal": 7},
    )
    monkeypatch.setattr(
        hermes_command,
        "get_client",
        Mock(side_effect=AssertionError("client created")),
    )
    output = handle_kroger("pull")
    assert output.startswith("Wrote 65 orders to `")
    assert str(path) in output
    assert "/kroger receipts" in output
    assert handle_kroger("pull extra") == "Usage: /kroger pull"
    assert "/kroger pull" in handle_kroger()


def test_pull_command_returns_cdp_error(monkeypatch):
    from kroger_shopping import hermes_command, purchase_history

    monkeypatch.setattr(
        purchase_history,
        "pull_purchase_history",
        Mock(side_effect=CdpError("Chrome DevTools is not reachable at 127.0.0.1:9222.")),
    )
    assert handle_kroger("pull") == "Chrome DevTools is not reachable at 127.0.0.1:9222."


def test_pull_preserves_names_for_offline_buyagain(monkeypatch, tmp_path):
    import json
    from kroger_shopping import hermes_command, purchase_history, receipts

    upc = "0001111050434"
    raw = {"receiptKey": "order-1", "createdDateTime": "2026-10-21T00:21:17Z",
           "lineItems": [{"upc": upc, "description": "  Organic\nMilk  "},
                         {"upc": upc, "description": "Duplicate"},
                         {"upc": "123", "description": "Invalid"}]}
    monkeypatch.setattr(purchase_history, "_cdp_json", lambda host, port, path:
                        {"webSocketDebuggerUrl": "ws://test"} if path == "/json/version" else
                        [{"type": "page", "url": "https://www.kroger.com/mypurchases",
                          "webSocketDebuggerUrl": "ws://test"}])
    monkeypatch.setattr(purchase_history, "_evaluate", lambda *args:
                        json.dumps({"orders": [raw], "pageTotal": 1}))
    result = purchase_history.pull_purchase_history(tmp_path)
    payload = json.loads(result["path"].read_text())
    assert payload["orders"][0]["productNames"] == {upc: "Organic Milk"}
    assert receipts.load_purchase_names(tmp_path) == {upc: "Organic Milk"}
    monkeypatch.setattr(hermes_command.receipts, "load_purchase_upcs",
                        lambda: frozenset({upc}))
    names = receipts.load_purchase_names(tmp_path)
    monkeypatch.setattr(hermes_command.receipts, "load_purchase_names", lambda: names)
    client = Mock(side_effect=AssertionError("No network"))
    monkeypatch.setattr(hermes_command, "get_client", client)
    assert "Organic Milk" in handle_kroger("buyagain")
    client.assert_not_called()


def test_detail_names_keep_only_order_upcs_and_preserve_unfetched():
    from kroger_shopping.purchase_history import apply_name_maps, preserve_prior_names

    orders = [{
        "receiptKey": "540~00013~2026-10-20~1460~1",
        "upcs": ["0001111050434"],
        "productNames": {"0001111050434": "List name"},
    }, {
        "receiptKey": "018~00680~2026-09-11~503~1",
        "upcs": ["0001111036789"],
        "productNames": {"0001111036789": "Old fuel"},
    }]
    fetched = apply_name_maps(orders, {
        "540~00013~2026-10-20~1460~1": {
            "0001111050434": "  Artesano   Buns  ",
            "0009999999999": "Not on the order",
        },
        "018~00680~2026-09-11~503~1": {"0001111036838": "Different fuel UPC"},
    }, [
        "540~00013~2026-10-20~1460~1",
        "018~00680~2026-09-11~503~1",
    ])
    assert orders[0]["productNames"] == {"0001111050434": "Artesano Buns"}
    assert "productNames" not in orders[1]
    assert fetched == {
        "540~00013~2026-10-20~1460~1",
        "018~00680~2026-09-11~503~1",
    }
    missed = [{"receiptKey": "021~00998~2026-01-24~505~1", "upcs": ["0078535702350"]}]
    preserve_prior_names(missed, [{
        "receiptKey": "021~00998~2026-01-24~505~1",
        "productNames": {"0078535702350": "Peet's"},
    }], set())
    assert missed[0]["productNames"]["0078535702350"] == "Peet's"
    preserve_prior_names(orders[1:], [{
        "receiptKey": "018~00680~2026-09-11~503~1",
        "productNames": {"0001111036789": "Old fuel"},
    }], fetched)
    assert "productNames" not in orders[1]
    order = normalize_order({"lineItems": [
        {"upc": "0001111050434", "productName": "Milk"},
        {"upc": "0001111050435", "name": "Bread"},
        {"upc": "0001111050436", "description": None},
    ]})
    assert order["productNames"] == {"0001111050434": "Milk", "0001111050435": "Bread"}
    assert len(order["upcs"]) == 3


def test_file_fetcher_reads_local_json(tmp_path):
    import json

    from kroger_shopping.file_backend import FileFetcher
    from kroger_shopping.receipts import PURCHASE_HISTORY_FILENAME

    path = tmp_path / PURCHASE_HISTORY_FILENAME
    path.write_text(
        json.dumps({
            "pageTotal": 2,
            "orders": [
                {
                    "receiptKey": "a",
                    "upcs": ["0001111050434"],
                    "productNames": {"0001111050434": "Milk"},
                },
                {"receiptKey": "b", "upcs": ["0001111050435"]},
            ],
        })
        + "\n",
        encoding="utf-8",
    )
    result = FileFetcher(tmp_path).pull_purchase_history()
    assert result["orders"] == 2
    assert result["titled"] == 1
    assert result["pageTotal"] == 2
    assert result["path"] == path


def test_file_fetcher_missing_file(tmp_path):
    from kroger_shopping.exceptions import KrogerError
    from kroger_shopping.file_backend import FileFetcher

    try:
        FileFetcher(tmp_path).pull_purchase_history()
    except KrogerError as exc:
        assert "No purchase history" in str(exc)
    else:
        raise AssertionError("expected KrogerError")


def test_pull_command_uses_injected_fetcher(monkeypatch):
    from kroger_shopping import hermes_command

    class FakeFetcher:
        def pull_purchase_history(self, receipts_dir=None):
            return {
                "path": Path("/tmp/purchase-history.json"),
                "orders": 3,
                "pageTotal": 1,
                "titled": 2,
            }

    monkeypatch.setattr(
        hermes_command,
        "get_client",
        Mock(side_effect=AssertionError("client created")),
    )
    output = hermes_command._pull_purchase_history_text(FakeFetcher())
    assert output.startswith("Wrote 3 orders to `")
    assert "/tmp/purchase-history.json" in output
    assert "Titles on 2 orders" in output
