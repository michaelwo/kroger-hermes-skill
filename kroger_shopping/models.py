from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class IngredientPreferenceRule:
    """Keyword rule for screening product ingredient text."""
    keyword: str
    label: str
    penalty: float = 15.0


@dataclass
class PreferenceProfile:
    """Weights and ingredient rules used to rank product recommendations."""
    simple_truth_bonus: float = 25.0
    kroger_rank_weight: float = 0.25
    nutrition_data_bonus: float = 3.0
    health_score_weight: float = 0.2
    ingredient_rules: list[IngredientPreferenceRule] = field(
        default_factory=lambda: [
            IngredientPreferenceRule("high fructose corn syrup", "high-fructose corn syrup"),
            IngredientPreferenceRule("aspartame", "aspartame"),
            IngredientPreferenceRule("sucralose", "sucralose"),
            IngredientPreferenceRule("acesulfame", "acesulfame potassium"),
            IngredientPreferenceRule("red 40", "Red 40 dye"),
            IngredientPreferenceRule("yellow 5", "Yellow 5 dye"),
            IngredientPreferenceRule("yellow 6", "Yellow 6 dye"),
            IngredientPreferenceRule("blue 1", "Blue 1 dye"),
            IngredientPreferenceRule("sodium benzoate", "sodium benzoate"),
            IngredientPreferenceRule("potassium sorbate", "potassium sorbate"),
            IngredientPreferenceRule("bha", "BHA"),
            IngredientPreferenceRule("bht", "BHT"),
            IngredientPreferenceRule("tbhq", "TBHQ"),
            IngredientPreferenceRule("partially hydrogenated", "partially hydrogenated oil"),
            IngredientPreferenceRule("hydrogenated oil", "hydrogenated oil"),
        ]
    )


@dataclass
class ProductPreferenceScore:
    """Preference score and explainability metadata for a product."""
    total: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inspected_fields: list[str] = field(default_factory=list)


@dataclass
class RankedProduct:
    """A Kroger product ranked with local preference scoring."""
    product: Product
    detail: Optional[ProductDetail]
    preference_score: ProductPreferenceScore
    original_kroger_rank: int


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