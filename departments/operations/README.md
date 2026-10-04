# Operations department

## Mission
Deliver on time: reshipper handoff, tracking, delay alerts, RTO stock, consolidation suggestions.

## Lead agent
dispatcher: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Supabase orders (read), courier tracking APIs, reshipper message drafts

## Human approval gates
- Refunds
- disputes
- any payment to reshippers
- address changes

## KPIs (reported daily via kpi-report)
- shipments in transit
- delayed
- delivered
- RTO stock value
- average delivery days

## Auto-approved actions (only when evals are green)
Tracking status updates into the approval queue

## Evals
evals/dispatcher.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
