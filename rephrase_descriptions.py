"""
rephrase_descriptions.py

Copyright-risk kam karne ke liye - brand websites se copy ki hui
descriptions (verbatim) ko REWRITE karta hai, taaki wording alag ho
jaaye jabki factual details (material, fit, color, style, features)
same rahein. Ye pure copy-paste se copyright infringement risk kam
karta hai.

NOTE (2026-09-09): Format upgrade - "editorial" structure banata hai:
Luxella-branded intro paragraph + "Key Features & Characteristics"
bullet list (jaisa premium resale sites - Mirage jaisi - karte hain).

NOTE (2026-09-15): BADA PROVIDER SWITCH - Anthropic API credits khatam
ho gaye the, isliye 38,000 mein se sirf ~1000 descriptions hi ho paayi
thi. Ye ek simple text-rewrite task hai (complex reasoning nahi
chahiye) - isliye Google Gemini API pe switch kiya, jiska GENUINELY
FREE tier hai (koi credit-card nahi chahiye, koi expiration nahi) -
1,500 requests/din tak free. Poora 38k backlog isse dheere-dheere
(kai din mein) bilkul free clear ho jaayega.

Requires GitHub Secrets:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY,
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=200 python rephrase_descriptions.py

NOTE #2: Do aur fixes bhi saath mein kiye (jo dusre debugging-session
mein mile the):
1. fetch_candidates() ab Supabase ke 1000-row default-limit se bachne
   ke liye .range() se explicit pagination karta hai - pehle bade
   batch_size (jaise 1500) silently 1000 pe cap ho jaate the.
2. Bohot lambi (6000+ chars) descriptions truncate hoti hain bhejne se
   pehle - oversized/garbled scraped text errors ki ek wajah thi.
3. API error ka poora response-body ab log hota hai (generic "400
   Bad Request" ki jagah asli reason dikhta hai).
"""
import os
import re
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
RATE_LIMIT_DELAY = 4.5  # Gemini free-tier RPM-limit (10-15/min) respect karne ke liye
API_VERSION = "2025-01"
GEMINI_MODEL = "gemini-2.0-flash-lite"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_DESCRIPTION_CHARS = 6000

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
    """Kabhi kabhi model ```html ... ``` mein wrap kar deta hai - hata dete hain."""
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def rephrase_with_gemini(name, brand, description_text):
    api_key = os.environ["GEMINI_API_KEY"]
    truncated = description_text[:MAX_DESCRIPTION_CHARS]
    prompt = REPHRASE_PROMPT.format(name=name or "", brand=brand or "", description=truncated)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    resp = requests.post(
        f"{GEMINI_API_URL}?key={api_key}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return strip_code_fence(text)


def fetch_candidates(sb, limit):
    """Explicit .range() pagination use karta hai - Supabase ka default
    1000-row limit bade batch_size (jaise 1500) ko silently cap kar
    deta tha, isliye."""
    resp = (
        sb.table("products")
        .select("id,name,brand,description,shopify_product_id,pushed_to_shopify")
        .not_.is_("description", "null")
        .neq("description", "")
        .is_("description_rephrased", "null")
        .range(0, limit - 1)
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

    print(f"{len(candidates)} descriptions rephrase kar rahe hain (editorial format, Gemini)...")

    access_token = None
    summary = {"rephrased": 0, "shopify_updated": 0, "errors": 0}

    for p in candidates:
        try:
            plain_text = strip_html(p["description"])
            if not plain_text:
                sb.table("products").update({"description_rephrased": True}).eq("id", p["id"]).execute()
                continue

            new_html = rephrase_with_gemini(p.get("name"), p.get("brand"), plain_text)

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

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] product id {p['id']}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["rephrased"]


if __name__ == "__main__":
    run()
