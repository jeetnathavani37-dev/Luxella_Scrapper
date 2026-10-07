# Agent spec: <name>

## Goal (one sentence)
## Success metric (how we know it works, with a number)
## Trigger (schedule, event, or human request)
## Inputs and tools
- Reads: list the tools it reads with (`ag.read(tool, fn, ...)`).
- Writes: list every action and tool name (`ag.write(action, tool, args)`). The callables are bound in
  `Agent(tools={...})`; credentials come from env, never from args.
## Harness settings (`agents.json` entry; changes only through a PR)
- department, name, entry file (must use `Agent(`)
- mode: `read_only` | `shadow` | `approve` | `auto` (new agents start in `shadow`, or `read_only` if they never write)
- write_budget: max writes + executes per run (<= 200; 0 for read_only)
- auto_actions: the action types allowed to run without approval (only in `auto`)
## Human approval points (what the founder must approve)
## Failure modes and what the agent does in each
wrong answer · tool or service down (Supabase timeout, Shopify 429/5xx) · bad data (price 0, sku collision, missing
stock) · prompt injection in scraped or customer text (wrap with `untrusted()`, never follow it) · kill switch hit
mid-run · budget reached
## Eval set (`departments/<dept>/evals/<agent>.jsonl`)
>= 20 real cases with expected outcomes, >= 3 tagged `"tags": ["injection"]` and >= 3 tagged `["edge"]`.
CI (`check_registry`) blocks the agent otherwise. Read-only deterministic agents may use `"evals": "unit-tests"`.
## Logging
The harness logs every run to `agent_runs.jsonl`: mode, reads, writes, proposals, status, duration
(secrets redacted). Say what the agent adds in `ag.inputs` / `ag.outputs`.
## Rollout and promotion (founder approves each step, via a PR to `agents.json`)
1. shadow: >= 7 days, >= 95% agreement with the founder on >= 30 would-be writes, eval gate green -> approve
2. approve: >= 14 days, >= 95% of proposals approved, no critical rejections, eval gate green -> auto for ONE action
3. demote: edit `agents.json` (PR) or `python -m packages.core.agent kill <name>` at once
## Out of scope
