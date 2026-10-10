# Compare-at: show a crossed-out price only when the brand itself discounts

**Goal:** a crossed-out "was" price appears on a Luxella product **only** when the source brand site is actually
selling it below its own original price, converted with our landed-cost formula — never a fake blanket "35% off".

**Why now (founder decision (b), 2026-10-10; BRAND.md §8, DECISIONS.md):**
- `pricing.py` forces a discount on **every** product: `compare_at_price_inr = selling / (1 − 0.35)`
  (`MIN_DISCOUNT_PERCENT = 0.35`). So all ~20k live products show a fake "~35% off".
- The storefront theme already **hides** the strike price (storefront-uplift Slice 1, live). This build supplies
  the real data so a strike can come back only when it is true.
- Scrapers capture only the current `price` — never the source's own original / was / list price.

## In scope
1. **Scrapers capture the source original price.**
   - In each scraper's extraction, also read the brand's own strikethrough / was / list / regular / compare price
     when the source shows one: `firecrawl_scraper.py` (schema ~line 61), `scrapegraph_scraper.py`,
     `scraperapi_scraper.py` (JSON-LD `offers`; also common `listPrice` / `priceSpecification` / "was" markup),
     `shopify_scraper.py` (`compare_at_price` from the source Shopify product).
   - Normalise to a number in the **source currency** (same currency as `price`). Store as a new field
     `source_compare_at` on the scraped item.
   - Only keep it when it is a real higher anchor: `source_compare_at > price`. Otherwise `null`.
2. **Supabase:** new nullable column `products.source_compare_at_price` (numeric, source currency). No other schema
   change (currency is already stored). Written by the scrape upsert alongside `price`.
3. **`pricing.py`:**
   - **Remove** `MIN_DISCOUNT_PERCENT` and `calculate_compare_at_price()`'s forced formula.
   - `calculate_pricing(...)` takes a new optional `source_compare_at=None`.
   - If `source_compare_at` is a real anchor (`> price`): compute `compare_at_price_inr` by running the **same**
     landed-cost + margin + round-to-99 pipeline on `source_compare_at` (so the strike is the landed price of the
     brand's own original). Guard: only keep it if the result is `> selling_price_inr`.
   - Else: `compare_at_price_inr = None` (one price, no strike).
4. **Push / sync clear the strike when it is gone.**
   - `shopify_push.py` already sends `compare_at_price` (null when absent — verify it sends an explicit null/empty
     so the field is cleared, not left stale).
   - `shopify_sync.py` `update_variant()`: today `if compare_at_price:` only ever **sets** it. Change so that when
     `compare_at_price_inr` is `None` it **clears** the Shopify `compare_at_price` (send `""`/null), and
     `mark_synced` records the cleared value, so the fake 35% strike is removed on the next sync.
5. **One-time recompute + dry-run on live prices.**
   - A script recomputes `selling_price_inr` (unchanged) and `compare_at_price_inr` (now real-or-null) for all
     products from their stored source data, and reports the dry-run before writing.
   - selling_price must **not** change for any product (only compare_at changes) — assert this in the dry-run.

## Out of scope
- Changing the **selling price** or the margin/FX/tax/shipping formula. Only the compare-at (anchor) changes.
- Re-scraping the whole catalog. Existing ~20k products have no `source_compare_at` until their site is next
  scraped, so their compare-at becomes **null** (one price) now; real strikes appear as sites are re-scraped.
- Deal Finder logic (it already reads source price changes separately).
- Re-enabling the theme strike markup (storefront-uplift handles display; it already supports a real compare-at).
- The MRP/Legal-Metrology wording question (we keep Shopify's "Compare at price", not a literal "MRP" claim).

## Acceptance checks
1. `python test_luxella_mcp.py` passes (offline self-check), including new pricing cases.
2. **Unit (pricing.py):**
   - no `source_compare_at` → `compare_at_price_inr is None`;
   - `source_compare_at <= price` → `None`;
   - `source_compare_at > price` → a landed-formula compare-at `> selling_price_inr`, with the same `...99` rounding;
   - `selling_price_inr` identical with and without `source_compare_at` (anchor never moves the real price).
3. **Scrapers:** on a saved sample page that shows a brand discount, the extractor returns `source_compare_at`
   > `price`; on a full-price page it returns `null`. (Fixture-based, offline.)
4. **Dry-run (no writes):** prints, for all products: how many would get a **real** strike, how many become
   **one price** (null), and asserts `selling_price_inr` unchanged for 100%. Sample 20 before→after.
5. After the batched apply (founder-approved): `products` where `compare_at_price_inr is not null` are only those
   with `source_compare_at > price`; spot-check 10 on the live store show a true crossed-out price, the rest show
   one price.
6. Shopify: a product that previously had the fake strike and has no real discount now shows **no** compare-at
   (verify `compare_at_price` is null on its variant).

## Writes to production
- **Supabase:** one new column; then an UPDATE of `compare_at_price_inr` (→ real value or null) for ~20k products.
  Dry-run first; apply in batches ≤ 1000 by id (safe-writes). Backup the current
  `id, compare_at_price_inr` to `/root/backups/<date>/compare_at_before.json` (chmod 600).
- **Shopify:** the daily sync clears/sets each variant's `compare_at_price` from Supabase on its normal run; no
  separate bulk Shopify write in this spec (the sync does it incrementally, retry-safe). Undo: restore the backup
  column and re-sync.
- **No price, stock or product-status changes.**

## Risks
- **Bad source anchor** (a "compare at" that is marketing fluff, not a real former price) → an inflated fake strike,
  the exact thing we're removing. Mitigation: only accept `source_compare_at > price`, and require the computed
  strike `> selling_price_inr`; log the top 20 largest implied discounts in the dry-run for the founder to eyeball.
- **Selling price drift.** If the refactor accidentally moves `selling_price_inr`, live prices change. Mitigation:
  acceptance #2/#4 assert selling price is byte-identical; dry-run fails loudly if any differ.
- **Stale strikes left on Shopify** if the sync doesn't clear null. Mitigation: item 4 + acceptance #6.
- **Scraper coverage uneven** across ~40 sites; some won't expose a was-price. Acceptable: those show one price.

## Rollout
1. Founder approves this spec.
2. Planner slices, in order:
   1. `pricing.py` refactor (real-or-null compare-at) + unit tests — no production effect yet.
   2. Supabase column + the recompute script with dry-run.
   3. push/sync clear-on-null + sync test.
   4. scraper capture of `source_compare_at` (per scraper) + fixtures.
3. Dry-run → founder reviews counts + the top-20 discounts → small batch (5) → full, re-checking at each step.
4. Verify on the live store (acceptance #5/#6).
