"""
Har site ka scraping config yahan hai.
Do type ke sites: browser-based (JS-heavy, jaise MK/Coach) aur
shopify-based (halka, koi browser/proxy nahi chahiye).
"""

SITES = [
    {
        "name": "michaelkors",
        "start_urls": [
            "https://www.michaelkors.com/women/handbags/_/N-28ei",
        ],
        "needs_browser": True,
        "needs_proxy": True,
        "proxy_country": "us",
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "load_more_selector": '.show-more button, button[class*="load-more"], button[class*="show-more"]',
        "currency": "USD",
    },
    {
        "name": "coach",
        "start_urls": [
            "https://www.coach.com/shop/women/bestsellers",
        ],
        "needs_browser": True,
        "needs_proxy": True,   # Coach bhi Akamai-protected nikla, proxy chahiye
        "proxy_country": "us",
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "load_more_selector": '.show-more button, button[class*="load-more"], button[class*="show-more"]',
        "currency": "USD",
    },
    {
        "name": "karllagerfeld",
        "platform": "shopify",
        "domain": "https://www.karllagerfeldparis.com",
        "category": "clothing",
        "currency": "USD",
    },

    # ============================================================
    # Naya Shopify site jodne ka TEMPLATE:
    # ============================================================
    # {
    #     "name": "brand_naam",
    #     "platform": "shopify",
    #     "domain": "https://www.example.com",
    #     "category": "kuch_bhi",
    #     "currency": "USD",
    # },
]
