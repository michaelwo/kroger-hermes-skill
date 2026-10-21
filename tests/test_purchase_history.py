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
