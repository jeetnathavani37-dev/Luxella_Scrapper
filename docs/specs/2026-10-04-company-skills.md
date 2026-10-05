# Company skills: approval-queue, kpi-report, eval-gate, luxury-voice

**Goal:** Give all 9 department agents the four shared skills they already depend on, so any agent can propose
risky actions for founder approval, report KPIs in one format, prove itself on evals before changes, and write
customer text in the Luxella voice.

**Why now:** The department files (PR #20) reference these skills 77 times, but none of them exist yet:
approval-queue 30, kpi-report 28, luxury-voice 10, eval-gate 9. They also reference `agent_runs` 18 times. Until
the skills exist, no department agent can run safely.

## In scope

Each skill lives in `.claude/skills/<name>/SKILL.md`, with a small Python helper where noted. Helpers go in
`packages/core/` and use only the standard library.

### 1. approval-queue
How an agent proposes a risky action and how it gets executed only after approval.

- **Proposal record:**
  - `id`, `created_at`, `department`, `agent`
  - `action` (one line), `risk` (low / med / high)
  - `tool` and `args`, i.e. the exact call that would run
  - `dry_run_output`, `undo`
  - `status`: pending, approved, rejected or expired
  - `decided_by`, `decided_at`
- **Helper:** `packages/core/approvals.py` with `propose()`, `list_pending()`, `decide(id, approve|reject)`,
  `mark_executed(id, result)`.
- **Phase 1 storage:** a JSONL file at `/root/luxella-ops/approvals.jsonl`, chmod 600. It lives outside the repo
  and writes nothing to production.
- **Notifications:** on a new proposal, send an ntfy push to the existing `luxella-alerts` topic. The push holds
  only the action line and the id; no customer data.
- **Rules:**
  - An agent may execute only proposals with `status=approved`, matching the exact `tool` and `args`.
  - Execution uses the tool's `confirm=True` path.
  - Proposals expire after 48 hours.
  - The founder approves by telling Claude in chat. A web UI comes later.

### 2. kpi-report
A single daily report format for every department.

```
<Department> · <date> · lead <agent>
KPI | today | 7-day avg | target | status (ok/watch/bad)
Highlights: up to 3 lines   Needs founder: pending approvals count + top 3   Data: sources and query time
```

- Numbers must come from a query in the same run, and the query is cited. Never estimate. A missing data source
  shows as `n/a (source missing)`.
- **Helper:** `packages/core/runs.py` with `log_run(department, agent, inputs, tool_calls, outputs, approvals,
  duration, status)`.
- **Phase 1 storage for `agent_runs`:** `/root/luxella-ops/agent_runs.jsonl`.

### 3. eval-gate
How to run `departments/*/evals/<lead>.jsonl` before any prompt or tool change.

- **Case format:** the existing `{id, input, expected, pass_rule}`.
- **Grading:** the agent runs on each case in a dry-run or read-only context. A judge model grades
  `pass_rule` → pass/fail plus a reason. The result is written to `evals/results/<agent>-<date>.json`.
- **Gate:** the change is allowed only if the pass rate is ≥ 90% and there are no new failures in cases marked
  `critical`. Auto-approved actions stay off for a department until its evals are green, as its README says.
- **Helper:** `packages/core/eval_gate.py <agent>`. It prints a table and exits non-zero if the gate fails.
- **Scope note:** this is the runner only. Collecting the 20–30 real cases per department is separate work.

### 4. luxury-voice
Customer-facing writing rules, from DESIGN.md "Content tone" and the brand.

- Short, calm, precise.
- No "SALE", "HURRY", "50% OFF", exclamation marks or emoji in formal messages.
- Never promise authenticity or a timeline unless verified data backs it.
- Do's and don'ts, plus 6 before/after examples: DM reply, WhatsApp order status, product copy, delay apology,
  price quote and newsletter intro.
- Hinglish is allowed for Indian customers only if the customer wrote in Hinglish.
- A pre-send self-check list. No helper code.

## Out of scope
- Supabase tables for `approvals` and `agent_runs`. That's phase 2, as its own spec, because it's a schema change.
- A web approval UI (later, in `apps/hq-dashboard`), and any channel integrations (Chatwoot, WhatsApp, Postiz).
- Writing the real 20–30 eval cases per department.
- Linking department agents into `.claude/agents/` (separate task).
- Any change to scrapers, push/sync or `luxella_mcp.py`.

## Acceptance checks
1. The four `SKILL.md` files exist and have valid frontmatter (`name`, `description`), and Claude lists them.
2. **Approvals:** `python -m packages.core.approvals selftest` creates a proposal in a temporary file, then:
   - lists it as pending
   - approves it
   - refuses to execute a proposal whose args don't match
   - expires one older than 48 hours
   - All of this happens with no network and no Supabase/Shopify calls.
3. **Runs:** `python -m packages.core.runs selftest` writes one valid JSONL line and reads it back.
4. **Eval gate:**
   - `python -m packages.core.eval_gate --selftest` passes on a fake 10-case set (9 pass, 1 fail, so 90%).
   - It exits non-zero on 8 out of 10.
5. **ntfy:** a test proposal sends one ntfy push, and the founder confirms they received it. If the app isn't
   subscribed yet, this check is skipped and noted.
6. `.venv/bin/python test_luxella_mcp.py` prints `ok`.
7. The `reviewer` agent verdict is `OK to merge`.

## Writes to production
None. Approvals and runs go to `/root/luxella-ops/*.jsonl` on the server. Eval results go to
`evals/results/` (gitignored). The only outbound call is the ntfy push in check 5.

## Risks
- **An agent executes without approval.** Mitigation:
  - Execution requires an approved record whose `tool` and `args` exactly match.
  - A selftest covers the mismatch case.
  - The reviewer checks every new agent's write path.
- **The JSONL file grows or gets corrupted.** Mitigation: append-only writes, one line per event, and a daily
  rotation note. Phase 2 moves this to Supabase.
- **The judge model costs money.** Mitigation: use the free Gemini key (flash-lite), which is fine for 30 cases
  per department, and cache results. No paid key.
- **Notification leaks.** The ntfy topic is public-by-name, so pushes carry the action line and id only. No
  customer names or prices.

## Rollout
1. Build the skills and helpers. Run the selftests (checks 2–4). No agents use them yet.
2. Trial with one department: catalog/curator. It proposes a `luxella_sync_catalog` dry-run into the queue, the
   founder approves in chat, and the run is logged.
3. Then the other departments, one at a time, as their evals get written.
