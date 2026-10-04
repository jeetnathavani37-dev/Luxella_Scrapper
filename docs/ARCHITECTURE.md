# Architecture

## Environments
- Dev machine: VPS (Contabo, Ubuntu) reached via SSH with a key. Work happens inside tmux (alias: lux).
- Source of truth for data: Supabase (project ref bkxzkrbhqpwosqecndnx).
- Storefront: Shopify (luxella-9299.myshopify.com).
- Code: GitHub repo Luxella_Scrapper. Changes go through PRs.

## Data flow
Retailer sites -> scrapers (Scrapy/Firecrawl) -> Supabase `products` -> shopify_push / shopify_sync -> Shopify

## Components
- Scrapers: per-brand scripts in Luxella_Scrapper.
- luxella_mcp.py: MCP server exposing 4 catalog tools to Claude Code. Writes only via sync_catalog with confirm=True.
- shopify_push.py / shopify_sync.py: existing push/sync logic. MCP calls these instead of duplicating them.
- Background removal: shopify_bg_removal.py and auto_pilot.py (PR #5). Columns bg_removed, bg_removed_at on products.
- GitHub Actions: scheduled pipelines. New schedules ship disabled until tested by hand.

## Secrets
Stored only in ~/.luxella.env (chmod 600). Variable names: SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ACCESS_TOKEN, SHOPIFY_STORE_DOMAIN, SHOPIFY_TOKEN, FIRECRAWL_API_KEY. Never committed, never printed.

## Known caveats
- Two Supabase projects exist in different organizations. The Luxella project is the one above. Verify the project ref before any query.
- The claude.ai Supabase connector may point at a different project than the repo MCP.

## Target shape (AI-led Luxella)
Agents (Claude Agent SDK) -> MCP tools (read-only by default) -> approval queue -> human -> write
Every run is logged and traceable.
