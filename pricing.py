"""
USD/GBP price ko INR me convert karta hai, product ke naam/category se
weight nikalta hai (isliye landed cost sahi bante hai), aur 25% margin
laga ke selling price deta hai.
"""

CURRENCY_TO_INR = {
    "USD": 95.5,
    "GBP": 129.0,
}
SHIPPING_PER_KG = 1250
MARGIN = 0.25

CATEGORY_WEIGHTS = {
    "shoes": 2.0,
    "footwear": 2.0,
    "clothing": 0.5,
    "apparel": 0.5,
    "activewear": 0.5,
    "watches": 0.3,
    "sunglasses": 0.2,
    "drinkware": 1.0,
    "uncategorized": 0.5,
}
DEFAULT_WEIGHT_KG = 0.5
DEFAULT_HANDBAG_WEIGHT_KG = 0.6

HANDBAG_SUBTYPE_WEIGHTS = [
    (["tote"], 2.0),
    (["crossbody", "cross body", "cross-body"], 1.0),
    (["wallet", "card holder", "cardholder", "card case"], 0.5),
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


def calculate_pricing(price, category, currency="USD", name=None):
    if price is None:
        return {"price_inr": None, "landed_cost_inr": None, "selling_price_inr": None}

    rate = CURRENCY_TO_INR.get(currency, CURRENCY_TO_INR["USD"])
    weight_kg = get_weight(category, name)

    price_inr = round(price * rate, 2)
    landed_cost_inr = round((price * rate) + (weight_kg * SHIPPING_PER_KG), 2)
    selling_price_inr = round(landed_cost_inr * (1 + MARGIN), 2)

    return {
        "price_inr": price_inr,
        "landed_cost_inr": landed_cost_inr,
        "selling_price_inr": selling_price_inr,
    }
