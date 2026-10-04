# Sales department

## Mission
Turn conversations into orders with a quiet, premium experience: DMs, WhatsApp, HNI follow-ups, order status.

## Lead agent
concierge: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Chatwoot / Evolution API (read and draft), Supabase customers and orders (read)

## Human approval gates
- Every outbound message
- any discount
- any promise on timeline or authenticity

## KPIs (reported daily via kpi-report)
- conversations
- replies sent
- conversion
- average response time
- pending approvals

## Auto-approved actions (only when evals are green)
Drafting replies into the approval queue

## Evals
evals/concierge.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
