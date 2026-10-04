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

NOTE (2026-10-04): Do badlaav:
1. gemini-2.0-flash-lite Google ne band kar diya (404 "no longer
   available") - har run har product pe fail ho raha tha. Default ab
   gemini-3.5-flash-lite hai; REPHRASE_GEMINI_MODEL se badal sakte ho.
2. Naya optional backend: REPHRASE_BACKEND=claude-cli - is server pe
   `claude -p` (Claude Code headless) se rewrite karta hai, jo Claude Max
   subscription se chalta hai - koi API key/alag bill nahi (bas Max ki
   usage limits mein ginta hai). GitHub Actions mein Claude Code login
   nahi hota, isliye wahan default "gemini" hi rahega.

        REPHRASE_BACKEND=claude-cli BATCH_SIZE=20 python rephrase_descriptions.py
        REPHRASE_DRY_RUN=1 ...   # sirf rewrite karke print, Supabase/Shopify mein kuch nahi likhta

    Env: REPHRASE_BACKEND (gemini|claude-cli), REPHRASE_GEMINI_MODEL,
    REPHRASE_CLAUDE_MODEL (default sonnet), REPHRASE_DRY_RUN.

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
import json
import os
import re
import subprocess
import tempfile
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
RATE_LIMIT_DELAY = 4.5  # Gemini free-tier RPM-limit (10-15/min) respect karne ke liye
API_VERSION = "2025-01"
# REPHRASE_* naam jaan-boojh ke - CLAUDE_* env vars Claude Code ke apne vars se takraate hain
BACKEND = os.environ.get("REPHRASE_BACKEND", "gemini").strip().lower()
GEMINI_MODEL = os.environ.get("REPHRASE_GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
CLAUDE_MODEL = os.environ.get("REPHRASE_CLAUDE_MODEL", "sonnet")
CLAUDE_TIMEOUT = 180
DRY_RUN = os.environ.get("REPHRASE_DRY_RUN") == "1"
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


def rephrase_with_claude_cli(name, brand, description_text):
    """`claude -p` (Claude Code headless) - Claude Max subscription pe chalta hai.

    Khaali temp dir mein, bina tools/plugins/MCP ke chalate hain: sirf text
    likhna hai, aur Luxella repo ke hooks/CLAUDE.md load karke tokens
    waste nahi karne. --bare NAHI use kar sakte - wo Max ka OAuth login
    padhta hi nahi, sirf API key.
    """
    truncated = description_text[:MAX_DESCRIPTION_CHARS]
    prompt = REPHRASE_PROMPT.format(name=name or "", brand=brand or "", description=truncated)
    cmd = [
        "claude", "-p",
        "--model", CLAUDE_MODEL,
        "--tools", "",
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    with tempfile.TemporaryDirectory() as empty_dir:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              cwd=empty_dir, timeout=CLAUDE_TIMEOUT)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError(f"claude -p exit {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    if out.get("is_error") or proc.returncode != 0:
        # Max ki usage limit khatam ho to bhi yahin aata hai - error ke saath ruk jaate hain
        raise RuntimeError(f"claude -p error ({out.get('subtype')}): {str(out.get('result'))[:500]}")
    return strip_code_fence(out.get("result") or "")


def rephrase(name, brand, description_text):
    if BACKEND == "claude-cli":
        return rephrase_with_claude_cli(name, brand, description_text)
    if BACKEND == "gemini":
        return rephrase_with_gemini(name, brand, description_text)
    raise ValueError(f"REPHRASE_BACKEND '{BACKEND}' unknown - gemini ya claude-cli use karo")


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

    model = CLAUDE_MODEL if BACKEND == "claude-cli" else GEMINI_MODEL
    print(f"{len(candidates)} descriptions rephrase kar rahe hain (editorial format, {BACKEND}/{model})"
          + (" - DRY RUN, kuch save nahi hoga" if DRY_RUN else "") + "...")

    access_token = None
    summary = {"rephrased": 0, "shopify_updated": 0, "errors": 0}
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5  # model band / quota khatam / Max limit - poora batch error-loop mein mat ghumao

    for p in candidates:
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"  {MAX_CONSECUTIVE_ERRORS} errors lagaatar - ruk rahe hain (model/quota/limit check karo).")
            break
        try:
            plain_text = strip_html(p["description"])
            if not plain_text:
                if not DRY_RUN:
                    sb.table("products").update({"description_rephrased": True}).eq("id", p["id"]).execute()
                continue

            new_html = rephrase(p.get("name"), p.get("brand"), plain_text)

            if DRY_RUN:
                print(f"\n--- product id {p['id']} ({p.get('brand')}) ---\n{new_html}\n")
                summary["rephrased"] += 1
                continue

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
            consecutive_errors = 0

        except Exception as e:
            summary["errors"] += 1
            consecutive_errors += 1
            print(f"  [ERROR] product id {p['id']}: {e}")

        if BACKEND == "gemini":
            time.sleep(RATE_LIMIT_DELAY)  # claude -p khud ~3s leta hai; Gemini free-tier RPM ke liye hi delay

    print("\n=== Summary ===")
    print(summary)
    return summary["rephrased"]


if __name__ == "__main__":
    run()
