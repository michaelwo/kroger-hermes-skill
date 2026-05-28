from typing import List, Sequence, Union

from .exceptions import KrogerValidationError
from .models import CartModality, ProductFulfillment


MIN_PRODUCT_SEARCH_LIMIT = 1
MAX_PRODUCT_SEARCH_LIMIT = 50
MIN_LOCATION_LIMIT = 1
MAX_LOCATION_LIMIT = 200
MIN_LOCATION_RADIUS = 1
MAX_LOCATION_RADIUS = 100


def validate_search_term(term: str) -> str:
    if term is None:
        raise KrogerValidationError("Search term is required")
    term = term.strip()
    if len(term) < 3:
        raise KrogerValidationError("Search term must be at least 3 characters")
    return term


def validate_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise KrogerValidationError("Search limit must be a whole number")
    if not MIN_PRODUCT_SEARCH_LIMIT <= limit <= MAX_PRODUCT_SEARCH_LIMIT:
        raise KrogerValidationError("Search limit must be between 1 and 50")
    return limit


def validate_location_id(location_id: str) -> str:
    location_id = location_id.strip()
    if len(location_id) != 8 or not location_id.isdigit():
        raise KrogerValidationError("Location ID must be exactly 8 digits")
    return location_id


def validate_fulfillment(
    fulfillment: Union[ProductFulfillment, Sequence[ProductFulfillment]],
) -> str:
    if isinstance(fulfillment, ProductFulfillment):
        return fulfillment.value
    if isinstance(fulfillment, str) or not isinstance(fulfillment, Sequence):
        allowed = ", ".join(item.name for item in ProductFulfillment)
        raise KrogerValidationError(f"Fulfillment must be ProductFulfillment enum values: {allowed}")

    values = []
    for item in fulfillment:
        if not isinstance(item, ProductFulfillment):
            allowed = ", ".join(value.name for value in ProductFulfillment)
            raise KrogerValidationError(f"Fulfillment must be ProductFulfillment enum values: {allowed}")
        values.append(item.value)
    if not values:
        raise KrogerValidationError("Fulfillment must include at least one ProductFulfillment value")
    return ",".join(values)


def validate_product_id(product_id: str, field_name: str = "Product ID") -> str:
    if product_id is None:
        raise KrogerValidationError(f"{field_name} is required")
    product_id = product_id.strip()
    if len(product_id) != 13 or not product_id.isdigit():
        raise KrogerValidationError(f"{field_name} must be exactly 13 digits")
    return product_id


def validate_quantity(quantity: int) -> int:
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise KrogerValidationError("Quantity must be a whole number")
    if quantity < 1:
        raise KrogerValidationError("Quantity must be at least 1")
    return quantity


def validate_cart_modality(modality: Union[CartModality, str]) -> CartModality:
    if isinstance(modality, CartModality):
        return modality
    if modality is None or not str(modality).strip():
        raise KrogerValidationError("Cart modality is required")

    value = str(modality).strip().upper()
    try:
        return CartModality(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in CartModality)
        raise KrogerValidationError(f"Cart modality must be one of: {allowed}") from exc


def validate_int_range(
    value: int,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KrogerValidationError(f"{field_name} must be a whole number")
    if not minimum <= value <= maximum:
        raise KrogerValidationError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def validate_zip_code(zip_code: str) -> str:
    zip_code = zip_code.strip()
    if len(zip_code) != 5 or not zip_code.isdigit():
        raise KrogerValidationError("ZIP code must be exactly 5 digits")
    return zip_code


def validate_coordinate(value: Union[str, float, int], field_name: str) -> str:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise KrogerValidationError(f"{field_name} must be a number") from exc

    if field_name == "Latitude" and not -90 <= coordinate <= 90:
        raise KrogerValidationError("Latitude must be between -90 and 90")
    if field_name == "Longitude" and not -180 <= coordinate <= 180:
        raise KrogerValidationError("Longitude must be between -180 and 180")
    return str(value).strip()


def validate_lat_long(lat_long: str) -> str:
    parts = [part.strip() for part in lat_long.split(",")]
    if len(parts) != 2 or not all(parts):
        raise KrogerValidationError("Latitude/longitude must be formatted as 'lat,lon'")
    lat = validate_coordinate(parts[0], "Latitude")
    lon = validate_coordinate(parts[1], "Longitude")
    return f"{lat},{lon}"


def validate_location_ids(location_ids: Union[str, List[str]]) -> str:
    values = split_filter_values(location_ids)
    return ",".join(validate_location_id(value) for value in values)


def validate_department_id(department_id: str) -> str:
    department_id = department_id.strip()
    if len(department_id) != 2 or not department_id.isdigit():
        raise KrogerValidationError("Department ID must be exactly 2 digits")
    return department_id


def validate_department_ids(department_ids: Union[str, List[str]]) -> str:
    values = split_filter_values(department_ids)
    return ",".join(validate_department_id(value) for value in values)


def split_filter_values(values: Union[str, List[str]]) -> List[str]:
    if isinstance(values, str):
        items = [value.strip() for value in values.split(",")]
    else:
        items = [str(value).strip() for value in values]
    if not items or any(not item for item in items):
        raise KrogerValidationError("Filter values must be non-empty")
    return items


def validate_required_name(name: str, field_name: str) -> str:
    if name is None or not name.strip():
        raise KrogerValidationError(f"{field_name} is required")
    return name.strip()
