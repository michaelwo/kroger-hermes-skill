from dataclasses import dataclass
from typing import Optional, Any


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
class CartItem:
    """Represents an item in the user's cart."""
    upc: str
    quantity: int
    modality: str = "PICKUP"


@dataclass
class TokenSet:
    """Represents OAuth tokens with expiry information."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int = 1800
    expires_at: Optional[float] = None
    scope: Optional[str] = None