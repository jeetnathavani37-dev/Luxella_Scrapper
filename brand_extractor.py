"""
brand_extractor.py

Marketplace sites (GOAT, StockX, Sephora, Kohl's, Gilt, Rue La La,
SecretSales, Zappos, Ulta) khud brand nahi hain - wo bohot saare
alag-alag brands bechte hain (jaise GOAT pe Supreme, Nike, Adidas sab
milte hain). Pehle humara code galti se site-name (jaise "goat") ko
hi "brand" field mein daal deta tha - is module ka kaam hai product
NAME se ASLI brand nikaalna.

Approach: known-brands list se match karta hai (case-insensitive,
product title ke shuru mein dhoondhta hai - retail listings usually
"BrandName Product Description" format follow karte hain).
"""
import re

# Sabse common streetwear/sneaker/luxury/beauty brands jo in
# marketplaces (GOAT, StockX, Sephora, Kohl's, Gilt, Rue La La,
# SecretSales, Zappos, Ulta) pe milte hain. Longer/more-specific
# names pehle check hote hain (jaise "Off-White" "White" se pehle).
KNOWN_BRANDS = [
    "Off-White", "Off White", "A Bathing Ape", "BAPE", "Fear of God Essentials",
    "Fear of God", "Essentials", "Travis Scott", "Kaws", "Palace",
    "Stone Island", "Comme des Garcons", "Comme Des Garcons",
    "Yeezy", "Jordan", "Air Jordan", "Nike", "Adidas", "New Balance",
    "Supreme", "Stussy", "Vans", "Converse", "Puma", "Reebok", "ASICS",
    "Salomon", "Crocs", "Birkenstock", "UGG", "Timberland", "Dr. Martens",
    "Balenciaga", "Gucci", "Louis Vuitton", "Dior", "Prada", "Chanel",
    "Burberry", "Versace", "Fendi", "Givenchy", "Valentino", "Celine",
    "Bottega Veneta", "Saint Laurent", "Moncler", "Canada Goose",
    "Rolex", "Cartier", "Omega", "Patek Philippe",
    "Coach", "Michael Kors", "Kate Spade", "Marc Jacobs", "Tory Burch",
    "Rare Beauty", "Fenty Beauty", "Fenty", "Charlotte Tilbury", "Drunk Elephant",
    "The Ordinary", "Tatcha", "Glow Recipe", "Summer Fridays", "Youth To The People",
    "Estee Lauder", "Clinique", "Lancome", "MAC", "NARS", "Urban Decay",
    "Too Faced", "Benefit", "Tarte", "IT Cosmetics", "Origins",
    "Ralph Lauren", "Polo Ralph Lauren", "Calvin Klein", "Tommy Hilfiger",
    "Levi's", "Levis", "Champion", "Carhartt", "Patagonia", "The North Face",
    "Columbia", "Under Armour", "Lululemon",
]

# Sort by length descending, taaki "Off-White" "White" se pehle check ho
_SORTED_BRANDS = sorted(KNOWN_BRANDS, key=len, reverse=True)


def extract_brand(name, fallback=None):
    """Product name se known brand dhoondhta hai. Title ke shuru mein
    priority - warna kahin bhi match. Nahi mile toh fallback deta hai
    (default None - caller decide karega kya karna hai)."""
    if not name:
        return fallback

    name_lower = name.lower()

    # Pehle: title ke bilkul shuru mein match (sabse reliable)
    for brand in _SORTED_BRANDS:
        if name_lower.startswith(brand.lower() + " ") or name_lower == brand.lower():
            return brand

    # Doosra: kahin bhi title mein match (kam reliable, but better than nothing)
    for brand in _SORTED_BRANDS:
        pattern = r"\b" + re.escape(brand.lower()) + r"\b"
        if re.search(pattern, name_lower):
            return brand

    return fallback
