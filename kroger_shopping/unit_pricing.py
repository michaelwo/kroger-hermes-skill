import re
from dataclasses import dataclass
from typing import Optional, Sequence

from .models import Product


@dataclass(frozen=True)
class ParsedSize:
    quantity: float
    unit: str
    family: str
    base_quantity: float
    base_unit: str


@dataclass(frozen=True)
class UnitPrice:
    price: float
    unit: str
    source: str
    family: Optional[str] = None


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

_UNIT_METADATA = {
    "oz": ("us_weight", "oz", 1.0),
    "lb": ("us_weight", "oz", 16.0),
    "fl oz": ("us_volume", "fl oz", 1.0),
    "pt": ("us_volume", "fl oz", 16.0),
    "qt": ("us_volume", "fl oz", 32.0),
    "gal": ("us_volume", "fl oz", 128.0),
    "g": ("metric_weight", "g", 1.0),
    "kg": ("metric_weight", "g", 1000.0),
    "ct": ("count", "ct", 1.0),
}


def parse_size_for_unit_price(size: Optional[str]) -> Optional[ParsedSize]:
    if not size:
        return None

    normalized = re.sub(r"\s+", " ", size.strip().lower())
    if not normalized:
        return None

    counted_total_size = _parse_counted_total_size(normalized)
    if counted_total_size is not None:
        return counted_total_size

    if _is_ambiguous_size(normalized):
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z. ]+)", normalized)
    if not match:
        return None

    return _parsed_size_from_match(match)


def _parsed_size_from_unit_qty(qty_str: str, unit_str: str) -> Optional[ParsedSize]:
    try:
        quantity = float(qty_str)
    except (ValueError, TypeError):
        return None
    if quantity <= 0:
        return None
    unit_key = re.sub(r"\s+", " ", unit_str.replace(".", " ")).strip()
    unit = _UNIT_ALIASES.get(unit_key)
    if not unit:
        return None
    family, base_unit, base_multiplier = _UNIT_METADATA[unit]
    return ParsedSize(
        quantity=quantity,
        unit=unit,
        family=family,
        base_quantity=quantity * base_multiplier,
        base_unit=base_unit,
    )


def _parsed_size_from_match(match: re.Match[str]) -> Optional[ParsedSize]:
    return _parsed_size_from_unit_qty(match.group(1), match.group(2))


# Labels that indicate the outer count is a per-unit multiplier (not just a descriptor).
# "sticks" and plain counts mean M is the total size; "ct"/"bottles"/"cans" mean N×M is total.
_MULTIPACK_MULTIPLIER_LABELS = frozenset({"ct", "bottle", "bottles", "can", "cans"})


def _parse_counted_total_size(size: str) -> Optional[ParsedSize]:
    # "N x M unit" → N × M total
    x_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s+x\s+(\d+(?:\.\d+)?)\s*([a-z. ]+)",
        size,
    )
    if x_match:
        count = float(x_match.group(1))
        if count <= 0:
            return None
        parsed = _parsed_size_from_unit_qty(x_match.group(2), x_match.group(3))
        if parsed is None:
            return None
        return ParsedSize(
            quantity=parsed.quantity * count,
            unit=parsed.unit,
            family=parsed.family,
            base_quantity=parsed.base_quantity * count,
            base_unit=parsed.base_unit,
        )

    # "N[label] / M unit [/ pk pk]" format
    # When label is "ct"/"bottles"/"cans", outer count N is a per-unit multiplier (total = N×M).
    # When label is "sticks" or absent, M is already the total size (total = M).
    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)(\s+(?:sticks?|ct|bottles?|cans?))?\s*/\s*"
        r"(\d+(?:\.\d+)?)\s*([a-z. ]+?)"
        r"(?:\s*/\s*(\d+(?:\.\d+)?)\s*pk)?",
        size,
    )
    if not match:
        return None

    label = (match.group(2) or "").strip()
    pack_count = float(match.group(5)) if match.group(5) else 1.0
    if pack_count <= 0:
        return None

    parsed = _parsed_size_from_unit_qty(match.group(3), match.group(4))
    if parsed is None:
        return None

    if label in _MULTIPACK_MULTIPLIER_LABELS:
        outer_count = float(match.group(1))
        if outer_count <= 0:
            return None
        total_multiplier = outer_count * pack_count
    else:
        total_multiplier = pack_count

    return ParsedSize(
        quantity=parsed.quantity * total_multiplier,
        unit=parsed.unit,
        family=parsed.family,
        base_quantity=parsed.base_quantity * total_multiplier,
        base_unit=parsed.base_unit,
    )


def unit_price_for_product(product: Product, products: Optional[Sequence[Product]] = None) -> Optional[UnitPrice]:
    parsed_size = parse_size_for_unit_price(product.size)
    target_unit = _target_unit_for_product(product, products, parsed_size)

    if product.regular_per_unit_estimate is not None:
        unit = parsed_size.unit if parsed_size else "unit"
        price = float(product.regular_per_unit_estimate)
        if parsed_size and target_unit == parsed_size.base_unit:
            price = price / (parsed_size.base_quantity / parsed_size.quantity)
            unit = target_unit
        return UnitPrice(
            price=price,
            unit=unit,
            source="api",
            family=parsed_size.family if parsed_size else None,
        )

    if product.price is None or not parsed_size:
        return None

    price = float(product.price)
    if price <= 0:
        return None

    denominator = parsed_size.base_quantity if target_unit == parsed_size.base_unit else parsed_size.quantity
    unit = target_unit if target_unit else parsed_size.unit
    return UnitPrice(
        price=price / denominator,
        unit=unit,
        source="computed",
        family=parsed_size.family,
    )


def format_unit_price(product: Product, products: Optional[Sequence[Product]] = None) -> str:
    unit_price = unit_price_for_product(product, products)
    if unit_price is None:
        return "N/A"
    return f"${unit_price.price:.2f}/{unit_price.unit}"


def format_unit_price_for_products(product: Product, products: Sequence[Product]) -> str:
    return format_unit_price(product, products)


def _target_unit_for_product(
    product: Product,
    products: Optional[Sequence[Product]],
    parsed_size: Optional[ParsedSize],
) -> Optional[str]:
    if not parsed_size:
        return None
    if not products:
        return parsed_size.base_unit

    families = {parsed_size.family}
    for candidate in products:
        candidate_size = parse_size_for_unit_price(candidate.size)
        if candidate_size:
            families.add(candidate_size.family)

    # Normalize inside each compatible family even when the result set mixes unrelated units.
    return parsed_size.base_unit if parsed_size.family in families else parsed_size.unit


def _is_ambiguous_size(size: str) -> bool:
    if "/" in size or " x " in size or "-" in size:
        return True
    if re.search(r"\b(about|approx|approximately|pk|pack|packs|package|packages)\b", size):
        return True
    return False
