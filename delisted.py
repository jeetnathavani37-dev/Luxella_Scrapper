"""
delisted.py

Jo products brand ne apni site se hata diye unhe sold out mark karna.
Spec: docs/specs/2026-10-05-mark-delisted-sold-out.md

shopify_scraper sirf abhi-listed products deta hai; jo row is run mein nahi dikhi uska
in_stock kabhi false nahi hota tha - Shopify pe hamesha bikti rehti thi (2026-10-05 audit:
2,382 aise live, jwpei ke sample URLs 404).

Guards (koi bhi fail -> kuch mark nahi):
  - scrape complete ho (shopify_scraper.scrape_shopify_catalog complete=True)
  - is run mein dikhe URLs >= MIN_SEEN_SHARE x site ke in-stock rows (site block/down nahi)
  - mark hone wale <= MAX_MARK_SHARE x in-stock rows (domain/handle badla ho to mass-mark nahi)
"""
import json
import time
from datetime import datetime, timezone

MIN_SEEN_SHARE = 0.5
MAX_MARK_SHARE = 0.3


def _ts(value):
    if not value:
        return None
    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)  # timestamp (bina tz) column bhi chale


def plan_delisted(rows, seen_urls, run_started_at, min_seen=MIN_SEEN_SHARE, max_mark=MAX_MARK_SHARE):
    """rows: site ki Supabase rows (id, product_url, in_stock, scraped_at ...). Return (to_mark, reason).

    Candidate = in_stock True, product_url hai, is run mein nahi dikha, aur is run se pehle scrape hua.
    Percentages site ke in-stock rows pe (purane sold-out rows ginti nahi bigaadte)."""
    started = _ts(run_started_at)
    in_stock = [r for r in rows if r.get("in_stock") is True and r.get("product_url")]
    if not in_stock:
        return [], "no in-stock rows"
    if len(seen_urls) < min_seen * len(in_stock):
        return [], f"seen {len(seen_urls)} < {min_seen:.0%} of {len(in_stock)} in-stock"
    to_mark = []
    for r in in_stock:
        if r["product_url"] in seen_urls:
            continue
        scraped = _ts(r.get("scraped_at"))
        if scraped is not None and started is not None and scraped >= started:
            continue  # isi run mein likha gaya (naya/badla) - unseen nahi
        to_mark.append(r)
    share = len(to_mark) / len(in_stock)
    if share > max_mark:
        return [], f"mark {len(to_mark)} = {share:.0%} > {max_mark:.0%} of {len(in_stock)} in-stock"
    return to_mark, "ok"


PAGE = 1000
CHUNK = 200
SELECT = "id,site,sku,name,product_url,in_stock,variants,scraped_at"


def fetch_site_stock_rows(client, site):
    """Site ki rows, sirf zaroori columns - id se paged (PostgREST 1000 cap)."""
    rows, last = [], 0
    while True:
        page = (client.table("products").select(SELECT).eq("site", site)
                .gt("id", last).order("id").limit(PAGE).execute().data)
        rows += page
        if len(page) < PAGE:
            return rows
        last = page[-1]["id"]


def _sold_out_variants(variants):
    if not isinstance(variants, list):
        return variants
    return [{**v, "in_stock": False} if isinstance(v, dict) else v for v in variants]


def mark_unseen_sold_out(client, site, seen_urls, run_started_at, mode="dry", deadline=None,
                         backup_path=None, log=print, now=None):
    """mode: "dry" (default) sirf log, "1" likhta hai. Return dict(planned, marked, reason, samples).

    Likhna: har row alag update (variants har row ka alag) - in_stock false, saare sizes false
    (warna per-size sync unhe 0 nahi karega), last_checked_at. .eq("in_stock", True) taaki beech
    mein dobara listed hua product overwrite na ho. Phir product_changes 'delisted' rows."""
    rows = fetch_site_stock_rows(client, site)
    to_mark, reason = plan_delisted(rows, seen_urls, run_started_at)
    samples = [r["product_url"] for r in to_mark[:10]]
    result = {"planned": len(to_mark), "marked": 0, "reason": reason, "samples": samples}
    log(f"  [delisted] {site}: {'would mark' if mode != '1' else 'marking'} {len(to_mark)} "
        f"(rows {len(rows)}, seen {len(seen_urls)}) - {reason}")
    for url in samples:
        log(f"    {url}")
    if mode != "1" or not to_mark:
        return result
    if not backup_path:
        log(f"  [delisted] {site}: no backup path - kuch nahi likha (safe-writes: pehle backup)")
        result["reason"] = "no backup path"
        return result

    with open(backup_path, "w") as f:
        json.dump([{k: r.get(k) for k in ("id", "product_url", "in_stock", "variants")} for r in to_mark], f)
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    marked = []
    try:
        for r in to_mark:
            if deadline and time.time() > deadline:
                log(f"  [delisted] {site}: deadline - {len(marked)} marked, baaki agle run")
                break
            res = client.table("products").update({
                "in_stock": False, "variants": _sold_out_variants(r.get("variants")), "last_checked_at": stamp,
            }).eq("id", r["id"]).eq("in_stock", True).execute()
            if res.data:  # 0 rows = beech mein dobara listed (in_stock true nahi raha) - mark nahi hua
                marked.append(r)
    finally:
        # beech mein exception aaye to bhi jo likh gaye unka change-log zaroor jaaye
        changes = [{"site": site, "sku": r.get("sku"), "product_url": r["product_url"], "name": r.get("name"),
                    "change_type": "delisted", "old_value": "True", "new_value": "False"} for r in marked]
        for i in range(0, len(changes), CHUNK):
            client.table("product_changes").insert(changes[i:i + CHUNK]).execute()
        result["marked"] = len(marked)
    return result


def mark_mode(env_value):
    """MARK_DELISTED: '1' likho, '0'/'off' band, baaki sab (khaali, 'dry', galat) = dry-run."""
    v = (env_value or "").strip().lower()
    if v == "1":
        return "1"
    if v in ("0", "off"):
        return "off"
    return "dry"


def should_mark(config, scrape, not_saved_deadline, deadline, mode, now=None):
    """Sirf Shopify-platform site, poora scrape, sab save hua, time bacha, mode off nahi."""
    if mode == "off" or config.get("platform") != "shopify" or config.get("use_firecrawl"):
        return False
    if not scrape or not scrape.get("complete") or not_saved_deadline:
        return False
    return (now if now is not None else time.time()) < deadline
