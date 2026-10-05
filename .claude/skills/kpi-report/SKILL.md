---
name: kpi-report
description: The one daily report format every Luxella department agent uses for its 5 KPIs, plus logging each run to agent_runs. Use when an agent reports KPIs, posts a daily summary/digest, or finishes any run.
---

# KPI report

Every number comes from a query run in the same session, and the query is cited. Never estimate or reuse old numbers.

## Format
```
<Department> · <YYYY-MM-DD> · lead <agent>
KPI | today | 7-day avg | target | status
<kpi 1> | 37 | 41 | ≤ 0 | bad
<kpi 2> | ...
Highlights: up to 3 short lines (what changed and why it matters)
Needs founder: <N> pending approvals - top 3: <id> <action> ...
Data: <source + query/tool> @ <time UTC>; ...
```

## Rules
- **Status:**
  - `ok` means on target.
  - `watch` means within 20% of target or getting worse.
  - `bad` means off target. Bad items go first in Highlights.
- **Missing source:** if a source is missing or unreachable, write `n/a (source missing)`. Don't use 0.
- **No target yet:** write `-`. Don't make one up.
- **KPI list:** each department has exactly 5 KPIs, listed in `departments/<dept>/README.md`. Use those names.
- **Pending approvals:** get them from `packages.core.approvals.list_pending()`.
- **Hard stop:** the report is read-only. It never triggers a write.

## Log every run
```python
from packages.core.runs import log_run
log_run("catalog", "curator", inputs={...}, tool_calls=["luxella_check_availability"],
        outputs={"kpis": {...}}, approvals=[pid, ...], duration=12.4, status="ok")  # ok/partial/failed/dry_run
```
Runs are stored in `/root/luxella-ops/agent_runs.jsonl`. View the latest with `packages.core.runs.recent()`.
