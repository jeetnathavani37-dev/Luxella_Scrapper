"""
recompute_compare_at.py — ek-baar ka maintenance: purana fake "35% off"
compare_at hatata hai (founder decision b; spec docs/specs/2026-10-10-compare-at-real-discounts.md).

Kyun sirf compare_at null, selling nahi chhuate:
  stored selling_price_inr HISTORICAL hai — jab product last price hua tab ke FX
  rate + tax ke hisaab se. Aaj se dobara compute karne pe formula evolve (USD FX,
  Sept-2026 wala 7% US sales tax) ki wajah se selling BADAL jaata hai. Isliye
  backfill selling ko haath hi nahi lagata. Abhi tak kisi product ka REAL source
  anchor nahi hai (Slice 4 ke scrapers wo capture karenge), to maujooda saare
  compare_at fake 35% hi hain -> sabko NULL. Real strikes tab aayenge jab site
  dobara scrape hogi (db.py tabhi selling + compare_at dono ek saath, same FX pe,
  compute karta hai).

    python recompute_compare_at.py            # DRY-RUN (kuch nahi likhta)
    python recompute_compare_at.py --apply    # backup -> batched NULL (founder-approved)

safe-writes: dry-run default, backup before apply, id-order <=1000 batches.
"""
import os
import sys
import json
from datetime import date

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(os.path.expanduser("~/.luxella.env"))  # SUPABASE_URL / SUPABASE_SERVICE_KEY
supabase = create_client(os.environ["SUPABASE_URL"].strip(), os.environ["SUPABASE_SERVICE_KEY"].strip())

PAGE = 1000


def iter_products():
    """id-order paging (PostgREST 1000-row cap ke upar bhi chalta hai).
    Sirf wahi rows jinka compare_at_price_inr abhi set hai (unhe hatana hai)."""
    last = -1
    while True:
        rows = (supabase.table("products")
                .select("id,name,price,selling_price_inr,compare_at_price_inr")
                .not_.is_("compare_at_price_inr", "null")
                .gt("id", last).order("id").limit(PAGE).execute().data) or []
        if not rows:
            return
        for r in rows:
            yield r
        last = rows[-1]["id"]
        if len(rows) < PAGE:
            return


def main(apply):
    rows = list(iter_products())
    print(f"[recompute] products with a (fake) compare_at to remove: {len(rows)}")
    print("  sample 20 (compare_at -> None; selling untouched):")
    for r in rows[:20]:
        print(f"     id={r['id']}  compare_at {r.get('compare_at_price_inr')} -> None"
              f"   (selling {r.get('selling_price_inr')} unchanged)  {str(r.get('name'))[:40]}")

    if not apply:
        print("\n[recompute] DRY-RUN only. Nothing written. selling_price_inr is never touched.")
        print("            Re-run with --apply (founder-approved) to null the fake compare_at.")
        return 0

    backup_dir = f"/root/backups/{date.today().isoformat()}"
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = f"{backup_dir}/compare_at_before.json"
    with open(backup_path, "w") as f:
        json.dump([{"id": r["id"], "compare_at_price_inr": r.get("compare_at_price_inr")} for r in rows], f)
    os.chmod(backup_path, 0o600)
    print(f"\n[recompute] backup of {len(rows)} rows -> {backup_path}")

    ids = [r["id"] for r in rows]
    written = 0
    CHUNK = 200  # safe-writes: Supabase .in_() 200 ya kam per call
    for idx in range(0, len(ids), CHUNK):
        chunk = ids[idx:idx + CHUNK]
        supabase.table("products").update({"compare_at_price_inr": None}).in_("id", chunk).execute()
        written += len(chunk)
        if idx % 4000 == 0:
            print(f"  cleared {written}/{len(ids)}")
    print(f"[recompute] done. {written} compare_at cleared. Shopify tab saaf hoga jab Slice 3 "
          "(clear-on-null) deploy hoga; theme pe strike waise bhi nahi dikhta.")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv[1:]))
