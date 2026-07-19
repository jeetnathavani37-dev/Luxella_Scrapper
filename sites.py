"""
Har site ka scraping config yahan hai.
Naya site add karna ho to bas neeche ek naya dict add kar do — poora scraper
dobara likhne ki zarurat nahi.
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
        "needs_proxy": False,   # pehle bina proxy try karte hain, block hua to True karenge
        "proxy_country": "us",
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "load_more_selector": '.show-more button, button[class*="load-more"], button[class*="show-more"]',
        "currency": "USD",
    },
]
