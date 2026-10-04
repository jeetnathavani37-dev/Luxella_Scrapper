# PRD: Luxella

## Vision
An AI-led luxury resale and concierge business. Agents handle sourcing, catalog, pricing support and
customer conversations. The founder approves every decision that affects money or a customer.

## Users
- Founder (operator): needs less manual work, fewer mistakes, clear daily reports.
- Customers (HNI buyers, resale clients): expect trust, speed and a quiet, premium experience.

## Current products
1. Catalog pipeline (Luxella_Scrapper): scrapes 60+ brands, stores in Supabase, pushes to Shopify.
2. Luxella MCP server (luxella_mcp.py): tools luxella_query, luxella_price_report, luxella_check_availability, luxella_sync_catalog.
3. Background-removal automation (PR #5): cleans product photos.
4. Luxella Trove: peer-to-peer luxury resale marketplace (in design).

## Goals (next 90 days)
- Fix catalog drift (products out of stock at source but still live on Shopify).
- Ship background removal safely, tested at small batch sizes first.
- Stand up one approval-based agent end to end, with logging and evals.
- Establish the design system and one polished storefront screen.

## Non-goals (for now)
- Fully autonomous customer messaging.
- Autonomous price changes on the live store.
- Merging the bid-pricing agent into the catalog tools.

## Success metrics
- Zero unreviewed writes to production.
- Out-of-stock-but-live products: target 0, checked daily.
- Every agent has a spec, an eval set and run logs before it goes live.

## Open questions (fill in)
- Pricing/markup rule for the live store.
- Which channel gets the first agent (DMs, sourcing alerts or order tracking).
