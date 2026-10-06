# Sync stock for every size, not just the first

**Goal:** A product's stock on Shopify matches the source for every size, so customers can't buy a size (or a
whole product) that is sold out at the retailer.

> **Revised 2026-10-05 after a measured sample. This replaces the numbers below.**
>
> `products.in_stock` comes from the **first size** only (`shopify_scraper.py`), so the "9,151 out of stock"
> figure was wrong. Most of those products just have a sold-out first size, and Shopify correctly sells the
> other sizes.
>
> I compared 30 random pushed multi-size products, size by size, between Shopify and the source
> (`variants[].in_stock`). 27 had real sizes; 3 Alo products exist on Shopify as a single variant.
> - **10 of 27 products (37%) have at least one wrong size.**
> - 14 of 229 sizes (6%) are wrong. **8 are buyable on Shopify but sold out at the source**; 6 are the other way
>   round, which means lost sales.
> - Extrapolated, that's roughly 8k products and about 1.3k buyable-but-sold-out sizes across 22k products. The
>   repair dry-run will give exact numbers.
>
> Cause: push sets per-size stock once, then sync only ever touches the first variant. Size changes after push
> never reach Shopify.
>
> Rule change: the targets use **only per-size `in_stock` plus price > 0**, never the product-level flag.
> Using that flag zeroed 18 available sizes on 2 sandals, which were then restored.
>
> **Original text (numbers superseded):** On 2026-10-05, Supabase shows 22,331 pushed multi-size products. Of
> those:
- **9,151 are out of stock at the source**, and the sync recorded them as out of stock. But it only zeroed the
  first size; every other size kept stock 10. A random check of 12 Cult Gaia products on Shopify found **12 of 12
  still buyable**, with 10–70 units across other sizes.
- **5,147 are in stock at the source but have some sizes sold out there.** Those sizes are likely still buyable
  on Shopify.
- Found while fixing the drift list: the Vince Camuto Pendreya and Saprenda sandals went 110 → 100 instead of
  → 0. They were fixed by hand: 21 sizes set to 0 (backup `/root/backups/2026-10-05/sandals_inventory_before.json`).

**Root cause:** `shopify_sync.update_stock()` only touches `shopify_inventory_item_id`, which is the first
variant's. Supabase stores no inventory-item ids for the other sizes. Per-size stock (`variants[].in_stock`) is
scraped but never synced after the push.

## In scope
1. **`shopify_sync.py`:** for products with 2 or more sizes, read the Shopify product's variants
   (`GET /products/{id}.json?fields=variants`; matched by `option1` = size). Then set each size's available
   quantity: 10 if the scraped size `in_stock` is true and price > 0, otherwise 0. Never use the product-level
   flag. Sizes at 1–9 (after customer orders) are left alone and reported. This runs only when the stock
   signature changed. The signature is price_ok plus per-size stock, stored in a new
   `last_synced_variant_stock` text/JSON column so unchanged products cost no extra calls.
   - Sizes on Shopify with no matching scraped size are left alone and reported. If half or more of a product's Shopify sizes are unmatched (a label change), nothing is written for it. The repair aborts above 2% unmatched.
   - Uses `inventorySetQuantities` with `changeFromQuantity` (CAS) and a fresh `@idempotent` key per call, up to 250 sizes per call.
2. **`luxella_mcp.price_stock_changes`:** mirror the rule for the preview, and add a test case.
3. **One-time repair, `repair_variant_stock.py`:**
   - Selects pushed multi-size products whose stored signature is empty, i.e. all 22k.
   - Reads Shopify variants and builds the per-size target.
   - **Dry-run by default.** It prints totals (products and sizes going 10→0 or 0→10) and 20 samples, and
     writes a backup of the current quantities.
   - With `--confirm`, it applies in batches. `--limit 5` comes first, then larger batches.
   - It writes the signature after each product so the next sync run skips it.

## Out of scope
- Changing quantities other than 0/10 (real stock counts).
- Drafting or deleting products.
- The 5 Supabase rows whose Shopify product no longer exists (separate step, needs its own approval).
- Price per size, which already comes from variants at push time.

## Acceptance checks
1. `test_luxella_mcp.py` passes, including a new multi-size preview case.
2. **Unit test with a fake Shopify:** for a product out of stock at the source with 13 sizes, all 13 are set to
   0. For a product in stock with sizes 6 and 7 sold out, only those two are 0 and the rest are 10. An unchanged
   signature makes no Shopify call.
3. **Repair dry-run on real data** (read-only) shows the counts. The 12 sampled Cult Gaia products appear with
   their in-stock sizes set to 0.
4. After `--confirm --limit 5`, a Shopify re-query shows those 5 products with the expected per-size stock.
   They're in the backup.
5. After the full repair, a sample of 30 random multi-size products matches source per-size stock on Shopify,
   with 0 mismatches.
6. The `reviewer` agent verdict is `OK to merge`.

## Writes to production
- **Schema:** one new column, `products.last_synced_variant_stock` (text, nullable). It's additive and undone
  with `drop column`. This is shown to the founder before it runs.
- **Shopify:**
  - About 9,151 products' extra sizes go to 0 (product out of stock at the source).
  - Some sizes of the 5,147 partial products go to 0, and a few might go 0→10 where the source has stock.
  - Exact numbers come from the dry-run.
- **Backup:** `/root/backups/<date>/variant_stock_before.jsonl` (per inventory item, before value).
- **Undo:** replay the backup with the same script (`--restore <file>`).

## Risks
- **The repair zeroes sizes that are actually in stock.** For example, a scrape bug or a size naming mismatch
  ("US 7" vs "7"). Mitigations:
  - Dry-run samples.
  - A `--limit 5` first batch.
  - Unmatched sizes are only reported in the dry-run, with a count shown before confirm.
- **Shopify rate limits.** GraphQL cost runs to about 22k reads and roughly 100 writes of 250. The script uses
  cost-aware throttling and resumes from its checkpoint (the signature column).
- **Extra sync calls.** These only happen when a signature changes, so it's a few hundred per run at most.
- **Stale scrape data drives the repair (added 2026-10-06).** 2,912 of 22,697 candidates were last scraped 3 to 30+
  days ago. Most were delisted at the source, and the dead-site sizes were set to 0 on 2026-10-05. Repairing them
  from old data would set sold-out or removed sizes back to 10. Mitigation:
  - `--max-age-days` (default 3): rows whose `scraped_at` is older, or null, get no stock writes and no signature.
  - The skipped count is shown as `skipped_stale` in the dry-run report.
  - Known gap (reviewer, 2026-10-06), a follow-up slice:
    - `mark_unseen_sold_out` sets every size to false but leaves `scraped_at` old. A delisted multi-size row
      therefore stays skipped with a null signature.
    - `shopify_sync`'s old path then zeroes only the first size on Shopify.
    - Fix: let `split_fresh` accept a stale row when **all** its sizes are sold out. Every target is then 0, and
      a 0 can never sell a missing item. Or have delisted-marking send the row through `sync_sizes`.
    - This doesn't affect the 18 dead sites, whose sizes were zeroed per inventory item on 2026-10-05.

## Rollout
1. **Add the schema column first (with approval).** If the code is merged before the column exists:
   - sync and the MCP preview crash (they select a missing column)
   - push creates duplicate Shopify products (it writes the column after the product is created, the write
     fails and the row stays unpushed)
2. Code plus tests, as a PR. Review, then merge **only after step 1 is verified**.
3. Repair: dry-run, show the counts, `--limit 5`, verify, then 500, verify, then the rest.
4. Watch the next 2 sync runs and the drift list.
