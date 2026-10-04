# Platform department

## Mission
Keep everything running: infra, pipelines, monitoring, evals, security, cost.

## Lead agent
platform: read-only by default, risky actions via approval-queue skill.

## Tools it may use
GitHub, Docker, Uptime Kuma, Langfuse, n8n

## Human approval gates
- Production deploys
- schema migrations
- new schedules
- secret rotation

## KPIs (reported daily via kpi-report)
- uptime
- failed jobs
- agent runs
- eval pass rate
- API cost

## Auto-approved actions (only when evals are green)
Restarting a failed job once, posting alerts

## Evals
evals/platform.jsonl, 20-30 real cases, run via eval-gate before any prompt or tool change.
