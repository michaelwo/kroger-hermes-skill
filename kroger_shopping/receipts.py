import json
import re
import warnings
from datetime import datetime
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_RECEIPTS_DIR = Path(__file__).resolve().parents[1] / "receipts"
BUNDLED_RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"
PURCHASE_HISTORY_FILENAME = "purchase-history.json"


@dataclass(frozen=True)
class ReceiptHistoryEntry:
    """One exported order and its recognized purchase history."""

    filename: str
    upcs: frozenset[str]
    readable: bool
    order_number: str | None = None
    order_date: str | None = None
    product_names: tuple[tuple[str, str], ...] = ()


def load_receipt_history(
    receipts_dir: Path = DEFAULT_RECEIPTS_DIR,
) -> tuple[ReceiptHistoryEntry, ...]:
    """Load receipts in filename order, refreshing when JSON metadata changes."""
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


def load_purchase_names(receipts_dir: Path = DEFAULT_RECEIPTS_DIR) -> dict[str, str]:
    """Return locally exported names, preferring the latest dated order."""
    names = {}
    dates = {}
    for receipt in load_receipt_history(receipts_dir):
        if not receipt.readable:
            continue
        try:
            order_date = datetime.strptime(receipt.order_date or "", "%Y-%m-%d").date().isoformat()
        except ValueError:
            order_date = ""
        for upc, name in receipt.product_names:
            if upc not in names or order_date > dates[upc]:
                names[upc] = name
                dates[upc] = order_date
    return names


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

    path = directory / PURCHASE_HISTORY_FILENAME
    try:
        stat = path.stat()
    except FileNotFoundError:
        return ()
    except OSError as exc:
        _warn_receipt(path.name, exc)
        return ()
    return ((path.name, stat.st_size, stat.st_mtime_ns),)


@lru_cache(maxsize=8)
def _load_receipt_history_cached(
    directory_value: str,
    fingerprint: tuple[tuple[str, int, int], ...],
) -> tuple[ReceiptHistoryEntry, ...]:
    filename = fingerprint[0][0]
    path = Path(directory_value) / filename
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("orders"), list):
            raise ValueError("Expected an object with an orders array")
    except (OSError, UnicodeError, ValueError) as exc:
        _warn_receipt(filename, exc)
        return (ReceiptHistoryEntry(filename, frozenset(), False),)

    history = []
    for index, order in enumerate(payload["orders"]):
        label = f"{filename} orders[{index}]"
        if not isinstance(order, dict) or not isinstance(order.get("upcs", []), list):
            _warn_receipt(label, ValueError("Expected an order object with a UPC array"))
            history.append(ReceiptHistoryEntry(label, frozenset(), False))
            continue
        upcs = frozenset(
            upc for upc in order.get("upcs", [])
            if isinstance(upc, str) and re.fullmatch(r"[0-9]{13}", upc)
        )
        number = order.get("receiptKey")
        date = order.get("orderDate")
        raw_names = order.get("productNames")
        names = tuple(
            (upc, " ".join(name.split())) for upc, name in raw_names.items()
            if upc in upcs and isinstance(name, str) and name.strip()
        ) if isinstance(raw_names, dict) else ()
        history.append(ReceiptHistoryEntry(
            filename, upcs, True,
            number if isinstance(number, str) and number.strip() else None,
            date if isinstance(date, str) and date.strip() else None,
            names,
        ))
    return tuple(history)


def _warn_receipt(filename: str, exc: Exception) -> None:
    warnings.warn(
        f"Could not read Kroger receipt {filename}: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
