# Add real size variants to products listed on Shopify without sizes

**Goal:** Every product that has sizes at the source can be bought **by size** on Luxella, with per-size stock
kept correct by the existing per-size sync. Customers can no longer order a size-less "Default Title" item, and
products are no longer shown sold out while most sizes are available.

**Why now (read-only data, 2026-10-06):**
- A full Shopify bulk export (51,863 products) was joined with Supabase on `shopify_product_id`.
- **3,567 live (`active`) products** have **one "Default Title" variant** on Shopify, while the source has 2–27
  sizes.
  - By site: aloyoga 2,996, karllagerfeld 386, jwpei 70, staud 34, frye 28, verabradley 22, cultgaia 18, others 13.
  - **2,312** can be bought now **without choosing a size**. Wrong-size orders mean refunds and lost trust.
  - **975** (fresh scrape) are shown **sold out on Luxella while sizes are in stock at the source**. The
    product-level stock comes from the **first** size only. Example: "ALO Runner" (id 3860) has 17 of 24 sizes
    available but sells as sold out because size 3.5M is out. Those are direct lost sales.
- Found by the repair dry-run: these listings made up 97% of the "unmatched" sizes. PR #30 makes the repair
  skip them, so today they stay on the old first-size stock path.
- **The root cause isn't active any more.** Multi-size push landed 2026-08-30 (8ecfbc5). All size-less pushes
  fall between 2026-08-30 and 2026-09-14, apparently pushed before their size data was scraped. 7,730 products
  pushed since then have none. So this is a one-time backfill, not a code fix.
- The sizes are **already in Supabase** (`variants[]`: size, price, in_stock, sku). No LLM or extra scraping is
  needed.

## In scope
1. **`relist_sizes.py`** (new, one-time, dry-run default). For each pushed product whose Shopify listing has
   exactly 1 variant while `get_size_variants(row)` returns 2+ sizes, it:
   - builds the target sizes with **the same code new pushes use**: `shopify_push.get_size_variants` plus the
     push's per-size price → INR selling-price conversion, so labels and prices match a fresh push. 28 products
     have prices that differ by size;
   - via the Admin GraphQL API. The sequence was **proven in slice 1 on a throwaway draft product** on 2026-10-06
     (created, checked, deleted, and verified gone):
     1. `productOptionsCreate(options: [{name: "Size", values: [all sizes]}], variantStrategy: LEAVE_AS_IS)`.
        The placeholder "Title" option is replaced, and **the existing "Default Title" variant becomes the first
        size and keeps its variant id and inventory item**;
     2. `productVariantsBulkCreate` for the remaining sizes, each with `optionValues {optionName: "Size"}`, price,
        compareAtPrice, `inventoryItem {sku, tracked: true}`, and
        `inventoryQuantities [{locationId: 87267410093, availableQuantity: 10|0}]`. Stock is set at creation, so
        no extra inventory calls are needed for new sizes;
     3. for the first (existing) variant only: `productVariantsBulkUpdate` (price, compare-at, SKU of size 1),
        and `inventorySetQuantities` with CAS if its target (10 or 0) differs from the current quantity;
   - stock target per size: 10 if the size is in stock at the source and the price is > 0, otherwise 0;
   - updates Supabase: `last_synced_variant_stock` = `stock_signature(row)`, so `shopify_sync` keeps every size
     correct from then on. `shopify_variant_id` and `shopify_inventory_item_id` **stay the same**, because the
     old variant is now size 1;
   - **skips** stale rows (`scraped_at` older than 3 days, the same rule as the repair) and products whose
     source price is 0.
2. **Dry-run report:** counts per site, 20 samples (product, sizes, per-size target stock and price), and the
   number currently sold out that would become buyable.
3. **Backup before every write:** per product, the Shopify product id, the old variant (id, price, compare-at,
   SKU, inventory item, available) and the Supabase columns being changed. Saved as a run artifact (90 days) and
   copied to `/root/backups/<date>/`.
4. **Workflow `relist-sizes.yml`** (`workflow_dispatch`): inputs `dry_run` (default `1`), `limit` (default `1`),
   `verify`. Production secrets are passed by name only. I can push it myself now.
5. Offline tests in `test_luxella_mcp.py`:
   - the target builder (sizes, price per size, stock 10/0, price 0 → all 0);
   - the skip rules (stale, single size, price 0);
   - an apply call that writes the backup **before** any mutation;
   - the signature is written only after every Shopify step succeeds.

## Out of scope
- Re-scraping, or any LLM/Pydantic AI extraction (the data already exists).
- Changing titles, images, descriptions, collections or prices beyond the per-size prices.
- The 206 stale products. They stay as they are until re-scraped, then a later run picks them up.
- Products that are single-size at the source.
- Deleting or recreating products. The product id, URL/handle and SEO stay as they are.

## Acceptance checks
1. `ruff` and `test_luxella_mcp.py` pass, CI is green, and the reviewer's verdict is OK.
2. **Dry-run on real data:** about 3.3k fresh products in scope (3,361 expected, give or take scrape churn),
   with the per-site split matching above. 0 writes.
3. **`limit=1` on ALO Runner (id 3860)** or another currently-sold-out product with available sizes:
   - Shopify shows a Size selector with 24 sizes; 17 have stock 10 and 7 have 0;
   - the storefront product page is buyable in an in-stock size;
   - the old variant id is unchanged, now as size 1, and Supabase has a signature;
   - the backup file has the old variant.
4. Then 5, 50 and the rest. After the full run, re-export and check: **0** of these products still single-variant,
   and a sample of 30 has per-size stock equal to the source.
5. The next `shopify_sync` run handles them on the per-size path: `[SIZES]` lines only when sizes change, and no
   `[SIZES-SKIP]` for these products.

## Writes to production
- **Shopify:** **3,346 products** (offline re-plan on real data, 2026-10-06; aloyoga 2,856, karllagerfeld 317,
  jwpei 69…).
  - Per product: 1 option, N-1 new variants with stock set at creation, and 1 update to the existing variant,
    plus 1 CAS stock set if needed. No variant is deleted.
  - In total: **15,371 new variants**; 13,441 sizes in stock; **962 products currently sold out become buyable**.
  - That's about 11k API calls through GitHub Actions with the existing Shopify app secrets.
- **Supabase:** 1 column per product (`last_synced_variant_stock`).
- **Backup:** described above, saved before each product's write.
- **Undo, per product (`--restore <backup>`, or workflow input `restore_run_id` which downloads that run's
  backup artifact):**
  - one `productOptionsDelete(Size, strategy: POSITION)` removes the added sizes, and the original variant
    becomes "Default Title" again with the **same id**. This was tested on a second draft product on 2026-10-06
    (deleted afterwards);
  - then its price, SKU and stock are restored from the backup and the signature is cleared.

## Risks
- **Shopify mutation semantics:** **resolved in slice 1.** On a draft test product (DRAFT, never published,
  deleted afterwards):
  - "Title" was replaced by "Size";
  - the original variant `67140549771437` became "3.5M/5W" with the same id and inventory item;
  - 3 new sizes were created with price ₹25,699, MRP ₹39,599, distinct SKUs, tracked, and stock 10/10/0;
  - the size order was kept.
- **Open carts and external feeds:** existing carts keep working, because the original variant id survives as
  size 1. Google or Meta feeds see new variant items for the added sizes, which is expected.
- **Label quirks:** sizes like "6 | US" (jwpei), "Small - Medium" and "+1.25" (verabradley). These use the same
  labels a new push would create. The dry-run samples show them for a check by eye.
- **Rate limits and partial failure:** the script is resumable. A product counts as done only once the
  signature is written, and a re-run skips products whose Shopify listing already has >1 variant.
- **A mid-run customer order on the old variant.** It's rare, and the order is kept; only that product's stock
  path changes.

## Rollout
1. Slice 1: confirm the mutation sequence on a throwaway draft product, then delete it (founder OK for the
   create/delete).
2. Slice 2: code, tests and the workflow as a PR (reviewer, CI).
3. Dry-run; the founder reviews the counts and samples.
4. `limit=1` (ALO Runner) → check the storefront → 5 → 50 → all, each with the founder's OK.
5. Re-export and verify (check 4), then watch the next 2 sync runs (check 5).
