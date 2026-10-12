# Slice 4 — capture real source compare-at

**Goal:** Real crossed-out prices appear on the store only when the *brand's own site* shows a genuine discount — by capturing the source's compare-at and feeding it into pricing (which already does real-or-null since PR #43).

**Why now:** PR #43 makes `calculate_pricing(source_compare_at=...)` emit a strike only for a real anchor, but `db.py` doesn't yet pass one, so every product saves with `compare_at=None`. Without Slice 4 there are **no** strikes at all (which is correct but means no "Deals"); with it, real brand markdowns show and a Deals section becomes honest. The current on-store "~35% off everywhere" is the old fake markup; it is removed by `recompute_compare_at.py --apply` and never re-added once this ships.

**In scope:**
- New Supabase column `products.source_compare_at_price numeric` (nullable).
- Scrapers record the source/original price the brand site shows next to the sale price (the strikethrough on the brand PDP), into that column. Null when the source shows no discount.
- `db.py` passes `source_compare_at=row["source_compare_at_price"]` into `calculate_pricing(...)` on save/update.
- Backfill (optional, later): re-scrape to populate `source_compare_at_price` for existing live products.

**Out of scope:**
- The bid-pricing agent (separate project).
- Changing `selling_price_inr` (historical FX — never recomputed).
- Any new "sale" tag or fake urgency.

**Acceptance checks:**
1. `ALTER TABLE products ADD COLUMN source_compare_at_price numeric;` applied (founder, SQL Editor).
2. `test_luxella_mcp.py` passes (add a case: a scraped row with a real source discount → `compare_at_price_inr` set, strike above selling, ≤85% off; a row with no source discount → `None`).
3. Dry-run a scrape of ~5 products from a site known to have markdowns: `source_compare_at_price` populated for the discounted ones, null for full-price ones; nothing written to Shopify in dry-run.
4. After a real (confirmed) scrape run: `productsCount(status:active inventory_total:>0 variant_compare_at_price:>0)` reflects only genuinely-discounted products (not the whole catalogue).

**Writes to production:** Supabase `products.source_compare_at_price` (new column + scraper writes) and, downstream, Shopify compare_at via the existing sync. Dry-run + confirm per safe-writes. Undo: set column null / `recompute_compare_at.py --apply`.

**Risks:** source price parsing wrong → bad anchors. Mitigated by the 85% bad-anchor cap already in `pricing.py` (absurd implied discount → dropped to None).

**Rollout:** ALTER TABLE → scraper change behind dry-run → scrape ~5 (verify) → one site full → all. Then build the **Deals** collection (smart: `variant_compare_at_price > 0` + inventory>0, sorted by biggest % off) and the homepage Deals rail.

**Founder actions:** (1) merge PR #43, (2) `ALTER TABLE` the column, (3) approve the first small scrape run.
