# Pricing department

## Mission
Quote fast and correctly: landed cost (retail + US tax by route + reshipper + domestic courier), target margin, competitive check. SEPARATE PROJECT: this folder holds only the spec and a link to the pricing repo.

## Lead agent
pricer: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Supabase (read), FX rates, retailer price lookups

## Human approval gates
- Every quote sent to a customer or B2B partner
- any change to margin rules

## KPIs (reported daily via kpi-report)
- quotes made
- quotes accepted
- average margin
- min-margin breaches
- turnaround time

## Auto-approved actions (only when evals are green)
None until pricer evals pass for 2 weeks

## Evals
evals/pricer.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.

## Pricing repo
SEPARATE PROJECT. This folder holds only the spec and a link to the pricing repo: <pricing repo link>
