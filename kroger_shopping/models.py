from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any


class CartModality(str, Enum):
    """Supported Kroger cart fulfillment modalities."""
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


@dataclass
class Product:
    """Represents a product from the Kroger catalog."""
    upc: str
    product_id: str
    description: str
    brand: Optional[str] = None
    size: Optional[str] = None
    price: Optional[float] = None
    categories: Optional[list] = None


@dataclass
class ProductItemDetail:
    """Represents store/location-specific product item details."""
    item_id: Optional[str] = None
    size: Optional[str] = None
    sold_by: Optional[str] = None
    price: Optional[dict] = None
    fulfillment: Optional[dict] = None
    inventory: Optional[dict] = None


@dataclass
class ProductDetail:
    """Represents a detailed product response from the Kroger catalog."""
    upc: str
    product_id: str
    description: str
    brand: Optional[str] = None
    categories: Optional[list] = None
    items: Optional[list[ProductItemDetail]] = None
    images: Optional[list] = None
    aisle_locations: Optional[list] = None
    temperature: Optional[dict] = None
    nutrition: Optional[dict] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class LocationAddress:
    """Represents a Kroger location address."""
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class GeoLocation:
    """Represents a Kroger location geolocation."""
    lat_lng: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class LocationDepartment:
    """Represents a department available at a specific location."""
    department_id: str
    name: str
    phone: Optional[str] = None
    hours: Optional[dict] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class Location:
    """Represents a Kroger store location."""
    location_id: str
    name: Optional[str] = None
    chain: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[LocationAddress] = None
    geolocation: Optional[GeoLocation] = None
    departments: Optional[list[LocationDepartment]] = None
    hours: Optional[dict] = None
    store_number: Optional[str] = None
    division_number: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class Chain:
    """Represents a Kroger-owned chain."""
    name: str
    division_numbers: Optional[list[str]] = None
    domain: Optional[str] = None
    friendly_banner_name: Optional[str] = None
    default_title: Optional[str] = None
    title_extension: Optional[str] = None
    apple_app_id: Optional[str] = None
    google_app_id: Optional[str] = None
    theme_color: Optional[str] = None
    description: Optional[str] = None
    modality_capabilities: Optional[dict] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class Department:
    """Represents a Kroger department."""
    department_id: str
    name: str
    raw: Optional[dict[str, Any]] = None


@dataclass
class CartItem:
    """Represents an item in the user's cart."""
    upc: str
    quantity: int
    modality: CartModality = CartModality.PICKUP


@dataclass
class TokenSet:
    """Represents OAuth tokens with expiry information."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 1800
    expires_at: Optional[float] = None
    scope: Optional[str] = None