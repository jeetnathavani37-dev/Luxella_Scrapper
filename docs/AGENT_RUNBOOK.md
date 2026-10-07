# Agent runbook

All commands run from `/root/Luxella_Scrapper` with `.venv/bin/python`.

## Stop an agent now
```bash
.venv/bin/python -m packages.core.agent kill <agent-name>   # e.g. deal-finder
.venv/bin/python -m packages.core.agent kill ALL            # every agent
.venv/bin/python -m packages.core.agent unkill <agent-name|ALL>
.venv/bin/python -m packages.core.agent status              # killed list + last run per agent
```
- A kill takes effect before the agent's next read, write or execute.
- A killed run logs `killed` and sends a high-priority phone alert.
- `LUXELLA_KILL=1` in an agent's environment does the same thing.
- The daily report lists killed agents every morning, so a forgotten kill shows up.

## An alert arrived ("Luxella agent <name>: failed | killed | budget_exceeded")
1. `status`: is it still running? What was the last status?
2. Read the run: `tail -n 5 /root/luxella-ops/agent_runs.jsonl` (mode, reads, writes, proposals, stop_reason).
   Secrets are redacted.
3. **failed**: the error type is in `stop_reason`. Fix it through a normal PR. If it may write again before the fix,
   kill it first.
4. **budget_exceeded**: the agent tried more writes than allowed. Treat it as a bug until proven otherwise. Check
   `writes` and undo using the action's backup or undo note. Do not just raise the budget.
5. **killed**: expected if someone killed it. Otherwise, check who created `/root/luxella-ops/kill/<name>`.

## Demote or change an agent's mode, budget or auto actions
- Edit its entry in `agents.json` through a PR. The reviewer and CI must pass, then the founder merges.
- The harness refuses `approve` or `auto` if the code asks for more than `agents.json` allows.
- For an immediate stop, kill first, then send the PR.

## Budget notes
- Shadow writes count against `write_budget` too (shadow should behave like the real mode). A shadow agent with the
  default budget 0 stops at its first write: set the budget in `agents.json`/the code to the expected run size.
- An attempt is counted before the tool runs, so a tool that raises still uses budget (retry loops can't repeat it).

## Approvals
- Pending proposals: `packages.core.approvals.list_pending()`. The founder decides with
  `decide(pid, "approve" | "reject", "founder")`.
- An agent runs an approved proposal with `ag.execute(pid, tool, args)`. The tool and args must match exactly,
  and the proposal must belong to that agent. Only `approve`/`auto` agents can execute.
- If the tool raises during `execute`, the proposal is closed as executed with `{"ok": false, "error": <type>}`.
  Running it again needs a new proposal and a new founder approval, so a half-applied action is never repeated
  silently.
