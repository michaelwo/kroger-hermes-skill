from typing import Any, Optional

from .models import (
    Chain,
    Department,
    GeoLocation,
    Location,
    LocationAddress,
    LocationDepartment,
    Product,
    ProductAllergen,
    ProductDetail,
    ProductItemDetail,
    ProductItemFulfillment,
    ProductItemInventory,
    ProductNutrient,
    ProductNutritionInformation,
)


def product_from_response(item: dict) -> Product:
    product_items = item.get("items") or []
    first_item = product_items[0] if product_items else {}
    return Product(
        upc=item.get("upc", ""),
        product_id=item.get("productId", ""),
        description=item.get("description", ""),
        brand=item.get("brand"),
        size=first_item.get("size"),
        price=first_item.get("price", {}).get("regular"),
        categories=item.get("categories"),
    )


def product_detail_from_response(item: dict) -> ProductDetail:
    product_items = item.get("items") or []
    return ProductDetail(
        upc=item.get("upc", ""),
        product_id=item.get("productId", ""),
        description=item.get("description", ""),
        brand=item.get("brand"),
        categories=item.get("categories"),
        items=[product_item_detail_from_response(product_item) for product_item in product_items],
        images=item.get("images"),
        aisle_locations=item.get("aisleLocations"),
        temperature=item.get("temperature"),
        nutrition_information=nutrition_information_from_response(
            item.get("nutritionInformation") or item.get("nutrition")
        ),
        allergens=allergens_from_response(item.get("allergens")),
        allergens_description=item.get("allergensDescription"),
        snap_eligible=item.get("snapEligible"),
        organic_claim_name=item.get("organicClaimName"),
        country_origin=item.get("countryOrigin"),
        warnings=item.get("warnings"),
        restrictions=item.get("restrictions") or item.get("retstrictions"),
        raw=item,
    )


def product_item_detail_from_response(item: dict) -> ProductItemDetail:
    return ProductItemDetail(
        item_id=item.get("itemId"),
        size=item.get("size"),
        sold_by=item.get("soldBy"),
        price=item.get("price"),
        national_price=item.get("nationalPrice"),
        favorite=item.get("favorite"),
        fulfillment=item_fulfillment_from_response(item.get("fulfillment")),
        inventory=item_inventory_from_response(item.get("inventory")),
        raw=item,
    )


def item_fulfillment_from_response(fulfillment: Optional[dict]) -> Optional[ProductItemFulfillment]:
    if not isinstance(fulfillment, dict):
        return None
    return ProductItemFulfillment(
        curbside=fulfillment.get("curbside"),
        delivery=fulfillment.get("delivery"),
        instore=fulfillment.get("instore"),
        shiptohome=fulfillment.get("shiptohome"),
        raw=fulfillment,
    )


def item_inventory_from_response(inventory: Optional[dict]) -> Optional[ProductItemInventory]:
    if not isinstance(inventory, dict):
        return None
    return ProductItemInventory(stock_level=inventory.get("stockLevel"), raw=inventory)


def nutrition_information_from_response(nutrition: Any) -> Optional[list[ProductNutritionInformation]]:
    if not nutrition:
        return None
    values = nutrition if isinstance(nutrition, list) else [nutrition]
    parsed = []
    for item in values:
        if not isinstance(item, dict):
            continue
        nutrients = []
        for nutrient in item.get("nutrients") or []:
            if isinstance(nutrient, dict):
                nutrients.append(
                    ProductNutrient(
                        code=nutrient.get("code"),
                        description=nutrient.get("description"),
                        display_name=nutrient.get("displayName"),
                        quantity=nutrient.get("quantity"),
                        unit_of_measure=nutrient.get("unitOfMeasure"),
                        percent_daily_intake=nutrient.get("percentDailyIntake"),
                        raw=nutrient,
                    )
                )
        parsed.append(
            ProductNutritionInformation(
                ingredient_statement=item.get("ingredientStatement"),
                serving_size=item.get("servingSize"),
                nutrients=nutrients or None,
                nutritional_rating=item.get("nutritionalRating"),
                raw=item,
            )
        )
    return parsed or None


def allergens_from_response(allergens: Any) -> Optional[list[ProductAllergen]]:
    if not allergens:
        return None
    parsed = []
    for item in allergens if isinstance(allergens, list) else [allergens]:
        if isinstance(item, dict):
            parsed.append(
                ProductAllergen(
                    name=item.get("name"),
                    level_of_containment_name=item.get("levelOfContainmentName"),
                    raw=item,
                )
            )
    return parsed or None


def location_from_response(item: dict) -> Location:
    address = item.get("address") or {}
    geolocation = item.get("geolocation") or {}
    departments = item.get("departments") or []
    return Location(
        location_id=item.get("locationId", ""),
        name=item.get("name"),
        chain=item.get("chain"),
        phone=item.get("phone"),
        address=LocationAddress(
            address_line1=address.get("addressLine1"),
            address_line2=address.get("addressLine2"),
            city=address.get("city"),
            county=address.get("county"),
            state=address.get("state"),
            zip_code=address.get("zipCode"),
            raw=address,
        ) if address else None,
        geolocation=GeoLocation(
            lat_lng=geolocation.get("latLng"),
            latitude=geolocation.get("latitude"),
            longitude=geolocation.get("longitude"),
            raw=geolocation,
        ) if geolocation else None,
        departments=[
            LocationDepartment(
                department_id=department.get("departmentId", ""),
                name=department.get("name", ""),
                phone=department.get("phone"),
                hours=department.get("hours"),
                raw=department,
            )
            for department in departments
        ],
        hours=item.get("hours"),
        store_number=item.get("storeNumber"),
        division_number=item.get("divisionNumber"),
        raw=item,
    )


def chain_from_response(item: dict) -> Chain:
    return Chain(
        name=item.get("name", ""),
        division_numbers=item.get("divisionNumbers"),
        domain=item.get("domain"),
        friendly_banner_name=item.get("friendlyBannerName"),
        default_title=item.get("defaultTitle"),
        title_extension=item.get("titleExtension"),
        apple_app_id=item.get("appleAppId"),
        google_app_id=item.get("googleAppId"),
        theme_color=item.get("themeColor"),
        description=item.get("description"),
        modality_capabilities=item.get("modalityCapabilities"),
        raw=item,
    )


def department_from_response(item: dict) -> Department:
    return Department(
        department_id=item.get("departmentId", ""),
        name=item.get("name", ""),
        raw=item,
    )
