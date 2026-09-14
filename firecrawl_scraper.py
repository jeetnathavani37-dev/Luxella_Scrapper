"""
firecrawl_scraper.py

Firecrawl ka /v1/scrape endpoint (JSON mode) use karta hai - prompt +
schema dono deke structured data nikalta hai, seedha JS-rendering ke
saath (extra "stealth" charge alag se nahi lagta, ScrapeGraphAI ki
tarah) - isliye cost-per-page kam padta hai.

Requires GitHub Secret: FIRECRAWL_API_KEY

Usage in sites.py: config mein "use_firecrawl": True daalo, baaki
sab (is_marketplace, currency, start_urls) scrapegraph_scraper.py jaisa
hi hai - schema bhi same rehta hai taaki db.py/shopify_push.py mein
kuch badalna na pade.

NOTE (2026-09-13): ScrapeGraphAI ke credits baar-baar khatam ho jaate
the aur uska plan mehenga tha ($20-100/month). Firecrawl try kiya -
same category (AI/prompt-based extraction), Hobby plan sasta hai
($16/month, 10k credits).

NOTE (2026-09-13) #2: BADA fix - request body ka format galat tha.
Firecrawl ka v1/scrape "formats" ek STRING array leta hai (jaise
["json"]), object nahi - aur prompt/schema "jsonOptions" naam ke alag
top-level field mein jaate hain, "formats" ke andar nahi. Pehle wala
format ("formats": [{"type": "json", ...}]) Firecrawl ke actual schema
se match nahi karta tha, isliye har request "400 Bad Request" de raha
tha. Fix kiya.

NOTE (2026-09-13) #3: IMPORTANT cost-correction - JSON-mode extraction
5 CREDITS/page leta hai (1 base + 4 extra JSON-mode ke liye), 1 nahi
jaisa pehle bataya tha. Credit-budget isके hisaab se recalculate karna
padega (50 brands, 1x/din = ~18,750 credits/mahina, Hobby ke 10,000
mein NAHI fit hoga - Standard ya kam brands/frequency chahiye hoga).
"""
import os
import re
import time
from datetime import datetime, timezone

import requests

from brand_extractor import extract_brand

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
MAX_RETRIES = 3
MIN_CONTENT_SIZE_WARNING = 2000

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "brand": {"type": "string"},
                    "description": {"type": "string"},
                    "color": {"type": "string"},
                    "sizes": {"type": "array", "items": {"type": "string"}},
                    "price": {"type": "string"},
                    "currency": {"type": "string"},
                    "product_url": {"type": "string"},
                    "image_url": {"type": "string"},
                    "sku": {"type": "string"},
                    "in_stock": {"type": "boolean"},
                },
                "required": ["name"],
            },
        }
    },
    "required": ["products"],
}

DEFAULT_PROMPT = (
    "This is an e-commerce category/listing page. Extract EVERY SINGLE "
    "product tile shown on this page - do not stop after the first few, "
    "capture all of them (could be dozens or hundreds). For each product: "
    "name (include brand if visible), brand (the manufacturer/brand of "
    "this specific product, e.g. 'Supreme' or 'Nike' - NOT the website's "
    "own name), description (any visible detail text - material, fit, "
    "style; short summary, blank if none), color, sizes (array of "
    "available size options, empty array if none), price (numeric string, "
    "no currency symbol), currency (e.g. USD, GBP), product_url (full "
    "absolute URL), image_url (full absolute URL), sku, and in_stock "
    "(true unless marked sold out). Skip banners/recommendations. Be "
    "exhaustive."
)


def to_num(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,]+\.?\d*", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _headers():
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY secret set nahi hai")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def build_variants_from_sizes(item):
    sizes = item.get("sizes")
    if not sizes or not isinstance(sizes, list) or len(sizes) < 2:
        return None

    base_price = to_num(item.get("price"))
    base_sku = item.get("sku")

    variants_out = []
    for size in sizes:
        if not size:
            continue
        variants_out.append({
            "size": str(size),
            "sku": f"{base_sku}-{size}" if base_sku else None,
            "price": base_price,
            "in_stock": True,
        })
    return variants_out if len(variants_out) > 1 else None


def fetch_products(url, prompt, schema, timeout=120):
    payload = {
        "url": url,
        "formats": ["json"],
        "jsonOptions": {"prompt": prompt, "schema": schema},
        "onlyMainContent": False,
    }
    resp = requests.post(FIRECRAWL_SCRAPE_URL, headers=_headers(), json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()

    if not body.get("success", True):
        raise RuntimeError(f"Firecrawl scrape error: {body.get('error', 'unknown')}")

    return body


def normalize_products(raw_json, config):
    raw_products = raw_json.get("products") if isinstance(raw_json, dict) else None
    if not raw_products:
        return []

    results = []
    for item in raw_products:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        sku = item.get("sku")
        if not (name or sku):
            continue

        description = item.get("description")
        if description:
            description = f"<p>{description}</p>"

        results.append({
            "sku": sku,
            "name": name,
            "_ai_brand": item.get("brand"),
            "description": description,
            "color": item.get("color") or None,
            "variants": build_variants_from_sizes(item),
            "price": to_num(item.get("price")),
            "in_stock": bool(item.get("in_stock", True)),
            "product_url": item.get("product_url"),
            "image_url": item.get("image_url"),
            "currency": item.get("currency") or config.get("currency", "USD"),
        })

    return results


def scrape_site_firecrawl(config):
    """scrapegraph_scraper.py jaisa hi pattern - retries, marketplace
    brand-extraction, debug logging - bas provider Firecrawl hai."""
    prompt = config.get("scrape_prompt", DEFAULT_PROMPT)
    is_marketplace = bool(config.get("is_marketplace"))
    all_products = []

    for url in config["start_urls"]:
        products = []
        last_body = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                body = fetch_products(url, prompt, EXTRACTION_SCHEMA)
                last_body = body
                raw_json = (body.get("data") or {}).get("json", {})
                products = normalize_products(raw_json, config)
            except Exception as e:
                print(f"  [ERROR] Firecrawl fetch failed for {url} (attempt {attempt}): {e}")
                products = []
                last_body = None

            if products:
                break

            if attempt < MAX_RETRIES:
                print(f"  [RETRY] 0 products on attempt {attempt} for {url}, retrying...")
                time.sleep(2)

        if len(products) == 0:
            print(f"  [DEBUG] no products extracted from {url} after {MAX_RETRIES} attempts")
            if last_body is not None:
                import json as json_module
                dumped = json_module.dumps(last_body)[:1500]
                print(f"  [DEBUG] last raw response (truncated): {dumped}")

        for p in products:
            p["site"] = config["name"]
            p["category"] = "uncategorized"

            if is_marketplace:
                ai_brand = p.pop("_ai_brand", None)
                p["brand"] = ai_brand or extract_brand(p.get("name"))
            else:
                p.pop("_ai_brand", None)
                p["brand"] = config["name"]

            p["scraped_at"] = datetime.now(timezone.utc).isoformat()
        all_products.extend(products)
        print(f"  {url} -> {len(products)} products")

    return all_products
