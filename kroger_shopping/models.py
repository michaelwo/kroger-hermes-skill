from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class ProductFulfillment(str, Enum):
    """Supported Kroger product search fulfillment filters."""
    AIS = "ais"
    CSP = "csp"
    DTH = "dth"
    STH = "sth"


class CartModality(str, Enum):
    """Supported Kroger cart fulfillment modalities."""
    DELIVERY = "DELIVERY"
    PICKUP = "PICKUP"


@dataclass
class ProductItemFulfillment:
    """Represents item fulfillment availability returned by Kroger."""
    curbside: Optional[bool] = None
    delivery: Optional[bool] = None
    instore: Optional[bool] = None
    shiptohome: Optional[bool] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProductItemInventory:
    """Represents item inventory returned by Kroger."""
    stock_level: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProductNutrient:
    """Represents a nutrient entry from Kroger nutrition information."""
    code: Optional[str] = None
    description: Optional[str] = None
    display_name: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[dict] = None
    percent_daily_intake: Optional[float] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProductNutritionInformation:
    """Represents Kroger nutrition information for a product."""
    ingredient_statement: Optional[str] = None
    serving_size: Optional[dict] = None
    nutrients: Optional[list[ProductNutrient]] = None
    nutritional_rating: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


@dataclass
class ProductAllergen:
    """Represents an allergen declaration returned by Kroger."""
    name: Optional[str] = None
    level_of_containment_name: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


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
    national_price: Optional[dict] = None
    favorite: Optional[bool] = None
    fulfillment: Optional[ProductItemFulfillment] = None
    inventory: Optional[ProductItemInventory] = None
    raw: Optional[dict[str, Any]] = None


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
    nutrition_information: Optional[list[ProductNutritionInformation]] = None
    allergens: Optional[list[ProductAllergen]] = None
    allergens_description: Optional[str] = None
    snap_eligible: Optional[bool] = None
    organic_claim_name: Optional[str] = None
    country_origin: Optional[str] = None
    warnings: Optional[str] = None
    restrictions: Optional[dict] = None
    raw: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class IngredientPreferenceRule:
    """Keyword rule for screening product ingredient text."""
    keyword: str
    label: str
    penalty: float = 15.0


SIMPLE_TRUTH_UNWANTED_INGREDIENT_RULES = [
    IngredientPreferenceRule('acesulfame k', 'Acesulfame-K (acesulfame potassium)'),
    IngredientPreferenceRule('acesulfame potassium', 'Acesulfame-K (acesulfame potassium)'),
    IngredientPreferenceRule('acetylated ester of mono and diglycerides', 'Acetylated ester of mono- and diglycerides'),
    IngredientPreferenceRule('ammonium chloride', 'Ammonium chloride'),
    IngredientPreferenceRule('artificial colors', 'Artificial colors'),
    IngredientPreferenceRule('synthetic colors', 'Artificial colors'),
    IngredientPreferenceRule('fd c', 'Artificial colors'),
    IngredientPreferenceRule('red 40', 'Artificial colors'),
    IngredientPreferenceRule('yellow 5', 'Artificial colors'),
    IngredientPreferenceRule('yellow 6', 'Artificial colors'),
    IngredientPreferenceRule('blue 1', 'Artificial colors'),
    IngredientPreferenceRule('artificial flavors', 'Artificial flavors'),
    IngredientPreferenceRule('aspartame', 'Aspartame'),
    IngredientPreferenceRule('astaxanthin', 'Astaxanthin'),
    IngredientPreferenceRule('azodicarbonamide', 'Azodicarbonamide'),
    IngredientPreferenceRule('bentonite', 'Bentonite'),
    IngredientPreferenceRule('benzoates', 'Benzoates in food'),
    IngredientPreferenceRule('benzyl alcohol', 'Benzyl Alcohol'),
    IngredientPreferenceRule('benzoyl peroxide', 'Benzoyl peroxide'),
    IngredientPreferenceRule('bha', 'BHA (butylated hydroxyanisole)'),
    IngredientPreferenceRule('butylated hydroxyanisole', 'BHA (butylated hydroxyanisole)'),
    IngredientPreferenceRule('bht', 'BHT (butylated hydroxytoluene)'),
    IngredientPreferenceRule('butylated hydroxytoluene', 'BHT (butylated hydroxytoluene)'),
    IngredientPreferenceRule('bisulfite', 'Bisulfites'),
    IngredientPreferenceRule('bisulfites', 'Bisulfites'),
    IngredientPreferenceRule('bleached flour', 'Bleached flour'),
    IngredientPreferenceRule('bromated flour', 'Bromated flour'),
    IngredientPreferenceRule('brominated vegetable oil', 'Brominated vegetable oil (BVO)'),
    IngredientPreferenceRule('bvo', 'Brominated vegetable oil (BVO)'),
    IngredientPreferenceRule('calcium bromate', 'Calcium bromate'),
    IngredientPreferenceRule('calcium disodium edta', 'Calcium disodium EDTA'),
    IngredientPreferenceRule('calcium peroxide', 'Calcium peroxide'),
    IngredientPreferenceRule('calcium propionate', 'Calcium propionate'),
    IngredientPreferenceRule('calcium stearoyl 2 lactylate', 'Calcium stearoyl-2-lactylate'),
    IngredientPreferenceRule('calcium sorbate', 'Calcium sorbate'),
    IngredientPreferenceRule('cap rocaprylobehenin', 'Cap rocaprylobehenin'),
    IngredientPreferenceRule('carmine', 'Carmine'),
    IngredientPreferenceRule('certified colors', 'Certified colors'),
    IngredientPreferenceRule('cochineal', 'Cochineal'),
    IngredientPreferenceRule('cyclamates', 'Cyclamates'),
    IngredientPreferenceRule('cystine', 'Cystine (L-cysteine)'),
    IngredientPreferenceRule('l cysteine', 'Cystine (L-cysteine)'),
    IngredientPreferenceRule('datem', 'DATEM'),
    IngredientPreferenceRule('diacetyl tartaric', 'DATEM'),
    IngredientPreferenceRule('diglycerides', 'Diglycerides'),
    IngredientPreferenceRule('dimethylpolysiloxane', 'Dimethylpolysiloxane'),
    IngredientPreferenceRule('dioctyl sodium sulfosuccinate', 'Dioctyl sodium sulfosuccinate (DSS)'),
    IngredientPreferenceRule('dss', 'Dioctyl sodium sulfosuccinate (DSS)'),
    IngredientPreferenceRule('disodium calcium edta', 'Disodium calcium EDTA'),
    IngredientPreferenceRule('disodium dihydrogen edta', 'Disodium dihydrogen EDTA'),
    IngredientPreferenceRule('disodium guanylate', 'Disodium guanylate (GMP)'),
    IngredientPreferenceRule('gmp', 'Disodium guanylate (GMP)'),
    IngredientPreferenceRule('disodium succinate', 'Disodium succinate'),
    IngredientPreferenceRule('dimethylamylamine', 'Dimethylamylamine (DMAA)'),
    IngredientPreferenceRule('dmaa', 'Dimethylamylamine (DMAA)'),
    IngredientPreferenceRule('edta', 'EDTA'),
    IngredientPreferenceRule('erythorbic acid', 'Erythorbic acid'),
    IngredientPreferenceRule('estergums', 'Estergums'),
    IngredientPreferenceRule('ester gums', 'Estergums'),
    IngredientPreferenceRule('ethanol', 'Ethanol'),
    IngredientPreferenceRule('ethyl alcohol', 'Ethanol'),
    IngredientPreferenceRule('ethyl vanillin', 'Ethyl vanillin'),
    IngredientPreferenceRule('ethylene oxide', 'Ethylene oxide'),
    IngredientPreferenceRule('ethoxyquin', 'Ethoxyquin'),
    IngredientPreferenceRule('ethyoxyquin', 'Ethoxyquin'),
    IngredientPreferenceRule('fd c colors', 'FD&C colors'),
    IngredientPreferenceRule('food dye', 'FD&C colors'),
    IngredientPreferenceRule('glycerol ester of wood rosin', 'Glycerol ester of wood rosin'),
    IngredientPreferenceRule('hexa esters of sucrose', 'Hexa-, hepta- and octa-esters of sucrose'),
    IngredientPreferenceRule('hepta esters of sucrose', 'Hexa-, hepta- and octa-esters of sucrose'),
    IngredientPreferenceRule('octa esters of sucrose', 'Hexa-, hepta- and octa-esters of sucrose'),
    IngredientPreferenceRule('high fructose corn syrup', 'High-fructose corn syrup'),
    IngredientPreferenceRule('hydrogenated', 'Hydrogenated/partially hydrogenated fats & oils'),
    IngredientPreferenceRule('partially hydrogenated', 'Hydrogenated/partially hydrogenated fats & oils'),
    IngredientPreferenceRule('hydroxypropyl guar gum', 'Hydroxypropyl guar gum'),
    IngredientPreferenceRule('hydroxpropyl guar gum', 'Hydroxypropyl guar gum'),
    IngredientPreferenceRule('methylene chloride', 'Methylene chloride'),
    IngredientPreferenceRule('methyl silicon', 'Methyl silicon'),
    IngredientPreferenceRule('monoglycerides', 'Monoglycerides'),
    IngredientPreferenceRule('monosodium glutamate', 'Monosodium glutamate (MSG)'),
    IngredientPreferenceRule('msg', 'Monosodium glutamate (MSG)'),
    IngredientPreferenceRule('neotame', 'Neotame'),
    IngredientPreferenceRule('nitrate', 'Nitrates/nitrites'),
    IngredientPreferenceRule('nitrates', 'Nitrates/nitrites'),
    IngredientPreferenceRule('nitrite', 'Nitrates/nitrites'),
    IngredientPreferenceRule('nitrites', 'Nitrates/nitrites'),
    IngredientPreferenceRule('oxystearin', 'Oxystearin'),
    IngredientPreferenceRule('parabens', 'Parabens'),
    IngredientPreferenceRule('partially hydrogenated oil', 'Partially hydrogenated oil'),
    IngredientPreferenceRule('polydextrose', 'Polydextrose'),
    IngredientPreferenceRule('potassium benzoate', 'Potassium benzoate'),
    IngredientPreferenceRule('potassium bisulfate', 'Potassium bisulfate'),
    IngredientPreferenceRule('potassium bromate', 'Potassium bromate'),
    IngredientPreferenceRule('potassium hydroxide', 'Potassium hydroxide'),
    IngredientPreferenceRule('potassium metabisulfite', 'Potassium metabisulfite'),
    IngredientPreferenceRule('potassium nitrate', 'Potassium nitrate or nitrite'),
    IngredientPreferenceRule('potassium nitrite', 'Potassium nitrate or nitrite'),
    IngredientPreferenceRule('potassium sorbate', 'Potassium sorbate'),
    IngredientPreferenceRule('propionate', 'Propionates'),
    IngredientPreferenceRule('propionates', 'Propionates'),
    IngredientPreferenceRule('propyl gallate', 'Propyl gallate'),
    IngredientPreferenceRule('propylene oxide', 'Propylene oxide'),
    IngredientPreferenceRule('propylparaben', 'Propylparaben'),
    IngredientPreferenceRule('saccharin', 'Saccharin'),
    IngredientPreferenceRule('simplesse', 'Simplesse'),
    IngredientPreferenceRule('sodium aluminum phosphate', 'Sodium aluminum phosphate'),
    IngredientPreferenceRule('sodium aluminum sulfate', 'Sodium aluminum sulfate'),
    IngredientPreferenceRule('sodium benzoate', 'Sodium benzoate'),
    IngredientPreferenceRule('sodium bisulfate', 'Sodium bisulfate'),
    IngredientPreferenceRule('sodium diacetate', 'Sodium diacetate'),
    IngredientPreferenceRule('sodium ferrocyanide', 'Sodium ferrocyanide'),
    IngredientPreferenceRule('sodium ferrocycanide', 'Sodium ferrocyanide'),
    IngredientPreferenceRule('sodium glutamate', 'Sodium glutamate'),
    IngredientPreferenceRule('sodium metabisulfite', 'Sodium metabisulfite'),
    IngredientPreferenceRule('sodium nitrate', 'Sodium nitrate/nitrite'),
    IngredientPreferenceRule('sodium nitrite', 'Sodium nitrate/nitrite'),
    IngredientPreferenceRule('sodium propionate', 'Sodium propionate'),
    IngredientPreferenceRule('sodium sterol lactylate', 'Sodium sterol lactylate'),
    IngredientPreferenceRule('sodium steroyl 2 lactylate', 'Sodium steroyl-2-lactylate'),
    IngredientPreferenceRule('sodium sulfite', 'Sodium sulfite'),
    IngredientPreferenceRule('solvent extracted oils', 'Solvent extracted oils'),
    IngredientPreferenceRule('sorbic acid', 'Sorbic acid'),
    IngredientPreferenceRule('sucralose', 'Sucralose'),
    IngredientPreferenceRule('sucroglycerides', 'Sucroglycerides'),
    IngredientPreferenceRule('sucrose polyester', 'Sucrose polyester (Olestra, Olean)'),
    IngredientPreferenceRule('olestra', 'Sucrose polyester (Olestra, Olean)'),
    IngredientPreferenceRule('olean', 'Sucrose polyester (Olestra, Olean)'),
    IngredientPreferenceRule('sulfites', 'Sulfites'),
    IngredientPreferenceRule('sulfur dioxide', 'Sulfites'),
    IngredientPreferenceRule('tartrazine', 'Tartrazine'),
    IngredientPreferenceRule('tbhq', 'TBHQ (tertiary butylhydroquinone)'),
    IngredientPreferenceRule('tertiary butylhydroquinone', 'TBHQ (tertiary butylhydroquinone)'),
    IngredientPreferenceRule('tetrasodium edta', 'Tetrasodium EDTA'),
    IngredientPreferenceRule('trans fatty acids', 'Trans fatty acids'),
    IngredientPreferenceRule('vanillin', 'Vanillin, synthetic'),
    IngredientPreferenceRule('synthetic vanillin', 'Vanillin, synthetic')
]


@dataclass
class PreferenceProfile:
    """Weights and ingredient rules used to rank product recommendations."""
    simple_truth_bonus: float = 25.0
    kroger_rank_weight: float = 0.25
    nutrition_data_bonus: float = 3.0
    health_score_weight: float = 0.2
    ingredient_rules: list[IngredientPreferenceRule] = field(
        default_factory=lambda: list(SIMPLE_TRUTH_UNWANTED_INGREDIENT_RULES)
    )


@dataclass
class ProductPreferenceScore:
    """Preference score and explainability metadata for a product."""
    total: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inspected_fields: list[str] = field(default_factory=list)
    unwanted_ingredient_count: Optional[int] = None
    unwanted_ingredients: list[str] = field(default_factory=list)
    ingredient_match_details: list[dict[str, Any]] = field(default_factory=list)


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