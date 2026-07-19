"""
Shopify stores ke liye halka scraper — koi browser ya proxy nahi chahiye.
Shopify ka public /products.json endpoint use karta hai.
"""
import requests
from datetime import datetime, timezone


def scrape_shopify(config):
    domain = config["domain"]
    site = config["name"]
    all_products = []
    page = 1

    while page <= 20:  # safety cap
        url = f"{domain}/products.json?limit=250&page={page}"
        resp = requests.get(
            url, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
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
            image = p["images"][0]["src"] if p.get("images") else None

            all_products.append({
                "sku": variant.get("sku") or str(p.get("id")),
                "name": p.get("title"),
                "price": float(variant["price"]) if variant.get("price") else None,
                "in_stock": variant.get("available"),
                "product_url": f"{domain}/products/{p.get('handle')}",
                "image_url": image,
                "currency": config.get("currency", "USD"),
                "site": site,
                "category": config.get("category", "uncategorized"),
                "brand": site,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })

        page += 1

    return all_products
