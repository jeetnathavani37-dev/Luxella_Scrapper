---
name: safe-writes
description: The required procedure for any write to Shopify or Supabase in Luxella (create, update, delete, publish, status, price, stock, collections, bulk jobs) - dry-run first, backup, explicit confirm, small batch, verify. Use before running or writing any code that changes production data.
---

# Safe writes

Production is the live Shopify store (luxella-9299.myshopify.com) and the Supabase `products` and
`product_changes` tables. Real customers can buy what's live.

## The procedure (every time)
1. **Dry-run first.** Code defaults to `dry_run=True` or `confirm=False`. The dry-run prints:
   - how many rows or products would change
   - a sample of 5–20 with before → after
   - a preview or batch id if the tool has one, e.g. `luxella_sync_catalog` returns a `preview_id`
2. **Founder approval.** Show the dry-run in Hinglish: what, how many, and how to undo it. Wait for an explicit yes. Approval covers only that batch; a new batch needs a new OK.
3. **Backup** before destructive or bulk changes. Save the current state to `/root/backups/<yyyy-mm-dd>/<what>.json` (chmod 600): IDs plus the fields you're about to change.
4. **Small batch first.** Run about 5 items, verify, then the rest. Use chunks of 200 or fewer for Supabase `.in_()`, and aliased mutations of 40 or fewer per call for Shopify.
5. **Verify after.** Re-query and show the count: before, expected and actual.
6. **Record it.** Add a line to the PR or `docs/DECISIONS.md` for policy changes. Store backup paths in memory for one-off fixes.

## Code rules
- New write paths: dry-run by default, plus a confirm flag (`confirm=True`; for new workflows, a `dry_run` input defaulting to `1`. Existing workflows don't have one yet).
- Never let price 0 or None reach Shopify. Treat it as "unknown" (PRs #15 and #16).
- Match products by `(site, product_url)`, not sku alone (PR #16).
- Page every Supabase read beyond 1,000 rows by id. PostgREST silently caps responses at 1,000.
- Don't `ORDER BY scraped_at` or `changed_at` on large tables; there's no index, so it times out. Order by `id` and filter instead.
- New cron schedules ship **disabled** until tested by hand at a small batch.

## Known blocks (don't route around them)
- The Shopify MCP blocks:
  - `bulkOperationRunMutation`
  - `publishableUnpublish`
  - theme publish
  - writes to the live theme
- Auto-mode can block mass deletes.

When something is blocked, tell the founder and give the admin steps instead.

## Real examples (2026-10-04)
- **Zero-price products:** 50 in-stock products were set to Draft.
  - Backup first: `/root/backups/2026-10-04/zero_price_drafted.txt`.
  - Then `bulk-update-product-status`, followed by a count check.
- **Collections:** rules were switched to product type. Backup in `collections_before_fix.json`; redirects were created with `redirectNewHandle`.
- **Kicksmachine and Luxlair removal:**
  - Full backups first.
  - Aliased `productDelete` at 40 per call, at most 2 calls in parallel.
  - Verified with `productsCount` = 0.
