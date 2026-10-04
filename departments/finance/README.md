# Finance department

## Mission
Know the money daily: P&L, margins by channel, receivables, payables, GST-ready exports for the CA.

## Lead agent
controller: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Supabase (read), Metabase, CSV/XLSX exports

## Human approval gates
- Any payment
- any invoice sent
- any tax filing

## KPIs (reported daily via kpi-report)
- cash position
- receivables
- payables
- margin by channel
- unreconciled items

## Auto-approved actions (only when evals are green)
Daily P&L summary

## Evals
evals/controller.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
