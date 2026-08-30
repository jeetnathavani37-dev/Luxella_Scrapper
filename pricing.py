"""
USD/GBP price ko INR me convert karta hai, product ke naam/category se
weight nikalta hai (isliye landed cost sahi bante hai), aur 25% margin
laga ke selling price deta hai.

NOTE (2026-08-30): selling_price_inr ab hamesha "...99" pe round hota
hai (jaise 7872.12 -> 7899, 24900.50 -> 24999) - psychological/retail
pricing standard. Formula: ceil(price/100)*100 - 1.

NOTE (2026-08-30) #2: compare_at_price_inr add kiya - ye "MRP"/anchor
price hai jo Shopify pe crossed-out dikhta hai (jaise ~~15000~~ 9699,
"discount" ka feel dene ke liye). India mein "MRP" term technically
packaged-goods specific hai (Legal Metrology Act) - isliye Shopify ka
"Compare at price" use kiya hai (same visual effect, bina literal MRP
claim ke). Formula: higher margin (COMPARE_AT_MARGIN) pe based hai,
selling price se hamesha zyada hota hai, ...99 pe round.
"""
import math

CURRENCY_TO_INR = {
    "USD": 95.5,
    "GBP": 129.0,
}
SHIPPING_PER_KG = 1250
MARGIN = 0.25
COMPARE_AT_MARGIN = 0.45  # "anchor" price ke liye - selling price se zyada dikhta hai

CATEGORY_WEIGHTS = {
    "shoes": 2.0,
    "footwear": 2.0,
    "clothing": 0.5,
    "apparel": 0.5,
    "activewear": 0.5,
    "watches": 0.3,
    "sunglasses": 0.2,
    "drinkware": 1.0,
    "luggage": 4.0,
    "uncategorized": 0.5,
}
DEFAULT_WEIGHT_KG = 0.5
DEFAULT_HANDBAG_WEIGHT_KG = 0.8

HANDBAG_SUBTYPE_WEIGHTS = [
    (["tote"], 1.2),
    (["crossbody", "cross body", "cross-body"], 1.0),
    (["wallet", "card holder", "cardholder", "card case"], 0.8),
]

HANDBAG_CATEGORIES = {"handbags", "bags", "bag/accessory"}


def get_weight(category, name=None):
    category_l = (category or "").lower()
    name_l = (name or "").lower()

    if category_l in HANDBAG_CATEGORIES:
        for keywords, weight in HANDBAG_SUBTYPE_WEIGHTS:
            if any(kw in name_l for kw in keywords):
                return weight
        return DEFAULT_HANDBAG_WEIGHT_KG

    return CATEGORY_WEIGHTS.get(category_l, DEFAULT_WEIGHT_KG)


def round_to_99(value):
    """Psychological pricing - hamesha '...99' pe round karta hai.
    7872.12 -> 7899, 24900.50 -> 24999, 18900.00 -> 18899."""
    if value is None:
        return None
    return math.ceil(value / 100) * 100 - 1


def calculate_pricing(price, category, currency="USD", name=None):
    if price is None:
        return {
            "price_inr": None,
            "landed_cost_inr": None,
            "selling_price_inr": None,
            "compare_at_price_inr": None,
        }

    rate = CURRENCY_TO_INR.get(currency, CURRENCY_TO_INR["USD"])
    weight_kg = get_weight(category, name)

    price_inr = round(price * rate, 2)
    landed_cost_inr = round((price * rate) + (weight_kg * SHIPPING_PER_KG), 2)

    raw_selling_price = landed_cost_inr * (1 + MARGIN)
    selling_price_inr = round_to_99(raw_selling_price)

    raw_compare_at = landed_cost_inr * (1 + COMPARE_AT_MARGIN)
    compare_at_price_inr = round_to_99(raw_compare_at)

    return {
        "price_inr": price_inr,
        "landed_cost_inr": landed_cost_inr,
        "selling_price_inr": selling_price_inr,
        "compare_at_price_inr": compare_at_price_inr,
    }
