# Sourcing department

## Mission
Find the best luxury inventory before competitors: drops, price cuts, restocks and supplier deals at a landed cost that protects margin.

## Lead agent
scout: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Firecrawl, changedetection.io, Supabase (read), web search

## Human approval gates
- Any purchase
- any new supplier
- any deposit

## KPIs (reported daily via kpi-report)
- new finds
- price drops caught
- buys proposed
- buys approved
- average discount vs retail

## Auto-approved actions (only when evals are green)
Posting a daily finds digest to the founder

## Evals
evals/scout.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
