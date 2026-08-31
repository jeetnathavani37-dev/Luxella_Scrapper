"""
USD/GBP price ko INR me convert karta hai, product ke naam/category se
weight nikalta hai (isliye landed cost sahi bante hai), aur 25% margin
laga ke selling price deta hai.

NOTE (2026-08-30): selling_price_inr ab hamesha "...99" pe round hota
hai (jaise 7872.12 -> 7899, 24900.50 -> 24999) - psychological/retail
pricing standard. Formula: ceil(price/100)*100 - 1.

NOTE (2026-08-30) #2: compare_at_price_inr - Shopify pe crossed-out
"MRP"/anchor price (jaise ~~15000~~ 9699). India mein "MRP" term
technically packaged-goods specific hai (Legal Metrology Act) - isliye
Shopify ka "Compare at price" use kiya hai (same visual effect, bina
literal MRP claim ke).

NOTE (2026-08-30) #3: Formula change - pehle compare_at ek fixed higher
margin (45%) pe based tha, jisse sirf ~14% "off" dikhta tha (bohot kam,
retail standard se neeche). Ab MIN_DISCOUNT_PERCENT (35%) se seedha
compute hota hai: compare_at = selling_price / (1 - 0.35). Isse HAR
product ka discount display kam se kam ~35% guarantee hota hai
(rounding ki wajah se thoda zyada bhi dikh sakta hai, kabhi kam nahi).
"""
import math

CURRENCY_TO_INR = {
    "USD": 95.5,
    "GBP": 129.0,
}
SHIPPING_PER_KG = 1250
MARGIN = 0.25
MIN_DISCOUNT_PERCENT = 0.35  # har product pe kam se kam itna "% off" dikhna chahiye

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


def calculate_compare_at_price(selling_price_inr):
    """selling_price se MRP/compare-at calculate karta hai, taaki kam se
    kam MIN_DISCOUNT_PERCENT (35%) off dikhe. Formula: compare_at =
    selling / (1 - 0.35). Rounding ki wajah se actual % off 35% se
    thoda zyada bhi ho sakta hai, kabhi kam nahi."""
    if selling_price_inr is None:
        return None
    raw_compare_at = selling_price_inr / (1 - MIN_DISCOUNT_PERCENT)
    return round_to_99(raw_compare_at)


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

    compare_at_price_inr = calculate_compare_at_price(selling_price_inr)

    return {
        "price_inr": price_inr,
        "landed_cost_inr": landed_cost_inr,
        "selling_price_inr": selling_price_inr,
        "compare_at_price_inr": compare_at_price_inr,
    }
