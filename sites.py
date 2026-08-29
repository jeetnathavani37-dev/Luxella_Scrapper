"""
Har site ka scraping config yahan hai.
Teen type ke sites: ScraperAPI-based (Akamai-protected, jaise MK/Coach),
browser-based (agar future mein koi aur JS-heavy site add ho), aur
shopify-based (halka, koi browser/proxy nahi chahiye).

NOTE (2026-08-29): MK/Coach ke liye Playwright, patchright, proxy (with/
without country) - sab try kiya, Akamai har baar 403 de raha tha (IP
nahi, browser-automation fingerprint hi Akamai detect kar raha tha).
Isliye ab ye dono ScraperAPI (managed anti-bot service) use karte hain
- "use_scraperapi": True, tile/name/price/link selectors CSS syntax mein
hi hain (BeautifulSoup se parse hote hain, Playwright locators se nahi).
Requires GitHub Secret: SCRAPERAPI_KEY

Coach confirmed working (16 products, 2026-08-29). MK ka purana URL
(/_/N-28ei) ScraperAPI se 404 de raha tha - simpler category URL pe
switch kar diya.

stockx_test / goat_test: exploratory entries - StockX PerimeterX+Cloudflare
use karta hai (Akamai se bhi tough maana jata hai), selectors abhi guess
hain (dono Next.js apps, hashed class names). Pehle dekhna hai ScraperAPI
fetch hi kar pata hai ya nahi, phir selectors tune karenge.
"""

SITES = [
    # ScraperAPI required (Akamai-protected, DIY browser automation block ho jata tha)
    {
        "name": "michaelkors",
        "start_urls": ["https://www.michaelkors.com/women/handbags/"],
        "use_scraperapi": True,
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "currency": "USD",
    },
    {
        "name": "coach",
        "start_urls": ["https://www.coach.com/shop/women/bestsellers"],
        "use_scraperapi": True,
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "currency": "USD",
    },
    # TEST ENTRIES - StockX/GOAT selectors unknown yet, isliye pehle sirf
    # fetch-success (blocked hota hai ya nahi) test karna hai
    {
        "name": "stockx_test",
        "start_urls": ["https://stockx.com/sneakers"],
        "use_scraperapi": True,
        "tile_selector": "[class*='tile'], [class*='product'], [data-testid*='product']",
        "name_selector": "[class*='name'], [class*='title']",
        "price_selector": "[class*='price']",
        "link_selector": "a[href]",
        "currency": "USD",
    },
    {
        "name": "goat_test",
        "start_urls": ["https://www.goat.com/sneakers"],
        "use_scraperapi": True,
        "tile_selector": "[class*='tile'], [class*='product'], [data-testid*='product']",
        "name_selector": "[class*='name'], [class*='title']",
        "price_selector": "[class*='price']",
        "link_selector": "a[href]",
        "currency": "USD",
    },

    # Handbags & Leather Goods
    {"name": "karllagerfeld", "platform": "shopify", "domain": "https://www.karllagerfeldparis.com", "category": "clothing", "currency": "USD"},
    {"name": "polene", "platform": "shopify", "domain": "https://uk.polene-paris.com", "category": "handbags", "currency": "GBP"},
    {"name": "jwpei", "platform": "shopify", "domain": "https://www.jwpei.com", "category": "handbags", "currency": "USD"},
    {"name": "mansurgavriel", "platform": "shopify", "domain": "https://www.mansurgavriel.com", "category": "handbags", "currency": "USD"},
    {"name": "strathberry", "platform": "shopify", "domain": "https://www.strathberry.com", "category": "handbags", "currency": "USD"},
    {"name": "staud", "platform": "shopify", "domain": "https://staud.clothing", "category": "handbags", "currency": "USD"},
    {"name": "demellier", "platform": "shopify", "domain": "https://www.demellierlondon.com", "category": "handbags", "currency": "USD"},
    {"name": "cultgaia", "platform": "shopify", "domain": "https://cultgaia.com", "category": "handbags", "currency": "USD"},
    {"name": "wandler", "platform": "shopify", "domain": "https://www.wandler.com", "category": "handbags", "currency": "USD"},
    {"name": "telfar", "platform": "shopify", "domain": "https://telfar.net", "category": "handbags", "currency": "USD"},
    {"name": "littleliffner", "platform": "shopify", "domain": "https://www.liffner.co", "category": "handbags", "currency": "USD"},
    {"name": "simonmiller", "platform": "shopify", "domain": "https://www.simonmillerusa.com", "category": "handbags", "currency": "USD"},
    {"name": "yuzefi", "platform": "shopify", "domain": "https://www.yuzefi.com", "category": "handbags", "currency": "USD"},
    {"name": "buildingblock", "platform": "shopify", "domain": "https://building--block.com", "category": "handbags", "currency": "USD"},
    {"name": "hobobags", "platform": "shopify", "domain": "https://www.hobobags.com", "category": "handbags", "currency": "USD"},
    {"name": "verabradley", "platform": "shopify", "domain": "https://www.verabradley.com", "category": "handbags", "currency": "USD"},
    {"name": "aimeekestenberg", "platform": "shopify", "domain": "https://www.aimeekestenberg.com", "category": "handbags", "currency": "USD"},
    {"name": "francesvalentine", "platform": "shopify", "domain": "https://francesvalentine.com", "category": "handbags", "currency": "USD"},
    {"name": "carmensol", "platform": "shopify", "domain": "https://carmensol.com", "category": "handbags", "currency": "USD"},
    {"name": "songmont", "platform": "shopify", "domain": "https://songmontofficial.com", "category": "handbags", "currency": "USD"},
    {"name": "cambridgesatchel", "platform": "shopify", "domain": "https://us.cambridgesatchel.com", "category": "handbags", "currency": "USD"},
    {"name": "luxlair", "platform": "shopify", "domain": "https://www.luxlair.com", "category": "handbags", "currency": "USD"},

    # Shoes
    {"name": "nodaleto", "platform": "shopify", "domain": "https://www.nodaleto.com", "category": "shoes", "currency": "USD"},
    {"name": "loefflerrandall", "platform": "shopify", "domain": "https://loefflerrandall.com", "category": "shoes", "currency": "USD"},
    {"name": "kicksmachine", "platform": "shopify", "domain": "https://www.kicksmachine.com", "category": "shoes", "currency": "INR"},
    {"name": "stevemadden", "platform": "shopify", "domain": "https://www.stevemadden.com", "category": "shoes", "currency": "USD"},
    {"name": "frye", "platform": "shopify", "domain": "https://www.thefryecompany.com", "category": "shoes", "currency": "USD"},
    {"name": "vincecamuto", "platform": "shopify", "domain": "https://www.vincecamuto.com", "category": "shoes", "currency": "USD"},
    {"name": "ninashoes", "platform": "shopify", "domain": "https://ninashoes.com", "category": "shoes", "currency": "USD"},

    # Sunglasses
    {"name": "lespecs", "platform": "shopify", "domain": "https://www.lespecs.com", "category": "sunglasses", "currency": "USD"},
    {"name": "krewe", "platform": "shopify", "domain": "https://kreweeyewear.com", "category": "sunglasses", "currency": "USD"},
    {"name": "jins", "platform": "shopify", "domain": "https://us.jins.com", "category": "sunglasses", "currency": "USD"},

    # Jewelry & Accessories
    {"name": "eliou", "platform": "shopify", "domain": "https://www.eliou.com", "category": "jewelry", "currency": "USD"},
    {"name": "emijay", "platform": "shopify", "domain": "https://www.emijay.com", "category": "jewelry", "currency": "USD"},
    {"name": "ericjavits", "platform": "shopify", "domain": "https://ericjavits.com", "category": "accessories", "currency": "USD"},
    {"name": "echonewyork", "platform": "shopify", "domain": "https://echonewyork.com", "category": "accessories", "currency": "USD"},
    {"name": "newera", "platform": "shopify", "domain": "https://www.neweracap.com", "category": "accessories", "currency": "USD"},

    # Clothing / Activewear
    {"name": "aloyoga", "platform": "shopify", "domain": "https://www.aloyoga.com", "category": "activewear", "currency": "USD"},
    {"name": "gymshark", "platform": "shopify", "domain": "https://www.gymshark.com", "category": "activewear", "currency": "USD"},
    {"name": "youngla", "platform": "shopify", "domain": "https://www.youngla.com", "category": "activewear", "currency": "USD"},
    {"name": "tedbaker", "platform": "shopify", "domain": "https://www.tedbaker.com", "category": "clothing", "currency": "USD"},
    {"name": "rejinapyo", "platform": "shopify", "domain": "https://www.rejinapyo.com", "category": "clothing", "currency": "USD"},
    {"name": "supreme", "platform": "shopify", "domain": "https://us.supreme.com", "category": "clothing", "currency": "USD"},
    {"name": "betseyjohnson", "platform": "shopify", "domain": "https://betseyjohnson.com", "category": "clothing", "currency": "USD"},
    {"name": "milly", "platform": "shopify", "domain": "https://www.milly.com", "category": "clothing", "currency": "USD"},
    {"name": "boden", "platform": "shopify", "domain": "https://us.boden.com", "category": "clothing", "currency": "USD"},
    {"name": "pjsalvage", "platform": "shopify", "domain": "https://www.pjsalvage.com", "category": "apparel", "currency": "USD"},
    {"name": "hampdenclothing", "platform": "shopify", "domain": "https://hampdenclothing.com", "category": "clothing", "currency": "USD"},

    # Drinkware / Travel / Luggage
    {"name": "stanley1913", "platform": "shopify", "domain": "https://www.stanley1913.com", "category": "drinkware", "currency": "USD"},
    {"name": "solgaard", "platform": "shopify", "domain": "https://solgaard.co", "category": "luggage", "currency": "USD"},
    {"name": "calpak", "platform": "shopify", "domain": "https://www.calpaktravel.com", "category": "luggage", "currency": "USD"},
    {"name": "delsey", "platform": "shopify", "domain": "https://us.delsey.com", "category": "luggage", "currency": "USD"},
    {"name": "lipault", "platform": "shopify", "domain": "https://www.lipault-usa.com", "category": "luggage", "currency": "USD"},
]
