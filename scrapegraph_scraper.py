"""
scrapegraph_scraper.py

ScrapeGraphAI ka SmartScraper endpoint use karta hai - CSS selectors ki
jagah plain-English prompt se product data extract karta hai. Useful hai
un sites ke liye jinka HTML structure baar baar badalta hai, ya jahan
CSS selectors likhna/maintain karna painful ho - AI khud samajh ke
extract kar leta hai.

Requires GitHub Secret: SCRAPEGRAPH_API_KEY

Usage in sites.py: config mein "use_scrapegraph": True daalo. Baaki
CSS-selector wale keys (tile_selector, name_selector, etc.) yahan
zaroori nahi hain - bas "start_urls" chahiye, aur optionally apna
"scrape_prompt" (warna default e-commerce prompt use hoga).

NOTE: Ye scraperapi_scraper.py ka replacement nahi hai - MK/Coach jaise
Akamai-protected sites ke liye ScraperAPI hi better hai (unka core
business hi bot-detection bypass karna hai). ScrapeGraphAI zyada useful
hai un sites ke liye jaha selector-maintenance overhead zyada hai, ya
site structure frequently change hoti hai - Akamai bypass ke liye nahi.
"""
import os
import re
import time
from datetime import datetime, timezone

import requests

SGAI_BASE_URL = "https://api.scrapegraphai.com/v1/smartscraper"
MAX_RETRIES = 3       # pehli try + 2 retries agar 0 products mile
POLL_INTERVAL = 3     # seconds, agar request turant complete na ho
MAX_POLL_ATTEMPTS = 20  # ~60 seconds tak poll karega

DEFAULT_PROMPT = (
    "Extract every product listed on this page. For each product return: "
    "name (include brand name if visible), price (numeric value only, no "
    "currency symbol), currency code (e.g. USD, GBP), product_url (full "
    "absolute URL), image_url (full absolute URL), sku or product id if "
    "visible, and in_stock (true unless explicitly marked sold out/"
    "unavailable). Return this as a JSON array under a top-level "
    "\"products\" key. Skip banners, recommendations, or non-product tiles."
)


def to_num(value):
    """'$199.50' ya 199.5 ya '199,50' -> 199.5 float mein, None agar na mile"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[\d,]+\.?\d*", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _headers():
    api_key = os.environ.get("SCRAPEGRAPH_API_KEY")
    if not api_key:
        raise RuntimeError("SCRAPEGRAPH_API_KEY secret set nahi hai")
    return {
        "accept": "application/json",
        "SGAI-APIKEY": api_key,
        "Content-Type": "application/json",
    }


def _poll_result(request_id, timeout_headers):
    """Agar SmartScraper turant complete na ho ('pending'/'processing'),
    to status endpoint poll karta hai jab tak result ya timeout na aaye."""
    status_url = f"{SGAI_BASE_URL}/{request_id}"
    for attempt in range(MAX_POLL_ATTEMPTS):
        resp = requests.get(status_url, headers=timeout_headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"SmartScraper request {request_id} failed: {data}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"SmartScraper request {request_id} timed out after polling")


def fetch_products(url, prompt, timeout=90):
    """Ek page ko ScrapeGraphAI ke SmartScraper se extract karta hai,
    raw 'result' dict return karta hai (jisme 'products' key honi chahiye)."""
    headers = _headers()
    payload = {"website_url": url, "user_prompt": prompt}

    resp = requests.post(SGAI_BASE_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "completed":
        return data.get("result", {})

    request_id = data.get("request_id")
    if not request_id:
        raise RuntimeError(f"Unexpected SmartScraper response (no request_id): {data}")

    completed = _poll_result(request_id, headers)
    return completed.get("result", {})


def normalize_products(raw_result, config):
    """SmartScraper ke JSON result ko baaki scrapers jaisa hi uniform
    product-dict schema mein convert karta hai."""
    raw_products = raw_result.get("products") if isinstance(raw_result, dict) else None
    if not raw_products:
        return []

    results = []
    for item in raw_products:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        sku = item.get("sku") or item.get("product_id")

        if not (name or sku):
            continue

        results.append({
            "sku": sku,
            "name": name,
            "price": to_num(item.get("price")),
            "in_stock": bool(item.get("in_stock", True)),
            "product_url": item.get("product_url") or item.get("url"),
            "image_url": item.get("image_url") or item.get("image"),
            "currency": item.get("currency") or config.get("currency", "USD"),
        })

    return results


def scrape_site_scrapegraph(config):
    """Config ke start_urls ko ScrapeGraphAI SmartScraper se scrape karta
    hai. 0 products milne pe (jaise LLM ne page samjha nahi, ya soft
    block) kuch retries karta hai - scraperapi_scraper.py jaisa hi pattern."""
    prompt = config.get("scrape_prompt", DEFAULT_PROMPT)
    all_products = []

    for url in config["start_urls"]:
        products = []

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw_result = fetch_products(url, prompt)
                products = normalize_products(raw_result, config)
            except Exception as e:
                print(f"  [ERROR] ScrapeGraphAI fetch failed for {url} (attempt {attempt}): {e}")
                products = []

            if products:
                break

            if attempt < MAX_RETRIES:
                print(f"  [RETRY] 0 products on attempt {attempt} for {url}, retrying...")
                time.sleep(2)

        if len(products) == 0:
            print(f"  [DEBUG] no products extracted from {url} after {MAX_RETRIES} attempts")

        for p in products:
            p["site"] = config["name"]
            p["category"] = "uncategorized"
            p["brand"] = config["name"]
            p["scraped_at"] = datetime.now(timezone.utc).isoformat()
        all_products.extend(products)
        print(f"  {url} -> {len(products)} products")

    return all_products
