"""CDP-backed purchase-history fetch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .purchase_history import CdpError


class CDPFetcher:
    """Pull purchase history from a logged-in kroger.com/mypurchases tab."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host
        self.port = port

    def pull_purchase_history(self, receipts_dir: Path | None = None) -> dict[str, Any]:
        from . import purchase_history as ph

        kwargs: dict[str, Any] = {}
        if receipts_dir is not None:
            kwargs["receipts_dir"] = receipts_dir
        if self.host is not None:
            kwargs["host"] = self.host
        if self.port is not None:
            kwargs["port"] = self.port
        return ph.pull_purchase_history(**kwargs)


__all__ = ["CDPFetcher", "CdpError"]
