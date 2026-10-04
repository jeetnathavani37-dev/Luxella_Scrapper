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
    # 2026-10-04: kicksmachine/goat ke un-pehchaane products mein sabse aam
    "Golden Goose", "Gallery Dept", "Ted Baker", "Tom Ford", "Abercrombie & Fitch", "Abercrombie",
    "Pop Mart", "Gentle Monster", "Loewe", "Chrome Hearts", "Vale Forever", "Vivobarefoot",
    "Paco Rabanne", "Mulberry", "Pokémon",
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


# --- Display names (2026-10-04) -------------------------------------------
# Supabase `products.brand` mein aksar SITE ka slug hota hai (jaise
# "stevemadden", "kicksmachine") - customer-facing text mein ye galat
# dikhta hai ("by kicksmachine"). Single-brand sites ke slug -> asli naam:
BRAND_DISPLAY = {
    "aimeekestenberg": "Aimee Kestenberg", "aloyoga": "Alo Yoga", "adanola": "Adanola",
    "athleta": "Athleta", "beyondyoga": "Beyond Yoga", "cambridgesatchel": "The Cambridge Satchel Company",
    "carmensol": "Carmen Sol", "coach": "Coach", "cultgaia": "Cult Gaia", "demellier": "DeMellier",
    "francesvalentine": "Frances Valentine", "frye": "Frye", "furla": "Furla", "goodamerican": "Good American",
    "hobobags": "HOBO", "ilovedooney": "Dooney & Bourke", "jwpei": "JW PEI", "karllagerfeld": "Karl Lagerfeld",
    "landsend": "Lands' End", "littleliffner": "Little Liffner", "loefflerrandall": "Loeffler Randall",
    "lululemon": "lululemon", "mansurgavriel": "Mansur Gavriel", "marcjacobs": "Marc Jacobs",
    "michaelkors": "Michael Kors", "nagnata": "Nagnata", "ninashoes": "Nina", "nodaleto": "Nodaleto",
    "on": "On", "penation": "P.E Nation", "polene": "Polène", "ralphlauren": "Ralph Lauren",
    "simonmiller": "Simon Miller", "songmont": "Songmont", "splits59": "Splits59", "stanley1913": "Stanley",
    "staud": "STAUD", "stevemadden": "Steve Madden", "swoveralls": "Swoveralls", "toryburch": "Tory Burch",
    "varley": "Varley", "verabradley": "Vera Bradley", "victoriabeckham": "Victoria Beckham",
    "victoriabeckhambeauty": "Victoria Beckham Beauty", "vincecamuto": "Vince Camuto", "wandler": "Wandler",
    "yuzefi": "Yuzefi", "katespade": "Kate Spade", "adidas": "adidas",
}

# Multi-brand retailers/marketplaces: inka naam kabhi brand nahi hota.
# sites.py ke is_marketplace=True sites + jo sites.py se hat chuki hain
# par purane products abhi bhi unke slug ke saath DB mein hain.
EXTRA_MARKETPLACES = {"kicksmachine", "secretsales", "secret sales"}


def _marketplace_slugs():
    try:
        import sites
        site_list = getattr(sites, "SITES", None) or next(
            v for v in vars(sites).values() if isinstance(v, list) and v and isinstance(v[0], dict))
        return {s["name"].lower() for s in site_list if s.get("is_marketplace")} | EXTRA_MARKETPLACES
    except Exception:
        return set(EXTRA_MARKETPLACES)


_MARKETPLACES = None


def display_brand(brand, name=None):
    """Customer-facing brand naam. None lautata hai agar pakka pata nahi -
    tab caller brand ka naam likhe hi nahi (galat naam se behtar)."""
    global _MARKETPLACES
    if _MARKETPLACES is None:
        _MARKETPLACES = _marketplace_slugs()
    b = (brand or "").strip()
    if not b or b.lower() == "none":
        return extract_brand(name)
    if b.lower() in _MARKETPLACES:
        return extract_brand(name)            # marketplace: asli brand product name se
    if b.lower() in BRAND_DISPLAY:
        return BRAND_DISPLAY[b.lower()]
    if b != b.lower():                         # "Nike", "Fear of God" - pehle se sahi naam
        return b
    return None                                # anjaan lowercase slug - andaaza mat lagao
