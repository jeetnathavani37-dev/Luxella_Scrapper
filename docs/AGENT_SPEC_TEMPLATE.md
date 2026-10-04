# Agent spec: <name>

## Goal (one sentence)
## Success metric (how we know it works, with a number)
## Trigger (schedule, event, or human request)
## Inputs and tools (MCP tools it may call)
## Permissions
- Default: read-only.
- Writes: only via tools that require confirm=True, and only after human approval.
## Human approval points (what the founder must approve)
## Failure modes (wrong answer, service down, bad data) and what the agent does in each
## Eval set (20-30 real cases with expected outcomes; the agent must pass before going live)
## Logging (what is recorded per run, where to see it)
## Rollout (dry-run only -> approval mode -> limited autonomy, with the criteria to move up)
## Out of scope
