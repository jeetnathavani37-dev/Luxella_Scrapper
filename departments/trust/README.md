# Trust department

## Mission
Zero fakes: authentication checklists, provenance records, fraud and chargeback flags.

## Lead agent
verifier: read-only by default, risky actions via approval-queue skill.

## Tools it may use
Image tools, authentication checklists, Supabase (read)

## Human approval gates
- Final authentication verdict
- any dispute response

## KPIs (reported daily via kpi-report)
- items authenticated
- flags raised
- disputes
- false positives
- average time

## Auto-approved actions (only when evals are green)
Flagging items for human review

## Evals
evals/verifier.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
