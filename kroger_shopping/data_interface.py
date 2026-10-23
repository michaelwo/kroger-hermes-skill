"""Purchase-history fetchers, independent of CDP vs local JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class KrogerDataFetcher(Protocol):
    """Fetch purchase history without tying callers to Chrome DevTools."""

    def pull_purchase_history(self, receipts_dir: Path | None = None) -> dict[str, Any]:
        """Return `{path, orders, pageTotal, titled}` after reading or writing JSON."""
        ...
