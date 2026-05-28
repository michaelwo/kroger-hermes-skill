import json
import os
import time
from datetime import datetime, date
from typing import Dict

USAGE_FILE = os.path.expanduser("~/.kroger_usage.json")


class RateLimitTracker:
    """Tracks daily API usage against Kroger rate limits."""

    LIMITS = {
        "products": 10000,
        "cart": 5000,
    }

    def __init__(self):
        self.usage = self._load_usage()

    def _load_usage(self) -> Dict:
        if not os.path.exists(USAGE_FILE):
            return {"date": str(date.today()), "products": 0, "cart": 0}
        try:
            with open(USAGE_FILE) as f:
                data = json.load(f)
            # Reset if it's a new day
            if data.get("date") != str(date.today()):
                return {"date": str(date.today()), "products": 0, "cart": 0}
            return data
        except Exception:
            return {"date": str(date.today()), "products": 0, "cart": 0}

    def _save_usage(self):
        with open(USAGE_FILE, "w") as f:
            json.dump(self.usage, f, indent=2)

    def record_call(self, endpoint: str):
        """Record an API call."""
        key = "products" if "products" in endpoint else "cart"
        self.usage[key] = self.usage.get(key, 0) + 1
        self._save_usage()

    def get_usage(self) -> Dict:
        """Return current usage and limits."""
        return {
            "date": self.usage["date"],
            "products": {
                "used": self.usage.get("products", 0),
                "limit": self.LIMITS["products"],
                "remaining": self.LIMITS["products"] - self.usage.get("products", 0),
            },
            "cart": {
                "used": self.usage.get("cart", 0),
                "limit": self.LIMITS["cart"],
                "remaining": self.LIMITS["cart"] - self.usage.get("cart", 0),
            },
        }

    def check_limit(self, endpoint: str) -> bool:
        """Return True if we're approaching the limit."""
        key = "products" if "products" in endpoint else "cart"
        used = self.usage.get(key, 0)
        limit = self.LIMITS[key]
        return used >= (limit * 0.9)  # Warn at 90% usage
