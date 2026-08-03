import re
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


DEFAULT_RECEIPTS_DIR = Path(__file__).resolve().parents[1] / "receipts"
UPC_LINE_PATTERN = re.compile(r"(?im)^\s*UPC:\s*(\d{13})\s*$")


def extract_upcs_from_text(text: str) -> set[str]:
    """Extract exact Kroger 13-digit UPC lines from receipt text."""
    return set(UPC_LINE_PATTERN.findall(text or ""))


def load_purchase_upcs(receipts_dir: Path = DEFAULT_RECEIPTS_DIR) -> frozenset[str]:
    """Load purchased UPCs from PDFs, refreshing when directory contents change."""
    directory = Path(receipts_dir)
    fingerprint = _receipt_fingerprint(directory)
    if not fingerprint:
        return frozenset()
    return _load_purchase_upcs_cached(str(directory), fingerprint)


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
def _load_purchase_upcs_cached(
    directory_value: str,
    fingerprint: tuple[tuple[str, int, int], ...],
) -> frozenset[str]:
    directory = Path(directory_value)
    purchased = set()
    for filename, _size, _mtime_ns in fingerprint:
        path = directory / filename
        try:
            text = "\n".join(_page_texts(PdfReader(path).pages))
        except Exception as exc:
            _warn_receipt(filename, exc)
            continue
        purchased.update(extract_upcs_from_text(text))
    return frozenset(purchased)


def _page_texts(pages: Iterable[object]) -> Iterable[str]:
    for page in pages:
        yield page.extract_text() or ""


def _warn_receipt(filename: str, exc: Exception) -> None:
    warnings.warn(
        f"Could not read Kroger receipt {filename}: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
