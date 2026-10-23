"""Current Buy and Save UPC snapshot. No network and no CDP."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FILENAME = "buysave.json"
ZONE = ZoneInfo("America/New_York")


def upc13(value: object) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits or len(digits) > 13:
        return None
    return digits.zfill(13)


def save_buysave(
    receipts_dir: Path,
    *,
    offer_code: str,
    description: str,
    end: str,
    upcs,
) -> int:
    directory = Path(receipts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    codes = sorted({code for code in (upc13(item) for item in upcs) if code})
    payload = {
        "offer_code": offer_code,
        "description": description,
        "end": str(end)[:10],
        "upcs": codes,
    }
    target = directory / FILENAME
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return len(codes)


def load_buysave_upcs(receipts_dir: Path, *, today: date | None = None) -> set[str]:
    path = Path(receipts_dir) / FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        end = date.fromisoformat(str(payload["end"])[:10])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return set()
    current = today or datetime.now(ZONE).date()
    if end < current:
        return set()
    return {code for code in (upc13(item) for item in payload.get("upcs") or []) if code}
