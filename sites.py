"""
Har site ka scraping config yahan hai.
Naya site add karna ho to bas neeche ek naya dict add kar do — poora scraper
dobara likhne ki zarurat nahi.

Fields:
  name            -> site ka short naam (products table ke 'site' column me jayega)
  start_urls      -> category page URLs jaha se scraping shuru hogi
  needs_browser   -> True agar site JavaScript se products load karti hai (MK jaisi)
                     False agar simple HTML site hai (Shopify jaisi, tez aur sasti)
  needs_proxy     -> True agar site bot-protection strong hai (residential proxy chahiye)
  proxy_country   -> proxy ka country code (US products ke liye 'us')
  tile_selector   -> ek product card ka CSS selector
  name_selector   -> tile ke andar product-name ka selector
  price_selector  -> tile ke andar price ka selector
  link_selector   -> tile ke andar product-link ka selector
  load_more_selector -> "Load More" button ka selector (agar ho, warna None)
  currency        -> 'USD', 'GBP', 'EUR' etc.
"""

SITES = [
    {
        "name": "michaelkors",
        "start_urls": [
            "https://www.michaelkors.com/women/handbags/_/N-28ei",
            # yaha aur category URLs add karte jaana (jewelry, shoes, watches, sale...)
        ],
        "needs_browser": True,
        "needs_proxy": True,          # MK ko residential proxy chahiye, warna block ho jata hai
        "proxy_country": "us",
        "tile_selector": ".product-tile",
        "name_selector": '[class*="name"], [class*="title"], .pdp-link',
        "price_selector": '[class*="price"]',
        "link_selector": ".product-tile-image-link, a[href]",
        "load_more_selector": '.show-more button, button[class*="load-more"], button[class*="show-more"]',
        "currency": "USD",
    },

    # ============================================================
    # Naya site jodne ka TEMPLATE (copy-paste karke fill karo):
    # ============================================================
    # {
    #     "name": "coach",
    #     "start_urls": ["https://www.coach.com/..."],
    #     "needs_browser": True,
    #     "needs_proxy": True,
    #     "proxy_country": "us",
    #     "tile_selector": ".product-tile",       # inspect karke confirm karna
    #     "name_selector": '[class*="name"]',
    #     "price_selector": '[class*="price"]',
    #     "link_selector": "a[href]",
    #     "load_more_selector": None,
    #     "currency": "USD",
    # },
]
