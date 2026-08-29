"""
scraperapi_scraper.py

MK/Coach jaise Akamai-protected sites ke liye ScraperAPI use karta hai.
Ye Playwright/patchright browser automation ki jagah, ScraperAPI ke
managed proxy+browser infrastructure se HTML fetch karta hai - unka
poora business hi Akamai/Cloudflare jaisa bot-detection bypass karna
hai, isliye success rate DIY browser automation se kaafi better hai.

Requires GitHub Secret: SCRAPERAPI_KEY

Usage in sites.py: config mein "use_scraperapi": True daalo, baaki
selectors (tile_selector, name_selector, etc.) same tarah kaam karte
hain jaise Playwright wale extract.py mein - bas CSS selectors hain,
engine badla hai, selector syntax nahi.
"""
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SCRAPERAPI_URL = "https://api.scraperapi.com/"


def to_num(text):
    """'$199.50' -> 199.5, None agar number na mile"""
    if not text:
        return None
    match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(match.group()) if match else None


def fetch_html(url, render=True, timeout=90):
    """ScraperAPI ke through page fetch karta hai. render=True matlab
    JS execute hoke poora page load hone ke baad ka HTML milta hai
    (lazy-loaded product grids ke liye zaroori)."""
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        raise RuntimeError("SCRAPERAPI_KEY secret set nahi hai")

    params = {
        "api_key": api_key,
        "url": url,
        "render": "true" if render else "false",
        "country_code": "us",
    }
    resp = requests.get(SCRAPERAPI_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_products_from_html(html, base_url, config):
    """Playwright wale extract_products() jaisa hi logic, bas
    BeautifulSoup se (kyunki yahan koi live browser page nahi hai)."""
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.select(config["tile_selector"])
    results = []

    parsed_base = urlparse(base_url)
    origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

    for tile in tiles:
        name_el = tile.select_one(config["name_selector"])
        price_el = tile.select_one(config["price_selector"])
        link_el = tile.select_one(config["link_selector"])
        img_el = tile.select_one("img")

        name = name_el.get_text(strip=True) if name_el else None
        price_raw = price_el.get_text(strip=True) if price_el else None
        product_url = link_el.get("href") if link_el else None
        if product_url and product_url.startswith("/"):
            product_url = origin + product_url

        sku = tile.get("data-pid")
        if not sku and product_url:
            m = re.search(r"/([A-Z0-9]{6,})\.html", product_url, re.I)
            sku = m.group(1) if m else None

        image_url = None
        if img_el:
            src = img_el.get("src") or ""
            data_src = img_el.get("data-src") or ""
            if data_src and not data_src.startswith("data:"):
                image_url = data_src
            elif src and not src.startswith("data:"):
                image_url = src

        if not (name or sku):
            continue

        results.append({
            "sku": sku,
            "name": name,
            "price": to_num(price_raw),
            "in_stock": True,
            "product_url": product_url,
            "image_url": image_url,
            "currency": config.get("currency", "USD"),
        })

    return results


def scrape_site_scraperapi(config):
    """Config ke start_urls ScraperAPI ke through scrape karta hai."""
    all_products = []
    for url in config["start_urls"]:
        try:
            html = fetch_html(url, render=True)
        except Exception as e:
            print(f"  [ERROR] ScraperAPI fetch failed for {url}: {e}")
            continue

        products = extract_products_from_html(html, url, config)

        if len(products) == 0:
            soup = BeautifulSoup(html, "lxml")
            tile_count = len(soup.select(config["tile_selector"]))
            title = soup.title.get_text(strip=True) if soup.title else ""
            body_snippet = soup.get_text()[:200].replace("\n", " ")
            print(f"  [DEBUG] page title: {title}")
            print(f"  [DEBUG] tile_selector matches: {tile_count}")
            print(f"  [DEBUG] body text starts with: {body_snippet}")

        for p in products:
            p["site"] = config["name"]
            p["category"] = "uncategorized"
            p["brand"] = config["name"]
            p["scraped_at"] = datetime.now(timezone.utc).isoformat()
        all_products.extend(products)
        print(f"  {url} -> {len(products)} products")

    return all_products
