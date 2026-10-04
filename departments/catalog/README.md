# Catalog department

## Mission
Keep the catalog accurate and beautiful: scrape, clean, enrich, photograph (bg removal), publish to Shopify, fix drift.

## Lead agent
curator: read-only by default, risky actions via approval-queue skill.

## Tools it may use
luxella_mcp (query, price_report, check_availability, sync_catalog), Shopify dev MCP, rembg scripts

## Human approval gates
- Any write to Shopify or Supabase (confirm=True)
- any schema change
- enabling any schedule

## KPIs (reported daily via kpi-report)
- products live
- OOS-but-live
- synced today
- failed syncs
- photo quality score

## Auto-approved actions (only when evals are green)
Dry-run reports, drift reports

## Evals
evals/curator.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
