"""
Shopify stores ke liye halka scraper — koi browser ya proxy nahi chahiye.
Shopify ka public /products.json endpoint use karta hai.

NOTE (2026-08-30): Pehle sirf pehli image (p["images"][0]) le rahe the,
baaki gallery images discard ho rahi thi - jabki Shopify ka /products.json
response mein already SAARI images hoti hain (extra request ki zaroorat
nahi thi). Ab poori gallery "image_urls" (list) mein save hoti hai,
"image_url" primary/first image ke liye backward-compat ke liye rakha
hai (purane code jo sirf ek image expect karte hain unke liye).
"""
import requests
from datetime import datetime, timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_color(product, variant):
    """Product ke 'options' list me Color/Colour dhoondhta hai, variant se value nikalta hai."""
    options = product.get("options", [])
    for idx, opt in enumerate(options):
        if opt.get("name", "").lower() in ("color", "colour"):
            return variant.get(f"option{idx + 1}")
    return None


def scrape_shopify(config):
    domain = config["domain"]
    site = config["name"]
    all_products = []
    page = 1

    while page <= 20:
        url = f"{domain}/products.json?limit=250&page={page}"
        resp = requests.get(url, timeout=20, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  [Shopify] {url} -> status {resp.status_code}, stopping")
            break

        data = resp.json()
        products = data.get("products", [])
        if not products:
            break

        for p in products:
            variants = p.get("variants", [])
            variant = variants[0] if variants else {}

            images = p.get("images", [])
            image_urls = [img["src"] for img in images if img.get("src")]
            primary_image = image_urls[0] if image_urls else None

            all_products.append({
                "sku": variant.get("sku") or str(p.get("id")),
                "name": p.get("title"),
                "price": float(variant["price"]) if variant.get("price") else None,
                "in_stock": variant.get("available"),
                "product_url": f"{domain}/products/{p.get('handle')}",
                "image_url": primary_image,
                "image_urls": image_urls,
                "color": extract_color(p, variant),
                "currency": config.get("currency", "USD"),
                "site": site,
                "category": config.get("category", "uncategorized"),
                "brand": site,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })

        page += 1

    return all_products
