import re
import warnings
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


DEFAULT_RECEIPTS_DIR = Path(__file__).resolve().parents[1] / "receipts"
BUNDLED_RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"
UPC_LINE_PATTERN = re.compile(r"(?im)^\s*UPC:\s*(\d{13})\s*$")


def extract_upcs_from_text(text: str) -> set[str]:
    """Extract exact Kroger 13-digit UPC lines from receipt text."""
    return set(UPC_LINE_PATTERN.findall(text or ""))


@dataclass(frozen=True)
class ReceiptHistoryEntry:
    """One local receipt and its recognized purchase history."""

    filename: str
    upcs: frozenset[str]
    readable: bool
    order_number: str | None = None
    order_date: str | None = None


def load_receipt_history(
    receipts_dir: Path = DEFAULT_RECEIPTS_DIR,
) -> tuple[ReceiptHistoryEntry, ...]:
    """Load receipts in filename order, refreshing when PDF metadata changes."""
    directory = Path(receipts_dir)
    if directory == DEFAULT_RECEIPTS_DIR and not directory.is_dir():
        directory = BUNDLED_RECEIPTS_DIR
    fingerprint = _receipt_fingerprint(directory)
    if not fingerprint:
        return ()
    return _load_receipt_history_cached(str(directory), fingerprint)


def load_purchase_upcs(receipts_dir: Path = DEFAULT_RECEIPTS_DIR) -> frozenset[str]:
    """Load the distinct purchased UPCs from the shared receipt history."""
    return frozenset(upc for receipt in load_receipt_history(receipts_dir) for upc in receipt.upcs)


def load_last_purchase_dates(
    receipts_dir: Path = DEFAULT_RECEIPTS_DIR,
) -> dict[str, str]:
    """Return each UPC's latest valid receipt order date in ISO format."""
    latest = {}
    for receipt in load_receipt_history(receipts_dir):
        if not receipt.readable or not receipt.order_date:
            continue
        for pattern in ("%B %d, %Y", "%Y-%m-%d"):
            try:
                order_date = datetime.strptime(receipt.order_date, pattern).date().isoformat()
                break
            except ValueError:
                continue
        else:
            continue
        for upc in receipt.upcs:
            if upc not in latest or order_date > latest[upc]:
                latest[upc] = order_date
    return latest


def _receipt_fingerprint(directory: Path) -> tuple[tuple[str, int, int], ...]:
    if not directory.is_dir():
        return ()

    entries = []
    for path in sorted(directory.glob("*.pdf")):
        try:
            stat = path.stat()
        except OSError as exc:
            _warn_receipt(path.name, exc)
            continue
        entries.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(entries)


@lru_cache(maxsize=8)
def _load_receipt_history_cached(
    directory_value: str,
    fingerprint: tuple[tuple[str, int, int], ...],
) -> tuple[ReceiptHistoryEntry, ...]:
    directory = Path(directory_value)
    history = []
    for filename, _size, _mtime_ns in fingerprint:
        path = directory / filename
        try:
            text = "\n".join(_page_texts(PdfReader(path).pages))
        except Exception as exc:
            _warn_receipt(filename, exc)
            history.append(ReceiptHistoryEntry(filename, frozenset(), False))
            continue
        number = re.search(r"(?im)^[ \t]*Order Number:[ \t]*([^\r\n]+)", text)
        date = re.search(r"(?im)^[ \t]*Order Date:[ \t]*([^\r\n]+)", text)
        history.append(ReceiptHistoryEntry(
            filename, frozenset(extract_upcs_from_text(text)), True,
            number.group(1).strip() if number else None,
            date.group(1).strip() if date else None,
        ))
    return tuple(history)


def _page_texts(pages: Iterable[object]) -> Iterable[str]:
    for page in pages:
        yield page.extract_text() or ""


def _warn_receipt(filename: str, exc: Exception) -> None:
    warnings.warn(
        f"Could not read Kroger receipt {filename}: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
