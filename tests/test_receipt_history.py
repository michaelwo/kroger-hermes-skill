from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from kroger_shopping import receipts


def test_history_shares_upcs_cache_and_refreshes(tmp_path, monkeypatch):
    assert receipts.load_receipt_history(tmp_path / "missing") == ()
    assert receipts.load_receipt_history(tmp_path) == ()
    calls = []

    def reader(path):
        calls.append(path.name)
        if path.name == "bad.pdf":
            raise ValueError("bad PDF")
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: path.read_text())])

    monkeypatch.setattr(receipts, "PdfReader", reader)
    (tmp_path / "a.pdf").write_text("UPC: 0001111050434\nUPC: 0001111050434")
    (tmp_path / "b.pdf").write_text("UPC: 0001111050434\nUPC: 0001111050435")
    (tmp_path / "empty.pdf").write_text("UPC: 123\nUPC: 12345678901234")
    (tmp_path / "bad.pdf").write_bytes(b"broken")
    (tmp_path / "ignored.txt").write_text("UPC: 0001111050436")
    with pytest.warns(RuntimeWarning, match="bad.pdf"):
        history = receipts.load_receipt_history(tmp_path)
    assert [entry.filename for entry in history] == ["a.pdf", "b.pdf", "bad.pdf", "empty.pdf"]
    assert history[2].readable is False
    assert history[3].readable is True and not history[3].upcs
    assert receipts.load_purchase_upcs(tmp_path) == frozenset({"0001111050434", "0001111050435"})
    assert receipts.load_receipt_history(tmp_path) is history
    assert len(calls) == 4
    (tmp_path / "a.pdf").write_text("UPC: 0001111050436")
    with pytest.warns(RuntimeWarning):
        refreshed = receipts.load_receipt_history(tmp_path)
    assert refreshed[0].upcs == frozenset({"0001111050436"})
    assert receipts.load_purchase_upcs(tmp_path) == frozenset(upc for entry in refreshed for upc in entry.upcs)
    (tmp_path / "b.pdf").unlink()
    with pytest.warns(RuntimeWarning):
        assert len(receipts.load_receipt_history(tmp_path)) == 3


def test_real_empty_and_malformed_pdfs(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(tmp_path / "empty.pdf")
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf")
    with pytest.warns(RuntimeWarning, match="bad.pdf"):
        history = receipts.load_receipt_history(tmp_path)
    assert history == (
        receipts.ReceiptHistoryEntry("bad.pdf", frozenset(), False),
        receipts.ReceiptHistoryEntry("empty.pdf", frozenset(), True),
    )


@pytest.mark.parametrize("number,date", [
    ("1261107276344089802", "April 21, 2026"),
    ("021~00998~2026-05-13~515~491117", "May 13, 2026"),
    (None, "May 13, 2026"),
    ("1261107276344089802", None),
])
def test_order_metadata_from_pdf_text(tmp_path, monkeypatch, number, date):
    text = "Order Type: Delivery\n"
    if date:
        text += f"Order Date: {date}\n"
    if number:
        text += f"Order Number: {number}\n"
    text += "UPC: 0001111050434\n"
    (tmp_path / "receipt.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(receipts, "PdfReader", lambda path: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: text)]))
    entry, = receipts.load_receipt_history(tmp_path)
    assert entry.order_number == number
    assert entry.order_date == date
    assert receipts.load_purchase_upcs(tmp_path) == frozenset({"0001111050434"})


def test_default_directory_fallback_and_root_precedence(tmp_path, monkeypatch):
    root = tmp_path / "receipts"
    bundled = tmp_path / "package" / "receipts"
    bundled.mkdir(parents=True)
    (bundled / "receipt.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(receipts, "DEFAULT_RECEIPTS_DIR", root)
    monkeypatch.setattr(receipts, "BUNDLED_RECEIPTS_DIR", bundled)
    monkeypatch.setattr(receipts, "PdfReader", lambda path: SimpleNamespace(pages=[]))
    assert len(receipts.load_receipt_history(root)) == 1
    root.mkdir()
    assert receipts.load_receipt_history(root) == ()
    assert receipts.load_receipt_history(tmp_path / "missing") == ()


def test_last_purchase_dates_choose_latest_valid_order_date(monkeypatch):
    entry = receipts.ReceiptHistoryEntry
    monkeypatch.setattr(receipts, "load_receipt_history", lambda directory: (
        entry("z.pdf", frozenset({"a", "b"}), True, order_date="December 31, 2025"),
        entry("a.pdf", frozenset({"a"}), True, order_date="January 2, 2026"),
        entry("later.pdf", frozenset({"a"}), True, order_date="2026-02-03"),
        entry("missing.pdf", frozenset({"a", "c"}), True),
        entry("invalid.pdf", frozenset({"a", "d"}), True, order_date="February 30, 2027"),
        entry("bad.pdf", frozenset({"a"}), False, order_date="January 1, 2028"),
    ))
    assert receipts.load_last_purchase_dates() == {"a": "2026-02-03", "b": "2025-12-31"}
