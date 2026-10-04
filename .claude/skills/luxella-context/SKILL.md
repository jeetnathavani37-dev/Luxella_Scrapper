---
name: luxella-context
description: Map of the Luxella_Scrapper repo and its systems - which script does what, data flow, Supabase/Shopify tables and fields, scheduled workflows, known limits and past incidents. Use when starting any Luxella task, answering "where/how does X work", or before changing scrapers, push/sync, pricing or the MCP server.
---

# Luxella context

## Data flow
Retailer sites → scrapers → Supabase `products` (+ `product_changes` log) → `shopify_push` / `shopify_sync` / `shopify_publish` → Shopify store `luxella-9299.myshopify.com`.

## Scraping
| File | Role |
|---|---|
| `main.py` | Entry point for `scrape.yml` (every 6 hours; `SCRAPE_GROUP` unset, so the default `free`) and `scrape-firecrawl.yml` (daily). Orders sites stalest-first, stops starting new sites after `MAX_RUN_MINUTES` (45), batch-saves per site. |
| `sites.py` | Site configs: `platform: shopify`, `use_firecrawl` or browser. `use_scraperapi` and `use_scrapegraph` are supported by `main.py` but no site uses them now. `is_marketplace` means the brand comes from the product name. |
| `shopify_scraper.py` | Reads the public `/products.json` (most sites). Skips $0, GWP and loyalty items, gift cards and fees. |
| `firecrawl_scraper.py`, `scrapegraph_scraper.py`, `scraperapi_scraper.py`, `extract.py` | AI and browser extraction for non-Shopify sites (GOAT, StockX…). |
| `db.py` | `save_products()` batch save; `save_product()` single. Matches by `(site, product_url)`. Price ≤ 0 means unknown. Logs price and stock changes to `product_changes`. |
| `pricing.py` | `calculate_pricing(price, category, currency)` → INR landed cost, selling price and compare-at. There's no floor constant, but shipping, margin and `round_to_99` turn price 0 into a category minimum (₹499 watches, ₹799 clothing/activewear/beauty, ₹1,299 handbags, ₹3,199 shoes). That's why price 0 must never reach it. |
| `brand_extractor.py` | `display_brand()`: slug → real brand name; marketplace → brand from the title. |
| `dedup_utils.py` | `compute_fingerprint(brand, name)` for duplicate detection. |

## Shopify sync
| File | Role |
|---|---|
| `shopify_push.py` | Creates new products (price > 0, not duplicate). Title, vendor and tags come from `display_brand`. |
| `shopify_sync.py` | Updates price, compare-at and stock of pushed products. Stock mismatches go first. Price-0 products get stock 0. |
| `shopify_publish.py` | Re-activates non-active rows (skips price 0). |
| `auto_pilot.py` | Loops push, sync and image backfill. |
| `shopify_image_backfill.py`, `shopify_bg_removal.py` | Gallery images and background removal. |
| `rephrase_descriptions.py` | Rewrites descriptions with Gemini (free tier). |
| `backfill_shopify_vendor.py` | One-time fix for vendor and title. Its workflow YAML is not added yet (the founder adds it). |
| `luxella_mcp.py` | MCP server with 4 tools: `luxella_query`, `luxella_price_report`, `luxella_check_availability`, and `luxella_sync_catalog` (dry-run plus `preview_id`; `confirm=True` runs push and sync). Test: `test_luxella_mcp.py`. |

## Key fields in `products`
- **Identity:** `id`, `site`, `sku`, `product_url`
- **Product:** `name`, `brand`, `category`, `currency`, `price` (source), `in_stock`, `variants`, `image_urls`, `description`
- **Pricing:** `selling_price_inr`, `compare_at_price_inr`, `landed_cost_inr`
- **Timestamps:** `scraped_at`, `last_checked_at`
- **Shopify state:** `pushed_to_shopify`, `shopify_product_id`, `shopify_variant_id`, `shopify_inventory_item_id`, `shopify_status`
- **Sync state:** `last_synced_price_inr`, `last_synced_in_stock`, `is_duplicate`, `product_fingerprint`

## Known limits
- **Supabase reads:**
  - PostgREST returns at most 1,000 rows. Page by `id`.
  - `ORDER BY scraped_at` or `changed_at` times out (no index).
- **Supabase MCP:** the `mcp__supabase__*` connector can point at another org's project (access denied). Use the repo's Luxella MCP, or a script that loads `~/.luxella.env` without printing it.
- **This server's IP:**
  - It gets 429 from Shopify stores and the storefront, so live scrape tests belong on GitHub Actions (`ONLY_SITE` dispatch).
  - ghcr.io pulls over IPv6 fail.
- **Shopify MCP:** works for reads and many writes, but blocks bulk mutations, unpublish, theme publish and live-theme writes.
- **GitHub from this server:** no git credentials. Push with the GitHub MCP `push_files`; it can't write `.github/workflows/*`.

## Incidents to remember (2026-10-04)
- **PR #15:** price-0 products were live at ₹799 (GOAT Jordans, Alo GWP). 50 were set to Draft; push, sync and publish now guard against price 0.
- **PR #16:** sku collisions (697 skus, about 2,900 URLs, e.g. frye `_used`) overwrote one row and logged fake drops. Products now match by URL.
- **PR #17:** scrape runs always hit the 60-minute timeout. Fixed with batch save plus a paged staleness query.
- **Collections:** tag rules never matched the scraper's tags. They now use product-type rules with clean handles.

## Other places
- **Windmill:** on demand at `127.0.0.1:8100`, workspace `luxella`. Scripts `f/luxella/brand_repush` and `price_drop_report` mount this repo read-only.
- **Backups:** `/root/backups/<date>/`.
- **Design:** `docs/DESIGN.md`. The staged theme JS is in `/root/luxella-theme-gsap`.
