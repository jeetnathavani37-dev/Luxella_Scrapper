"""
scrapegraph_scraper.py

ScrapeGraphAI ka v2 Extract endpoint use karta hai - CSS selectors ki
jagah plain-English prompt se product data extract karta hai. Useful hai
un sites ke liye jinka HTML structure baar baar badalta hai, ya jahan
CSS selectors likhna/maintain karna painful ho - AI khud samajh ke
extract kar leta hai.

Requires GitHub Secret: SCRAPEGRAPH_API_KEY

Usage in sites.py: config mein "use_scrapegraph": True daalo. Baaki
CSS-selector wale keys (tile_selector, name_selector, etc.) yahan
zaroori nahi hain - bas "start_urls" chahiye, aur optionally apna
"scrape_prompt" (warna default e-commerce prompt use hoga).

NOTE (2026-08-30): ScrapeGraphAI ne v1 API deprecate kar diya hai - naye
API keys sirf v2 (v2-api.scrapegraphai.com) ke saath kaam karte hain,
purana v1 endpoint (api.scrapegraphai.com/v1/...) 403 "auth_invalid_key"
deta hai naye keys ke saath ("issued against the legacy v1 surface").
v2 ka /api/extract endpoint synchronous hai (koi request_id polling
nahi chahiye) - {status, data} shape mein response deta hai.

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

SGAI_EXTRACT_URL = "https://v2-api.scrapegraphai.com/api/extract"
MAX_RETRIES = 3  # pehli try + 2 retries agar 0 products mile

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


def fetch_products(url, prompt, timeout=120):
    """Ek page ko ScrapeGraphAI v2 /api/extract se extract karta hai,
    raw 'data' dict return karta hai (jisme 'products' key honi chahiye).
    v2 synchronous hai - ek hi request-response mein result mil jaata hai."""
    headers = _headers()
    payload = {"url": url, "prompt": prompt}

    resp = requests.post(SGAI_EXTRACT_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()

    if body.get("status") == "error":
        error_msg = body.get("error", "unknown error")
        raise RuntimeError(f"ScrapeGraphAI extract error: {error_msg}")

    return body.get("data", {})


def normalize_products(raw_data, config):
    """v2 extract ke JSON result ko baaki scrapers jaisa hi uniform
    product-dict schema mein convert karta hai."""
    raw_products = raw_data.get("products") if isinstance(raw_data, dict) else None
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
    """Config ke start_urls ko ScrapeGraphAI v2 Extract se scrape karta
    hai. 0 products milne pe (jaise LLM ne page samjha nahi, ya soft
    block) kuch retries karta hai - scraperapi_scraper.py jaisa hi pattern."""
    prompt = config.get("scrape_prompt", DEFAULT_PROMPT)
    all_products = []

    for url in config["start_urls"]:
        products = []

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw_data = fetch_products(url, prompt)
                products = normalize_products(raw_data, config)
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
