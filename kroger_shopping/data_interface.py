from typing import List, Protocol
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Order:
    receipt_key: str
    order_date: str # YYYY-MM-DD
    purchase_type: str
    total: float
    status: str
    upcs: List[str]
    
class KrogerDataFetcher(Protocol):
    """
    Interface for fetching Kroger purchase history data.
    Decouples data retrieval from the specific transport mechanism (e.g., CDP).
    """
    def fetch_purchase_history(self) -> List[Order]:
        """
        Fetches all purchase orders.
        Called by high-level plugin logic (kroger_shopping/hermes_command.py).
        """
        ... # Implementation depends on the concrete fetcher (CDP, File, etc.)
    
    def fetch_all_upcs(self) -> List[str]:
        """
        Retrieves all unique UPCs from the current dataset.
        """
        ... # Implementation depends on the concrete fetcher
