"""
Har site ka scraping config yahan hai. Do main types: ScrapeGraphAI-based
(LLM-powered, prompt-based extraction, koi CSS selector ki zaroorat
nahi) aur Shopify-platform-based (halka, /products.json se seedha).

NOTE (2026-08-29): MK/Coach ke liye Playwright, patchright, proxy -
sab try kiya, Akamai har baar 403 de raha tha (browser-automation
fingerprint hi detect ho raha tha). ScraperAPI use kiya tha isके liye,
successfully kaam bhi kiya (MK, Coach, StockX, GOAT, On, Ulta,
SecretSales, Zappos sab working the).

NOTE (2026-09-02): BADA switch - ScraperAPI ka trial plan 100% credits
khatam ho gaya, sabhi ScraperAPI-based sites ScrapeGraphAI pe switch
kiye.

NOTE (2026-09-04): BADA data-quality fix - "is_marketplace": True flag
add kiya un sites pe jo khud brand NAHI hain, balki multiple alag-alag
brands bechte hain. Single-brand sites ko is flag ki zaroorat nahi -
unka apna naam hi sahi brand hai.

NOTE (2026-09-04) #2: Nordstrom Rack, YOOX, Flannels (marketplace) aur
Tory Burch, Ralph Lauren, Marc Jacobs, Furla, Lands' End (single-brand)
add kiye. NOTE: is waqt (2026-09-04) ScraperAPI aur ScrapeGraphAI dono
ke credits khatam hain - in sabka (aur baaki saari use_scrapegraph:True
sites) ka test turant 402/403 dega jab tak credits refresh na hon ya
paid tier na liya jaaye. Config ready hai, bas providers ka credit
chahiye chalane ke liye.
"""

# ScrapeGraphAI ke liye - JS-rendering + stealth mode + scrolling,
# hard-to-scrape ya infinite-scroll/lazy-load sites ke liye.
STEALTH_FETCH_CONFIG = {"mode": "js", "stealth": True, "wait": 2000, "scrolls": 5}

SITES = [
    # Single-brand sites - inka apna naam hi sahi brand hai
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
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "coach",
        "start_urls": [
            "https://www.coach.com/shop/women/view-all",
            "https://www.coach.com/shop/women/handbags/view-all",
            "https://www.coach.com/shop/men/view-all",
            "https://www.coach.com/shop/women/accessories/view-all",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "katespade",
        "start_urls": [
            "https://www.katespadeoutlet.com/shop/view-all",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "lululemon",
        "start_urls": [
            "https://shop.lululemon.com/c/women-bestsellers/n16o10znskl",
            "https://shop.lululemon.com/c/women-leggings/n1udsq",
            "https://shop.lululemon.com/c/bestsellers-accessories/n14w56znskl",
            "https://shop.lululemon.com/c/women-whats-new/n16o10zq0cf",
            "https://shop.lululemon.com/c/women-work-clothes/n14rn9z4uwk",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "toryburch",
        "start_urls": [
            "https://www.toryburch.com/en-us/handbags/",
            "https://www.toryburch.com/en-us/sale/shoes/",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "ralphlauren",
        "start_urls": [
            "https://www.ralphlauren.com/women-accessories-handbags",
            "https://www.ralphlauren.com/women-handbags-totes",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "marcjacobs",
        "start_urls": [
            "https://www.marcjacobs.com/us-en/the-marc-jacobs/bags/view-all/",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "furla",
        "start_urls": [
            "https://www.furla.com/us/en/eshop/women/",
            "https://www.furla.com/us/en/eshop/women/bags/",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "landsend",
        "start_urls": [
            "https://www.landsend.com/shop/womens/S-y5c-175p-xec",
            "https://www.landsend.com/shop/womens-clothing/S-xez-y5c-xec",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },

    # MARKETPLACE sites (2026-09-04) - multiple brands bechte hain,
    # "is_marketplace": True se product-name se real brand nikalta hai
    {
        "name": "stockx",
        "start_urls": [
            "https://stockx.com/sneakers",
            "https://stockx.com/handbags",
            "https://stockx.com/watches",
            "https://stockx.com/streetwear",
            "https://stockx.com/category/accessories",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "goat",
        "start_urls": [
            "https://www.goat.com/sneakers",
            "https://www.goat.com/apparel",
            "https://www.goat.com/accessories",
            "https://www.goat.com/collectibles",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "on",
        "start_urls": ["https://www.on.com/en-us/shop/mens/shoes/cloud"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
    },
    {
        "name": "ultabeauty",
        "start_urls": ["https://www.ulta.com/shop/skin-care"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "secretsales",
        "start_urls": ["https://www.secretsales.com/"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "GBP",
        "is_marketplace": True,
    },
    {
        "name": "zappos",
        "start_urls": ["https://www.zappos.com/women-boots"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },

    {
        "name": "sephora",
        "start_urls": ["https://www.sephora.com/shop/skincare"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "kohls",
        "start_urls": ["https://www.kohls.com/catalog/handbags-accessories.jsp"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
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
        "is_marketplace": True,
    },
    {
        "name": "ruelala",
        "start_urls": ["https://www.ruelala.com/boutique/women"],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "nordstromrack",
        "start_urls": [
            "https://www.nordstromrack.com/shop/women",
            "https://www.nordstromrack.com/shop/women/handbags",
            "https://www.nordstromrack.com/shop/women/shoes",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "yoox",
        "start_urls": [
            "https://www.yoox.com/us/women/shoponline/handbags_c",
            "https://www.yoox.com/us/women/shoes/shoponline",
            "https://www.yoox.com/us/women/sale/shoponline/handbags_c",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "USD",
        "is_marketplace": True,
    },
    {
        "name": "flannels",
        "start_urls": [
            "https://www.flannels.com/women",
            "https://www.flannels.com/women/clothing",
            "https://www.flannels.com/clearance/women",
        ],
        "use_scrapegraph": True,
        "fetch_config": STEALTH_FETCH_CONFIG,
        "currency": "GBP",
        "is_marketplace": True,
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
