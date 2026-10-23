"""Local JSON purchase-history fetch, for tests and offline use."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import KrogerError
from .receipts import DEFAULT_RECEIPTS_DIR, PURCHASE_HISTORY_FILENAME


class FileFetcher:
    """Read an existing `purchase-history.json` without talking to Chrome."""

    def __init__(self, receipts_dir: Path | None = None) -> None:
        self.receipts_dir = (
            Path(receipts_dir) if receipts_dir is not None else DEFAULT_RECEIPTS_DIR
        )

    def pull_purchase_history(self, receipts_dir: Path | None = None) -> dict[str, Any]:
        directory = Path(receipts_dir) if receipts_dir is not None else self.receipts_dir
        path = directory / PURCHASE_HISTORY_FILENAME
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise KrogerError(f"No purchase history at {path}.") from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise KrogerError(f"Purchase history at {path} is unreadable.") from exc
        orders = payload.get("orders") if isinstance(payload, dict) else None
        if not isinstance(orders, list):
            orders = []
        titled = sum(
            1
            for order in orders
            if isinstance(order, dict) and order.get("productNames")
        )
        return {
            "path": path,
            "orders": len(orders),
            "pageTotal": payload.get("pageTotal") if isinstance(payload, dict) else None,
            "titled": titled,
        }
