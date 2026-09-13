"""
rephrase_descriptions.py

Copyright-risk kam karne ke liye - brand websites se copy ki hui
descriptions (verbatim) ko Claude API se REWRITE karta hai, taaki
wording alag ho jaaye jabki factual details (material, fit, color,
style, features) same rahein. Ye pure copy-paste se copyright
infringement risk kam karta hai.

NOTE (2026-09-09): Format upgrade - ab sirf plain-paragraph rewrite
nahi karta, balki ek proper "editorial" structure banata hai:
Luxella-branded intro paragraph + "Key Features & Characteristics"
bullet list (jaisa premium resale sites - Mirage jaisi - karte hain).
Isse description sirf copyright-safe hi nahi, professional/premium
bhi lagti hai.

Requires GitHub Secrets:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY,
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=200 python rephrase_descriptions.py
"""
import os
import re
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
RATE_LIMIT_DELAY = 0.4
API_VERSION = "2025-01"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

REPHRASE_PROMPT = """Yahan ek product ki details hain, jinse tumhe Luxella (luxury goods reseller) ke liye ek premium, editorial-style product description banani hai - HTML format mein.

Product name: {name}
Brand: {brand}
Original description (brand ki site se scrape hui, ise apne words mein rewrite karo, koi fact mat badlo/hatao):
{description}

Output format (bilkul isी structure mein, valid HTML):
1. Ek engaging intro paragraph (<p> tag) - jisme product ka naam, brand, aur "Luxella" ka mention ho (jaise "exclusively curated by Luxella" ya "sourced by Luxella" jaisa tone) - premium/aspirational tone, 2-3 sentences
2. "<h3>Key Features & Characteristics:</h3>"
3. "<ul>" mein bullet points (<li>) - original description se saari factual details (material, dimensions, color, hardware, fastening, lining, etc.) - jo bhi original mein mila

Rules:
- Koi naya fact mat banao jo original mein nahi tha
- Koi fact mat hatao jo original mein tha
- Sirf VALID HTML output do (p, h3, ul, li tags) - koi preamble, explanation, ya markdown nahi
- Brand ka naam "Luxella" ke saath sirf "curated by/sourced by" context mein use karo - kabhi "authorized/official partner" jaisa mat likho
"""


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_shopify_domain():
    return os.environ["SHOPIFY_STORE_DOMAIN"]


def get_access_token():
    client_id = os.environ["SHOPIFY_CLIENT_ID"]
    client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]
    resp = requests.post(
        f"https://{get_shopify_domain()}/admin/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_shopify_base_url():
    return f"https://{get_shopify_domain()}/admin/api/{API_VERSION}"


def strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def strip_code_fence(text):
    """Kabhi kabhi Claude ```html ... ``` mein wrap kar deta hai - hata dete hain."""
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def rephrase_with_claude(name, brand, description_text):
    api_key = os.environ["ANTHROPIC_API_KEY"]
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    prompt = REPHRASE_PROMPT.format(name=name or "", brand=brand or "", description=description_text)
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return strip_code_fence(body["content"][0]["text"])


def fetch_candidates(sb, limit):
    resp = (
        sb.table("products")
        .select("id,name,brand,description,shopify_product_id,pushed_to_shopify")
        .not_.is_("description", "null")
        .neq("description", "")
        .is_("description_rephrased", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


def update_shopify_description(access_token, shopify_product_id, new_description_html):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"product": {"id": int(shopify_product_id), "body_html": new_description_html}}
    resp = requests.put(
        f"{get_shopify_base_url()}/products/{shopify_product_id}.json",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()


def run():
    sb = get_supabase()
    candidates = fetch_candidates(sb, BATCH_SIZE)

    if not candidates:
        print("Koi products nahi mile rephrase karne ke liye - sab already done hain.")
        return 0

    print(f"{len(candidates)} descriptions rephrase kar rahe hain (editorial format)...")

    access_token = None
    summary = {"rephrased": 0, "shopify_updated": 0, "errors": 0}

    for p in candidates:
        try:
            plain_text = strip_html(p["description"])
            if not plain_text:
                sb.table("products").update({"description_rephrased": True}).eq("id", p["id"]).execute()
                continue

            new_html = rephrase_with_claude(p.get("name"), p.get("brand"), plain_text)

            sb.table("products").update({
                "description": new_html,
                "description_rephrased": True,
            }).eq("id", p["id"]).execute()
            summary["rephrased"] += 1

            if p.get("pushed_to_shopify") and p.get("shopify_product_id"):
                if access_token is None:
                    access_token = get_access_token()
                update_shopify_description(access_token, p["shopify_product_id"], new_html)
                summary["shopify_updated"] += 1
                time.sleep(RATE_LIMIT_DELAY)

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] product id {p['id']}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["rephrased"]


if __name__ == "__main__":
    run()
