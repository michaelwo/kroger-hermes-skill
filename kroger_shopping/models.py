from dataclasses import dataclass
from typing import Optional


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