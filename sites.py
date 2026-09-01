"""
Har site ka scraping config yahan hai.
Teen type ke sites: ScraperAPI-based (Akamai/PerimeterX-protected, jaise
MK/Coach/StockX/GOAT/On/Ulta/SecretSales/Zappos), browser-based (agar
future mein koi aur JS-heavy site add ho), aur shopify-based (halka,
koi browser/proxy nahi chahiye). Ab ScrapeGraphAI-based bhi (prompt-based
extraction, CSS selectors ki zaroorat nahi) - "use_scrapegraph": True.

NOTE (2026-08-29): MK/Coach ke liye Playwright, patchright, proxy (with/
without country) - sab try kiya, Akamai har baar 403 de raha tha (IP
nahi, browser-automation fingerprint hi Akamai detect kar raha tha).
Isliye ab ye ScraperAPI (managed anti-bot service) use karte hain -
"use_scraperapi": True, tile/name/price/link selectors CSS syntax mein
hi hain (BeautifulSoup se parse hote hain, Playwright locators se nahi).
Requires GitHub Secret: SCRAPERAPI_KEY

Coach confirmed working (16 products). MK ka purana URL (/_/N-28ei)
ScraperAPI se 404 de raha tha - simpler category URL pe switch kar diya.
StockX/GOAT bhi ScraperAPI se successfully fetch ho rahe hain (dono
PerimeterX+Cloudflare use karte hain, StockX Akamai se bhi tough maana
jata hai) - selectors actual HTML se reverse-engineer kiye.
On (on.com) apna custom React platform hai, JS-heavy - render=true
ke saath ScraperAPI se 18 products mile Cloud collection se.
Ulta confirmed working (60 products) - kabhi kabhi soft-block deta hai,
isliye scraperapi_scraper.py mein auto-retry add kiya. Sephora ScraperAPI
se abhi kaam nahi karta tha - "premium"/"ultra_premium" proxy tier
maangta hai jo current ScraperAPI trial plan mein nahi hai.
SecretSales UK confirmed working (18 products, discounted designer
goods - Coach, Gucci, Marc Jacobs). Gilt/Rue La La abhi kaam nahi
karte (premium proxy tier + login-gated content, dono issues).
Zappos confirmed working (108 products!) - JSON-LD structured data use
karta hai ("use_jsonld": True), CSS selectors ki zaroorat nahi. Kohl's
aur Hoka abhi kaam nahi karte (dono Akamai + premium proxy tier
chahiye - Hoka Deckers ka SFCC platform hai, MK/Coach jaisa).

NOTE (2026-08-30): ScrapeGraphAI batch test round 2 (fetch_config
mode=js, stealth=True, wait=2000) - Sephora WORKING (bot-detection
bypass hua) but sirf 3 products mile (LLM ne poori page scroll nahi ki,
sirf pehli screen ka content extract kiya). Kohl's - real content
mila (5287 chars) par LLM ko products samajh nahi aaye. Hoka(502)/
Gilt(404)/Rue La La(exception) - teeno ScrapeGraphAI backend ki
transient instability lagti hai ek hi run mein (gilt.com khud up hai,
verified) - retry-later cases, permanent block nahi.

Round 3: STEALTH_FETCH_CONFIG mein "scrolls": 5 add kiya (poori page
scroll karke saare lazy-loaded products load karne ke liye) +
scrapegraph_scraper.py ka default prompt explicit kiya "extract EVERY
product, be exhaustive" - Sephora ke count-issue ko fix karne ke liye.
Requires GitHub Secret: SCRAPEGRAPH_API_KEY

NOTE (2026-08-30) #2: MK/Coach/StockX/GOAT ab poori site cover karte
hain - pehle sirf 1 category thi (jaise MK sirf handbags), ab har site
ke start_urls mein multiple category pages hain (real URLs web-search
se verify kiye, taaki 404 na aaye jaisa MK ke purane URL ke saath hua
tha). Selectors same rakhe hain kyunki sab ek hi site platform ke
alag-alag category pages hain, tile/name/price structure same rehta
hai.

NOTE (2026-09-01): MK aur Coach sabse zyada bikte hain (user confirmed)
- isliye inke liye extra kaam kiya:
1. Categories aur badhaye - MK mein jewelry, wallets, watches,
   sunglasses add kiye (pehle sirf handbags/shoes/men's tha).
2. Multiple images ke liye alag script (scraperapi_detail_gallery.py)
   banaya - category-listing page se sirf 1 thumbnail milta hai,
   poori gallery ke liye har product ka individual detail page visit
   karna padta hai. Wo script CDN URL pattern-matching se robust
   tareeke se gallery nikaalta hai (assets.michaelkors.com ya
   coach.scene7.com pattern), fragile CSS selectors ki jagah.
3. Kate Spade Outlet add kiya - Coach ke hi parent company (Tapestry)
   ki hai, isliye same .product-tile selectors try kiye. NOTE: purana
   domain "surprise.katespade.com" tha, jo ab katespadeoutlet.com pe
   migrate ho chuka hai (site khud confirm karta hai: "Our Surprise
   deals are moving to katespadeoutlet.com") - user ne sahi domain
   bataya, isliye URL fix kiya.
4. SKIMS add kiya - confirmed Shopify platform pe hai (multiple sources
   se verify kiya), isliye halka shopify-platform scraper use hota hai,
   koi ScraperAPI/selectors ki zaroorat nahi.
5. Lululemon add kiya - shop.lululemon.com custom platform pe hai (NOT
   Shopify, verify kiya), isliye ScraperAPI use kiya. Selectors abhi
   BEST-GUESS hain (generic e-commerce class-name patterns, jaisa
   on.com ke liye kiya tha) - real HTML structure verify nahi kiya,
   test run ke baad scraperapi_scraper.py ka debug output
   (tile_selector match count) dekh ke adjust karna pad sakta hai.
6. Victoria Beckham (fashion + beauty, dono confirmed Shopify) aur
   Good American (Khloe Kardashian/Emma Grede, confirmed Shopify) add
   kiye - teeno halke shopify-platform scraper se, koi issue expected
   nahi.
"""

# ScrapeGraphAI ke liye - JS-rendering + stealth mode + scrolling,
# hard-to-scrape ya infinite-scroll/lazy-load sites ke liye.
STEALTH_FETCH_CONFIG = {"mode": "js", "stealth": True, "wait": 2000, "scrolls": 5}

SITES = [
    # ScraperAPI required (Akamai/PerimeterX-protected, DIY browser automation block ho jata tha)
    # MK/Coach best-sellers hain (2026-09-01) - poori site cover: handbags,
    # shoes, men's, jewelry, wallets, watches, sunglasses
    {
        "name": "michaelkors",
        "start_urls": [
            "https://www.michaelkors.com/women/handbags/",
            "https://www.michaelkors.com/women/shoes/",
            "https://www.michaelkors.com/men/",
            "https://www.michaelkors.com/women/jewelry/",
            "https://www.michaelkors.com/women/wallets/",
            "https://www.michaelkors.com/women/watches/",
            "https://www.michaelkors.com/women/sunglasses/",
        ],
        "use_scraperapi": True,
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "currency": "USD",
    },
    # Poori site cover: women (all), handbags-specific, men's, accessories
    {
        "name": "coach",
        "start_urls": [
            "https://www.coach.com/shop/women/view-all",
            "https://www.coach.com/shop/women/handbags/view-all",
            "https://www.coach.com/shop/men/view-all",
            "https://www.coach.com/shop/women/accessories/view-all",
        ],
        "use_scraperapi": True,
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "currency": "USD",
    },
    # Kate Spade Outlet (2026-09-01) - Coach ke parent company (Tapestry)
    # ki hai, isliye same selectors try kar rahe (SFCC platform pattern
    # jaisa MK/Coach). Domain: katespadeoutlet.com (purana
    # surprise.katespade.com wahan se migrate ho chuka hai).
    {
        "name": "katespade",
        "start_urls": [
            "https://www.katespadeoutlet.com/shop/view-all",
        ],
        "use_scraperapi": True,
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "currency": "USD",
    },
    # Lululemon (2026-09-01) - shop.lululemon.com custom platform hai
    # (Shopify nahi). Selectors best-guess hain - agar debug output mein
    # tile_selector match count 0 aaye, generic class patterns adjust
    # karne honge actual HTML dekh ke.
    {
        "name": "lululemon",
        "start_urls": [
            "https://shop.lululemon.com/c/women-bestsellers/n16o10znskl",
            "https://shop.lululemon.com/c/women-leggings/n1udsq",
            "https://shop.lululemon.com/c/bestsellers-accessories/n14w56znskl",
        ],
        "use_scraperapi": True,
        "tile_selector": '[class*="product-tile"], [class*="ProductTile"], [class*="product-card"]',
        "name_selector": '[class*="product-name"], [class*="ProductName"], [class*="title"]',
        "price_selector": '[class*="price"]',
        "link_selector": "a[href]",
        "currency": "USD",
    },
    # StockX/GOAT confirmed working via ScraperAPI (2026-08-29) - both are
    # PerimeterX/Cloudflare protected (StockX considered tougher than
    # Akamai), but ScraperAPI fetches clean, real HTML for both. Selectors
    # reverse-engineered from actual fetched HTML.
    # Poori site cover: sneakers, handbags, watches, streetwear, accessories
    {
        "name": "stockx",
        "start_urls": [
            "https://stockx.com/sneakers",
            "https://stockx.com/handbags",
            "https://stockx.com/watches",
            "https://stockx.com/streetwear",
            "https://stockx.com/category/accessories",
        ],
        "use_scraperapi": True,
        "tile_selector": '[data-testid="ProductTile"]',
        "name_selector": '[data-testid="product-tile-title"]',
        "price_selector": '[data-testid="product-tile-lowest-ask-amount"]',
        "link_selector": 'a[data-testid="productTile-ProductSwitcherLink"]',
        "currency": "USD",
    },
    # Poori site cover: sneakers, apparel, accessories, collectibles
    {
        "name": "goat",
        "start_urls": [
            "https://www.goat.com/sneakers",
            "https://www.goat.com/apparel",
            "https://www.goat.com/accessories",
            "https://www.goat.com/collectibles",
        ],
        "use_scraperapi": True,
        "tile_selector": '[class*="GridCellWrapper"]',
        "name_selector": '[class*="GridCellProductInfo__Name"]',
        "price_selector": '[class*="GridCellProductInfo__Price-"]',
        "link_selector": 'a[href^="/sneakers/"]',
        "currency": "USD",
    },
    {
        "name": "on",
        "start_urls": ["https://www.on.com/en-us/shop/mens/shoes/cloud"],
        "use_scraperapi": True,
        "tile_selector": '[class*="productCard"]',
        "name_selector": '[class*="_title_"]',
        "price_selector": '[class*="_price_"]',
        "link_selector": "a[href]",
        "currency": "USD",
    },
    # Ulta confirmed working (60 products) - kabhi kabhi soft-block/
    # interstitial deta hai, scraperapi_scraper.py mein auto-retry hai
    # isliye.
    {
        "name": "ultabeauty",
        "start_urls": ["https://www.ulta.com/shop/skin-care"],
        "use_scraperapi": True,
        "tile_selector": ".ProductCard",
        "name_selector": ".pal-c-ProductCardBody--title",
        "price_selector": ".pal-c-ProductCardBody--price",
        "link_selector": "a[href]",
        "currency": "USD",
    },
    # SecretSales UK confirmed working (18 products, real designer discounts -
    # Coach, Gucci, Marc Jacobs seen in test). Gilt aur Rue La La abhi kaam
    # nahi kar rahe (premium proxy tier + login-gated, dono issues).
    {
        "name": "secretsales",
        "start_urls": ["https://www.secretsales.com/"],
        "use_scraperapi": True,
        "tile_selector": '[class*="ProductCard-product-"]',
        "name_selector": '[class*="ProductCard-productName-"]',
        "price_selector": ".text-sm.font-bold",
        "link_selector": "",
        "currency": "GBP",
    },
    # Zappos confirmed working (108 products via JSON-LD, no CSS selectors
    # needed - clean structured data with brand+name+price+url per product).
    {
        "name": "zappos",
        "start_urls": ["https://www.zappos.com/women-boots"],
        "use_scraperapi": True,
        "use_jsonld": True,
        "currency": "USD",
    },

    # ScrapeGraphAI test batch (2026-08-30) - saari sites jo ScraperAPI
    # ke free/trial tier se fail ho rahi thi. Sephora confirmed working
    # (round 2), Hoka/Gilt/Rue La La round 2 mein transient backend
    # errors the (retrying round 3), Kohl's LLM-extraction issue.
    # Requires GitHub Secret: SCRAPEGRAPH_API_KEY
    {
        "name": "sephora",
        "start_urls": ["https://www.sephora.com/shop/skincare"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "kohls",
        "start_urls": ["https://www.kohls.com/catalog/handbags-accessories.jsp"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "hoka",
        "start_urls": ["https://www.hoka.com/en/us/womens-running-shoes/"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "gilt",
        "start_urls": ["https://www.gilt.com/sale/women/handbags"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "ruelala",
        "start_urls": ["https://www.ruelala.com/boutique/women"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
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
    {"name": "skims", "platform": "shopify", "domain": "https://skims.com", "category": "apparel", "currency": "USD"},
    {"name": "victoriabeckham", "platform": "shopify", "domain": "https://www.victoriabeckham.com", "category": "clothing", "currency": "USD"},
    {"name": "victoriabeckhambeauty", "platform": "shopify", "domain": "https://victoriabeckhambeauty.com", "category": "beauty", "currency": "USD"},
    {"name": "goodamerican", "platform": "shopify", "domain": "https://www.goodamerican.com", "category": "clothing", "currency": "USD"},

    # Drinkware / Travel / Luggage
    {"name": "stanley1913", "platform": "shopify", "domain": "https://www.stanley1913.com", "category": "drinkware", "currency": "USD"},
    {"name": "solgaard", "platform": "shopify", "domain": "https://solgaard.co", "category": "luggage", "currency": "USD"},
    {"name": "calpak", "platform": "shopify", "domain": "https://www.calpaktravel.com", "category": "luggage", "currency": "USD"},
    {"name": "delsey", "platform": "shopify", "domain": "https://us.delsey.com", "category": "luggage", "currency": "USD"},
    {"name": "lipault", "platform": "shopify", "domain": "https://www.lipault-usa.com", "category": "luggage", "currency": "USD"},
]
