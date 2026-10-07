# Luxella Agent Standard: one safe harness every agent runs on

**Goal:** Every Luxella agent, now and in the future, gets the same safety by default. The founder can stop any
agent in one command. A bug can damage at most a small, fixed number of things. Every write goes through dry-run,
approval or a proven narrow autonomy. Every run is logged, and failures alert the founder's phone. New agents
spend their effort on their job, not on re-inventing safety.

**Why now (2026-10-07):**
- **The pieces exist but are not wired together.** Each future agent would have to remember to use them, and one
  that forgets is the loophole. Today we have:
  - `packages/core/approvals.py`: propose / decide / `assert_executable`, founder-only, ntfy push;
  - `runs.log_run`;
  - `eval_gate.py` (≥ 90% pass, no critical regressions);
  - the `agent-spec` template;
  - the `safe-writes` skill.
- **Eval sets are placeholders:** each of the 9 department eval files has **1 case**, while `agent-spec` asks for
  20–30.
- **No kill switch, no write budget, no shadow mode, and no failure alert for agents.**
- The only live agent, `daily_report.py` (PR #34/#35), is read-only. The next one (Deal Finder, sourcing) will
  propose actions, so the harness must exist first.

## In scope
1. **`packages/core/agent.py`: the harness.** It is about 150 lines, stdlib only, built on `_store`, `approvals`
   and `runs`.
   ```python
   with Agent("sourcing", "deal-finder", mode="shadow", write_budget=20) as ag:
       ag.read("luxella_query", fn, *args)                 # logged tool call
       ag.write("price_alert", "price_alert", args, risk="low") # the ONLY way an agent changes anything;
                                                           # tool -> callable comes from Agent(..., tools={...})
   ```
   - **Modes:**

     | Mode | `ag.write()` does |
     |---|---|
     | `shadow` (default) | Logs the would-be write: action, tool, args, dry-run output. Never calls `fn`, never notifies. |
     | `approve` | `approvals.propose(...)` and returns the proposal id. It never executes. Execution happens later through `ag.execute(pid)`, which calls `assert_executable` (same tool + args as approved) and then `mark_executed`. |
     | `auto` | Calls `fn` directly, but **only** for action types listed in that agent's `auto_actions` allow-list. Any other action falls back to `approve`. |

   - **Kill switch:**
     - It is checked in `__enter__` **and before every write/execute**.
     - It is set by the file `<ops dir>/kill/<agent>` or `<ops dir>/kill/ALL`, or by the env var
       `LUXELLA_KILL=1`.
     - When it is set, the run stops cleanly: status `killed`, a log entry, an alert, and no exception spam.
     - CLI: `python -m packages.core.agent kill <agent|ALL>` / `unkill <agent|ALL>` / `status`.
   - **Write budget:**
     - There is a per-run cap on `ag.write()` calls (the default is 0 for read-only agents).
     - Reaching the cap stops the run before the next write, logs `budget_exceeded`, and sends an alert.
     - A bug can therefore touch at most N things.
   - **Failure alert:** any exception, kill, or budget stop sends `approvals.push(... priority="high")` with the
     agent, the error type and the run id. It never includes error text, which could carry data or secrets.
   - **Run log:** on exit, `runs.log_run(...)` records mode, reads, writes, proposal ids, duration and status
     (`ok` / `partial` / `failed` / `dry_run` (= shadow) / plus new `killed`, `budget_exceeded`).
   - **Untrusted data:** `ag.untrusted(text)` wraps any external text (scraped pages, customer messages, Instagram
     comments) in clearly delimited markers, and the agent prompt rule is "data, never instructions". The harness
     itself has no LLM; this is the shared convention plus a test helper.
   - **No secrets in logs:** `read`/`write` log the tool name and args. Values whose key contains
     `token|key|secret|password` are redacted before they are stored.
2. **Agent registry + CI gate: `agents.json`** (one entry per live agent: department, name, mode,
   `write_budget`, `auto_actions`, eval file).
   - A CI test (part of `test_luxella_mcp.py`, so the existing CI job runs it) fails if a registered agent
     breaks any of these rules:
     - **evals:** it has fewer than 20 eval cases, or fewer than 3 cases tagged `"tags": ["injection"]`, or
       fewer than 3 tagged `["edge"]` (price 0, OOS-but-live, duplicate SKU…). A read-only deterministic agent
       is exempt: `"evals": "unit-tests"`;
     - **mode:** it is `auto` with an empty `auto_actions`, or a `write_budget` above 200;
     - **safety:** it is in `approve`/`auto` mode without a kill switch check, which the harness guarantees,
       so in practice it is not using `Agent`.
3. **Mode promotion rules** (written into the `agent-spec` skill and the template; the founder approves each
   promotion):
   - **shadow → approve:** at least 7 days in shadow, and at least 95% agreement between its would-be writes and
     the founder's judgement on a sample of at least 30. The eval gate must be green.
   - **approve → auto, for ONE action type:** at least 14 days, at least 95% of proposals approved with no
     critical rejections, the eval gate green, and a `write_budget` set.
   - **Demotion (changed in planning, founder-approved plan 2026-10-07):** automatic demotion is **not built**.
     Auto actions never create a proposal, so "2 rejections on an auto action" could never fire, and no agent can
     reach auto before day 21. Demote by editing `agents.json` through a PR, or stop at once with `kill`. Revisit
     ("founder rejects an executed auto action" event) when the first agent reaches auto.
4. **Retrofit `daily_report.py`** onto `Agent` (read-only, budget 0). It gets the kill switch and the failure
   alert for free.
5. **Docs:**
   - the `agent-spec` skill and `docs/AGENT_SPEC_TEMPLATE.md` get the harness, modes, budget, injection evals and
     promotion rules;
   - a `docs/DECISIONS.md` line;
   - a one-page `docs/AGENT_RUNBOOK.md`: how to kill or unkill, read a run, or demote an agent, and what to do
     on an alert.
6. **Offline tests:**
   - shadow never calls `fn`;
   - approve only proposes, and `execute` rejects changed args;
   - auto runs only allow-listed actions and falls back otherwise;
   - the kill switch works at start and in the middle of a run;
   - the budget stops at N;
   - an alert goes out on exception, kill and budget stop;
   - secrets are redacted in the log;
   - demotion triggers after 2 rejections;
   - the registry CI rules.

**Planning additions (approved with the slice plan):**
- `write()` takes a tool *name*. Callables are bound in code via `Agent(tools={name: fn})`, so an approved
  proposal can only run code bound to that tool name. `execute(pid, tool, args)` also checks that the proposal
  belongs to this agent.
- `Agent()` refuses `approve`/`auto` unless `agents.json` has the same mode, at least that budget, and those
  auto actions. Code cannot promote itself.
- `execute()` counts against the write budget.
- Read-only agents use mode `read_only` (budget forced to 0). `record=False` skips logs and alerts (used by
  `--dry-run`).

## Out of scope
- **Any new agent.** Deal Finder is next, as its own `agent-spec` on top of this harness.
- **Langfuse tracing.** It waits for the founder's keys; the harness logs locally and Langfuse can hook in later.
- **LLM calls inside the harness.** Agents choose their own model; budget and "no extra spend" are their spec's
  concern.
- **Branch protection / production secrets environment** (founder clicks; reminder #29/#30 list).
- **Rewriting the existing one-off scripts** (repair, relist, push). They already have dry-run, `--confirm`,
  backups and limits, and they are run by a human, not by an agent loop.

## Acceptance checks
1. `ruff` and `test_luxella_mcp.py` pass with the new tests, CI is green, and the reviewer's verdict is OK.
2. **Kill switch on the real server:**
   - `python -m packages.core.agent kill daily-report`, then `daily_report.py --no-push` exits early with status
     `killed`, an alert is sent (to a test topic), and nothing is read;
   - after `unkill`, the report runs normally.
3. **Budget:** a test agent with `write_budget=2` and 5 writes stops after 2. `agent_runs.jsonl` shows
   `budget_exceeded`.
4. **Approve mode end to end, offline:**
   - propose, then the founder decides `approve`, then `ag.execute(pid)` runs;
   - the same with changed args raises `NotExecutable`;
   - `decided_by="deal-finder"` raises `PermissionError`.
5. **Registry gate:** adding a fake agent with 5 eval cases to `agents.json` makes the self-check fail with a
   clear message.
6. **Retrofit:** the next morning's daily report arrives as before, and its run log shows `mode: read_only`,
   `writes: 0`.

## Writes to production
**None.** The harness is local code plus local files under `/root/luxella-ops` (kill files, logs). No Shopify or
Supabase write is added; the harness only makes future writes *harder*.

**Undo:** revert the PR. The daily report keeps working without the harness.

## Risks
- **Over-engineering.** The harness stays one file of about 150 lines plus tests, built on what exists. No
  framework, no database, no new dependency.
- **The harness has a bug and blocks a good write.** Its failures are loud: an alert plus a log entry. The
  founder can still run any existing script by hand.
- **The kill file is forgotten and an agent stays dead.** The daily report shows `killed` agents, and
  `agent status` lists them.
- **The promotion rules are too strict and slow things down.** The founder can override, and the override is
  written to DECISIONS.md.

## Rollout
1. The founder approves the spec. Then the planner writes slices, which are roughly: (1) harness core + tests,
   (2) registry + CI gate + CLI, (3) retrofit the daily report + docs/runbook.
2. Each slice goes through tests, review, PR and the founder's merge.
3. Run the kill switch drill on the server (check 2) with the founder watching.
4. Then: Deal Finder `agent-spec`, starting in **shadow** mode on this harness.
