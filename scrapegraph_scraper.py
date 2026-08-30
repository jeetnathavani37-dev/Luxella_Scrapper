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

Optional "fetch_config" dict bhi de sakte ho config mein - JS-rendering
ya stealth mode ke liye (hard-to-scrape sites). Example:
    "fetch_config": {"mode": "js", "stealth": True, "wait": 2000, "scrolls": 5}
NOTE: stealth mode extra credits leta hai (~5 credits/request) - sirf
un sites pe use karo jo normal fetch se block ho rahi hain.

NOTE (2026-08-30): ScrapeGraphAI ne v1 API deprecate kar diya hai - naye
API keys sirf v2 (v2-api.scrapegraphai.com) ke saath kaam karte hain.
v2 ka /api/extract endpoint synchronous hai, result "json" key mein
hota hai ("data" mein NAHI).

NOTE (2026-08-30) #2: Batch test round 1 (default fetch) - sab fail.
Round 2 (fetch_config: mode=js, stealth=True, wait=2000):
  - Sephora: WORKING (3 products!) - stealth mode ne bot-detection
    bypass kiya. Par count kam hai - real listing page mein sainkdo
    products hone chahiye, LLM sirf pehle 3 hi extract kar paya (page
    ke upar wala visible portion). Fix: scrolls badhaya (5) aur prompt
    ko explicit kiya ki poori page scroll karke SAARE products extract
    kare, sirf pehli screen wale nahi.
  - Kohl's: 0 products par 5287 chars real content (JS render kaam
    kar raha hai) - LLM ne products samjhe nahi, prompt clarity issue.
  - Hoka: 502, Gilt: 404, Rue La La: exception - teeno ScrapeGraphAI
    backend ki transient instability lagti hai (ek hi run mein teen
    alag providers-side errors) - gilt.com khud up hai (verified),
    isliye ye likely retry-later cases hain, permanent block nahi.

NOTE: Ye scraperapi_scraper.py ka replacement nahi hai - MK/Coach jaise
Akamai-protected sites ke liye ScraperAPI hi better hai (unka core
business hi bot-detection bypass karna hai). ScrapeGraphAI zyada useful
hai un sites ke liye jaha selector-maintenance overhead zyada hai, ya
site structure frequently change hoti hai - Akamai bypass ke liye nahi.
"""
import os
import re
import time
import json as json_module
from datetime import datetime, timezone

import requests

SGAI_EXTRACT_URL = "https://v2-api.scrapegraphai.com/api/extract"
MAX_RETRIES = 3  # pehli try + 2 retries agar 0 products mile
MIN_CONTENT_SIZE_WARNING = 2000  # is se kam chunk size = likely blocked/interstitial page

DEFAULT_PROMPT = (
    "This is an e-commerce category/listing page. Scroll through the "
    "ENTIRE page and extract EVERY SINGLE product tile shown - do not "
    "stop after the first few visible products, keep going until you "
    "have captured all products loaded on the page (this could be "
    "dozens or hundreds of items). For each product return: name "
    "(include brand name if visible), price (numeric value only, no "
    "currency symbol), currency code (e.g. USD, GBP), product_url (full "
    "absolute URL), image_url (full absolute URL), sku or product id if "
    "visible, and in_stock (true unless explicitly marked sold out/"
    "unavailable). Return this as a JSON array under a top-level "
    "\"products\" key. Skip banners, recommendations, or non-product tiles. "
    "Be exhaustive - a partial list is not acceptable."
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


def _total_chunk_size(body):
    """Debug ke liye - metadata.chunker.chunks se total fetched content
    size nikalta hai, taaki pata chale page properly load hua ya nahi
    (blocked/interstitial pages bohot chhoti hoti hain)."""
    try:
        chunks = body.get("metadata", {}).get("chunker", {}).get("chunks", [])
        return sum(c.get("size", 0) for c in chunks)
    except (AttributeError, TypeError):
        return None


def fetch_products(url, prompt, fetch_config=None, timeout=120):
    """Ek page ko ScrapeGraphAI v2 /api/extract se extract karta hai,
    poora response body return karta hai. Result body['json'] mein hota
    hai. fetch_config diya ho to JS-rendering/stealth mode/scrolling/etc
    enable karta hai (hard-to-scrape ya infinite-scroll sites ke liye)."""
    headers = _headers()
    payload = {"url": url, "prompt": prompt}
    if fetch_config:
        payload["fetchConfig"] = fetch_config

    resp = requests.post(SGAI_EXTRACT_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()

    if body.get("status") == "error" or body.get("error"):
        error_msg = body.get("error", "unknown error")
        raise RuntimeError(f"ScrapeGraphAI extract error: {error_msg}")

    return body


def normalize_products(raw_json, config):
    """v2 extract ke 'json' field ko baaki scrapers jaisa hi uniform
    product-dict schema mein convert karta hai."""
    raw_products = raw_json.get("products") if isinstance(raw_json, dict) else None
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
    block) kuch retries karta hai - scraperapi_scraper.py jaisa hi pattern.
    0 products pe raw response + fetched-content-size bhi print karta hai
    debug ke liye (chhota content size = likely blocked/interstitial page)."""
    prompt = config.get("scrape_prompt", DEFAULT_PROMPT)
    fetch_config = config.get("fetch_config")
    all_products = []

    for url in config["start_urls"]:
        products = []
        last_body = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                body = fetch_products(url, prompt, fetch_config=fetch_config)
                last_body = body
                raw_json = body.get("json", {})
                products = normalize_products(raw_json, config)
            except Exception as e:
                print(f"  [ERROR] ScrapeGraphAI fetch failed for {url} (attempt {attempt}): {e}")
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
                content_size = _total_chunk_size(last_body)
                if content_size is not None:
                    flag = " <-- likely blocked/interstitial page, not real content!" \
                        if content_size < MIN_CONTENT_SIZE_WARNING else ""
                    print(f"  [DEBUG] total fetched content size: {content_size} chars{flag}")
                dumped = json_module.dumps(last_body)[:1500]
                print(f"  [DEBUG] last raw response (truncated to 1500 chars): {dumped}")
            else:
                print("  [DEBUG] last attempt raised an exception, no response body available")

        for p in products:
            p["site"] = config["name"]
            p["category"] = "uncategorized"
            p["brand"] = config["name"]
            p["scraped_at"] = datetime.now(timezone.utc).isoformat()
        all_products.extend(products)
        print(f"  {url} -> {len(products)} products")

    return all_products
