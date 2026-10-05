# Mark products the source no longer lists as sold out

**Goal:** When a brand removes a product from its site, Luxella stops selling it within one scrape and one sync cycle.

**Why now:** a read-only audit on 2026-10-05 found:
- **2,382 pushed products** on active Shopify-platform sites are still live and in stock on Luxella, but haven't been seen by the scraper for 3 to 50+ days.
  - Largest: jwpei 1,565, staud 605, victoriabeckham 576, aloyoga 529.
- **2 of 2 spot-checked stale jwpei URLs return 404** at the source.
- Cause: `shopify_scraper.scrape_shopify` only returns products that are listed now, and `db.save_products` only updates rows it receives. Nothing marks unseen rows, so they stay `in_stock=true` forever.

## In scope
1. **Completeness signal from `scrape_shopify`.** It returns `complete=True` only when pagination ended on an empty page. It returns `False` when:
   - a page returned non-200 (e.g. 429), or
   - the 20-page cap (5,000 products) was hit, or
   - an exception happened.
2. **New `db.mark_unseen_sold_out(site, seen_urls, run_started_at)`**, called from `main.run()` only when **all** of these hold:
   - the scrape is `complete`;
   - the site is Shopify-platform (Firecrawl sites are out of scope, see below);
   - the number seen is **≥ 50%** of the site's current pushed+unpushed rows. A sudden drop means the site changed or is blocking us, not a mass delisting;
   - at most `MAX_MARK_SHARE = 30%` of the site's rows would be marked in one run. If more, it logs and skips, and someone looks.
3. **What it does:** for rows of that site with `in_stock=true` whose `product_url` was not in this run, set `in_stock=false` and every `variants[].in_stock=false`, plus `last_checked_at=now`. It does not delete anything or touch price.
   - These rows' `last_synced_in_stock` is still true, so `fetch_synced_products` picks them up as **urgent** in the next sync, which sets Shopify stock to 0 (all sizes once the product has a size signature).
   - It also writes a `product_changes` row (`change_type='delisted'`) so the change shows up in reports.
4. **Dry-run first:** env `MARK_DELISTED=dry` (the default for the first week) only logs counts and 10 samples per site. `MARK_DELISTED=1` writes.
5. Offline tests in `test_luxella_mcp.py`, with a fake scrape plus a fake Supabase:
   - partial scrape → no marks
   - below 50% seen → no marks
   - above 30% to mark → no marks
   - normal → only unseen in-stock rows are marked
   - a product seen again later → `save_products` sets it back to `in_stock=true`, which already happens today

## Out of scope
- The 18 dead Firecrawl sites. The founder chose separately to set their 3,898 live products to stock 0 (a one-off, with its own approval).
- Deleting or drafting products.
- Firecrawl sites in general: their scrape isn't a full-catalog listing.

## Acceptance checks
1. `ruff check .` and `test_luxella_mcp.py` pass, including the 5 new cases.
2. One dry-run scrape for `ONLY_SITE=jwpei`:
   - logs "would mark N" with N within about 10% of the audit (1,565 stale; how many are in stock is reported);
   - every sampled URL returns 404 or is sold out at the source (spot check of 5).
3. After `MARK_DELISTED=1` on jwpei only, the next sync zeroes those products on Shopify. A re-query of 10 random ones shows `available=0`.
4. The reviewer agent verdict is OK.

## Writes to production
- **Supabase:**
  - `products.in_stock` / `variants` / `last_checked_at` for unseen rows of a site that passed every guard.
  - New `product_changes` rows.
  - About 2.4k rows in total, spread over the sites' normal scrape runs.
- **Shopify:** indirect, through the normal sync (stock goes to 0).
- **Backup:** before the first `MARK_DELISTED=1` per site, save the rows' `id, in_stock, variants` to `/root/backups/<date>/delisted_<site>.json`.
- **Undo:** restore from the backup. The next scrape also restores any product that is listed again.

## Risks
- **The scrape misses real products** (pagination change, a filter like `is_sellable`, the 5,000 cap). Guarded by the completeness flag, the 50% seen floor and the 30% mark cap.
  - `is_sellable` skips (gift cards, GWP) are counted as "seen" so they aren't marked.
- **URL changes** (the brand renames a handle): the old row is marked sold out and the new URL arrives as a new product. That's acceptable; the dedupe fingerprint prevents a double listing.
- **Sites above 5,000 products** (none today, but aloyoga has 4,645 rows) will hit the cap. `complete=False` means no marks, and a warning is logged.

## Rollout
1. PR with code and tests, then review, then merge.
2. Dry-run for one week; the founder sees counts per site.
3. jwpei goes first with `MARK_DELISTED=1`, then verify.
4. All Shopify-platform sites.
