import re
from dataclasses import dataclass
from typing import Optional

from .models import Product


@dataclass(frozen=True)
class ParsedSize:
    quantity: float
    unit: str


@dataclass(frozen=True)
class UnitPrice:
    price: float
    unit: str
    source: str


_UNIT_ALIASES = {
    "fl oz": "fl oz",
    "fluid oz": "fl oz",
    "fluid ounce": "fl oz",
    "fluid ounces": "fl oz",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "gal": "gal",
    "gallon": "gal",
    "gallons": "gal",
    "qt": "qt",
    "quart": "qt",
    "quarts": "qt",
    "pt": "pt",
    "pint": "pt",
    "pints": "pt",
    "ct": "ct",
    "count": "ct",
}


def parse_size_for_unit_price(size: Optional[str]) -> Optional[ParsedSize]:
    if not size:
        return None

    normalized = re.sub(r"\s+", " ", size.strip().lower())
    if not normalized:
        return None

    if _is_ambiguous_size(normalized):
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z. ]+)", normalized)
    if not match:
        return None

    quantity = float(match.group(1))
    if quantity <= 0:
        return None

    unit_key = re.sub(r"\s+", " ", match.group(2).replace(".", " ")).strip()
    unit = _UNIT_ALIASES.get(unit_key)
    if not unit:
        return None

    return ParsedSize(quantity=quantity, unit=unit)


def unit_price_for_product(product: Product) -> Optional[UnitPrice]:
    parsed_size = parse_size_for_unit_price(product.size)

    if product.regular_per_unit_estimate is not None:
        unit = parsed_size.unit if parsed_size else "unit"
        return UnitPrice(
            price=float(product.regular_per_unit_estimate),
            unit=unit,
            source="api",
        )

    if product.price is None or not parsed_size:
        return None

    price = float(product.price)
    if price <= 0:
        return None

    return UnitPrice(
        price=price / parsed_size.quantity,
        unit=parsed_size.unit,
        source="computed",
    )


def format_unit_price(product: Product) -> str:
    unit_price = unit_price_for_product(product)
    if unit_price is None:
        return "N/A"
    return f"${unit_price.price:.2f}/{unit_price.unit}"


def _is_ambiguous_size(size: str) -> bool:
    if "/" in size or " x " in size or "-" in size:
        return True
    if re.search(r"\b(about|approx|approximately|pk|pack|packs|package|packages)\b", size):
        return True
    return False
