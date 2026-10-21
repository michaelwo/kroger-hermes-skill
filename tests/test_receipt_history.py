import json

import pytest

from kroger_shopping import receipts


def write_history(directory, orders):
    (directory / "purchase-history.json").write_text(json.dumps({"orders": orders}))


def test_json_history_cache_and_refresh(tmp_path):
    assert receipts.load_receipt_history(tmp_path) == ()
    write_history(tmp_path, [
        {"receiptKey": "order-1", "orderDate": "2026-10-21", "upcs": [
            "0001111050434", "0001111050434", "123", 1111050435,
            "12345678901234", "１２３４５６７８９０１２３"]},
        {"receiptKey": "order-2", "orderDate": "2026-05-31", "upcs": ["0001111050434", "0001111050435"]},
    ])
    history = receipts.load_receipt_history(tmp_path)
    assert len(history) == 2
    assert history[0].order_number == "order-1"
    assert history[0].order_date == "2026-10-21"
    assert history[0].upcs == frozenset({"0001111050434"})
    assert receipts.load_purchase_upcs(tmp_path) == frozenset({"0001111050434", "0001111050435"})
    assert receipts.load_last_purchase_dates(tmp_path) == {"0001111050434": "2026-10-21", "0001111050435": "2026-05-31"}
    assert receipts.load_receipt_history(tmp_path) is history
    write_history(tmp_path, [{"upcs": ["0001111050436"]}])
    assert receipts.load_purchase_upcs(tmp_path) == frozenset({"0001111050436"})
    (tmp_path / "purchase-history.json").unlink()
    assert receipts.load_receipt_history(tmp_path) == ()


@pytest.mark.parametrize("content", ["invalid", "[]", '{"orders": {}}'])
def test_invalid_json(tmp_path, content):
    (tmp_path / "purchase-history.json").write_text(content)
    with pytest.warns(RuntimeWarning, match="purchase-history.json"):
        entry, = receipts.load_receipt_history(tmp_path)
    assert not entry.readable
    assert not entry.upcs


def test_invalid_order_preserves_valid_orders(tmp_path):
    write_history(tmp_path, [None, {"upcs": "invalid"}, {"upcs": ["0001111050434"]}, {}])
    with pytest.warns(RuntimeWarning):
        history = receipts.load_receipt_history(tmp_path)
    assert [entry.readable for entry in history] == [False, False, True, True]
    assert receipts.load_purchase_upcs(tmp_path) == frozenset({"0001111050434"})


def test_default_directory_fallback_and_root_precedence(tmp_path, monkeypatch):
    root = tmp_path / "receipts"
    bundled = tmp_path / "package" / "receipts"
    bundled.mkdir(parents=True)
    write_history(bundled, [{"upcs": []}])
    monkeypatch.setattr(receipts, "DEFAULT_RECEIPTS_DIR", root)
    monkeypatch.setattr(receipts, "BUNDLED_RECEIPTS_DIR", bundled)
    assert len(receipts.load_receipt_history(root)) == 1
    root.mkdir()
    assert receipts.load_receipt_history(root) == ()
    assert receipts.load_receipt_history(tmp_path / "missing") == ()


def test_last_purchase_dates_choose_latest_valid_order_date(monkeypatch):
    entry = receipts.ReceiptHistoryEntry
    monkeypatch.setattr(receipts, "load_receipt_history", lambda directory: (
        entry("z.json", frozenset({"a", "b"}), True, order_date="December 31, 2025"),
        entry("a.json", frozenset({"a"}), True, order_date="January 2, 2026"),
        entry("later.json", frozenset({"a"}), True, order_date="2026-02-03"),
        entry("missing.json", frozenset({"a", "c"}), True),
        entry("invalid.json", frozenset({"a", "d"}), True, order_date="February 30, 2027"),
        entry("bad.json", frozenset({"a"}), False, order_date="January 1, 2028"),
    ))
    assert receipts.load_last_purchase_dates() == {"a": "2026-02-03", "b": "2025-12-31"}
