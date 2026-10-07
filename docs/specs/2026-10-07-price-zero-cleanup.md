# Price-0 products: take the last ones off the store, and make the daily report count the real risk

**Goal:**
- No product whose source price is 0 or unknown can be bought on Luxella, or shows a fake ₹799 price.
- The daily report's "price 0 live" alarm counts only the products a customer can **actually buy**, so it goes
  green once the risk is gone instead of nagging forever.

**Why now (read-only data, 2026-10-07):**
- **Supabase:** 237 pushed products have `price` 0 or null.
  - By site: victoriabeckham 178, aloyoga 19, goat 17, stanley1913 9, ninashoes 7, adanola 2, verabradley 1,
    stockx 1.
  - All of them still have Supabase `shopify_status = active`. That was left on purpose on 2026-10-04, because
    `shopify_publish` re-publishes anything that is not `active`.
- **Shopify, nodes query on all 237** (results in `/tmp/claude-0/p0shopify.jsonl`):

  | Shopify state | Count | Can a customer buy it? |
  |---|---|---|
  | ACTIVE, inventory > 0 | **1** (Carmen Sol "Seven Jeans – Second Chance", ₹1,299, stock 10) | **YES**, the only real money risk |
  | ACTIVE, inventory 0 | **186** (177 at **₹799**, mostly Victoria Beckham "look-N" / "ss27-look-N" pages, 7 Nina shoes at ₹3,199) | No, but the store shows them as "Sold out ₹799": a wrong price, and pages that aren't products |
  | DRAFT | 50 (the 2026-10-04 cleanup) | No |

- **Where the guards stand:** PR #15/#16 already stop push, sync and publish from creating or reviving price-0
  products, and sync sets their stock to 0. That is why only 1 is buyable. The Carmen Sol item is a "second
  chance" resale listing that slipped through. The source shows no price.
- **The report is misleading:** it shows "price 0 live: 237 (target 0)" as **bad every morning**, while the real
  buyable count is 1.

## In scope
1. **Shopify: set the 187 ACTIVE price-0 products to DRAFT.** That is the 1 buyable product plus the 186
   "Sold out ₹799" pages.
   - **Backup first** to `/root/backups/2026-10-07/price0_drafted.json`: Shopify id, Supabase id, site, name,
     status, inventory, price.
   - **Dry-run list** shown to the founder: count per site, plus 20 samples.
   - **Apply:** the Shopify MCP `bulk-update-product-status`, as on 2026-10-04, in batches of 40 or fewer.
   - **Founder approval** for the batch (safe-writes).
   - **Supabase is not changed.** `shopify_status` stays `active`, so `shopify_publish` won't re-publish them (it
     also skips price 0 since PR #15).
2. **Daily report metric fix.**
   - Replace "price 0 live" (a Supabase count) with **"price 0 buyable on Shopify"**: of the pushed price-0
     products, how many are Shopify ACTIVE with inventory > 0.
     - A read-only `nodes` query over the price-0 ids, 50 per call (about 5 calls).
     - Target 0, so it is a bad item if above 0.
     - It is `n/a` until the server has Shopify keys (reminder #29). Until then, a read-only "price-0 rows:
       N" info line stays, so the number is still visible.
   - Offline tests:
     - 0 buyable is ok;
     - 1 buyable is bad and names the product id;
     - missing Shopify gives n/a, not 0.

## Out of scope
- Fixing the scrapers' price parsing for Victoria Beckham, ALO, GOAT, Nina and Stanley. PR #16 fixed the main
  causes. The "look-N" pages are lookbook pages, not products, and should be filtered in the scraper in a
  separate spec.
- Deleting the products. DRAFT is reversible; deletion is not.
- Re-pricing them by hand.

## Acceptance checks
1. **Backup** file exists with 187 rows (600 permissions).
2. **After apply:**
   - `productsCount(query: "status:active")` falls by 187, within ±5 of drift;
   - a re-run of the nodes query over the 237 ids shows **0 ACTIVE** (237 DRAFT);
   - the Carmen Sol URL returns 404 on the storefront.
3. **The next sync run** (`Sync Shopify Prices & Stock`) does not re-activate them. Sync never sets status, and
   publish skips price 0. Re-check 0 ACTIVE after one sync run.
4. `ruff` and `test_luxella_mcp.py` pass, CI is green, and the reviewer's verdict is OK for the report change.
   The next morning's report shows "price 0 buyable: 0" (or n/a without Shopify keys) and no longer "237 bad".

## Writes to production
**Shopify:** the status of 187 products goes ACTIVE → DRAFT. There are no Supabase writes.

**Undo:** the backup lists the 187 ids. `bulk-update-product-status` → ACTIVE restores them exactly.

## Risks
- **Hiding a product that is really for sale.** The Carmen Sol item is the only buyable one, and its source price
  is unknown. Selling it at ₹1,299 could be a loss either way. It stays DRAFT until a real price is scraped; the
  founder can re-activate it from the backup.
- **SEO.** The 186 are "Sold out ₹799" lookbook pages and odd items, not real products with value. Unpublishing
  removes junk pages. Earlier decision (a), to keep sold-out items live for SEO, covered real products at real
  prices, not these.
- **The MCP blocks the bulk status change.** It worked on 2026-10-04. If it is blocked now, the founder gets the
  admin steps (Shopify admin → filter → bulk "Set as draft").

## Rollout
1. The founder approves the spec.
2. Dry-run list plus backup. The founder says "haan".
3. Apply in batches of 40 or fewer, then verify (checks 2 and 3).
4. PR for the daily report metric: reviewer, CI, founder merge.
