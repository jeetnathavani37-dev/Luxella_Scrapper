---
name: approval-queue
description: How a Luxella agent proposes a risky action (any Shopify/Supabase write, outbound message, purchase, payment, schedule) for founder approval and executes it only after an exact-match approval. Use whenever an agent or session is about to do something listed under a department's "Human approval gates", or the founder says approve/reject a proposal.
---

# Approval queue

Helper: `packages/core/approvals.py` (standard library only).
Storage: `/root/luxella-ops/approvals.jsonl` (append-only, chmod 600). Run commands from the repo root with `.venv/bin/python`.

## Propose (agent side)
1. Dry-run first (see the `safe-writes` skill) and keep its output short.
2. Propose:
```python
from packages.core import approvals as aq
pid = aq.propose(department="catalog", agent="curator",
                 action="Set 5 drift products to stock 0",   # one line, no customer data
                 risk="med",                                   # low / med / high
                 tool="inventorySetQuantities", args={...},    # the EXACT call that would run
                 dry_run_output="5 items 10->0 (list...)", undo="backup /root/backups/...")
```
3. This sends an ntfy push (action line + id only) to the founder's topic.
4. Tell the founder in chat: what it does, how many, the risk, how to undo it, and the id. Then stop.

## Decide (founder, in chat)
- The founder says "approve a-xxxx" or "reject a-xxxx".
- Record it with `aq.decide(pid, "approve", decided_by="founder")`.
- Only `decided_by="founder"` (case-insensitive) is accepted. An agent can never decide any proposal.
- A pending proposal expires 48 hours after creation. An approved but unexecuted proposal expires 48 hours after approval. A new batch needs a new proposal.

## Execute (only after approval)
```python
aq.assert_executable(pid, tool, args)   # raises unless approved, unexpired, and tool+args match exactly
result = <run the tool with confirm=True>
aq.mark_executed(pid, result={...})
```
- If anything changed since approval (args, batch, ids), re-propose instead of editing args.
- Verify after executing, as in `safe-writes`, and log the run (`kpi-report`).

## Commands
- `.venv/bin/python -m packages.core.approvals list`: lists pending proposals.
- `... approvals selftest`: offline check.
- `... approvals notify-test`: sends one real push to test the phone.
- Turn pushes off with `LUXELLA_NTFY=0`. The topic comes from `LUXELLA_NTFY_TOPIC` or the existing topic file. Never print the topic.

## Rotation
Phase 1 is a single JSONL file. Phase 2 moves it to a Supabase `approvals` table, which needs its own spec because it's a schema change.
