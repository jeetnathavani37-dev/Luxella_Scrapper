"""
rephrase_descriptions.py

Copyright-risk kam karne ke liye - brand websites se copy ki hui
descriptions (verbatim) ko Claude API se REWRITE karta hai, taaki
wording alag ho jaaye jabki factual details (material, fit, color,
style, features) same rahein. Ye pure copy-paste se copyright
infringement risk kam karta hai.

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

REPHRASE_PROMPT = """Yahan ek product description hai jo brand ki website se scrape hui hai. Ise COMPLETELY REWRITE karo - naye sentence structure, naye words - jabki ye SAARI factual details preserve rahein: material, fit, fabric, color, style, features, sizing info. Koi naya fact mat banao, koi fact mat hatao. Sirf wording/phrasing badlo taaki ye original se kaafi alag lage. Output sirf rewritten description do (HTML tags ke bina), koi preamble/explanation nahi.

Original description:
{description}"""


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


def rephrase_with_claude(description_text):
    api_key = os.environ["ANTHROPIC_API_KEY"]
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": REPHRASE_PROMPT.format(description=description_text)}],
    }
    resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    return body["content"][0]["text"].strip()


def fetch_candidates(sb, limit):
    resp = (
        sb.table("products")
        .select("id,description,shopify_product_id,pushed_to_shopify")
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

    print(f"{len(candidates)} descriptions rephrase kar rahe hain...")

    access_token = None
    summary = {"rephrased": 0, "shopify_updated": 0, "errors": 0}

    for p in candidates:
        try:
            plain_text = strip_html(p["description"])
            if not plain_text:
                sb.table("products").update({"description_rephrased": True}).eq("id", p["id"]).execute()
                continue

            new_text = rephrase_with_claude(plain_text)
            new_html = f"<p>{new_text}</p>"

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
