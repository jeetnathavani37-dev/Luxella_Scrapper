---
name: spec-first
description: Write a short spec (goal, scope, acceptance checks, risks) before building any Luxella feature or non-trivial fix, and get the founder's OK before editing code. Use at the start of every feature, bug fix that changes behaviour, new script or workflow, or anything that writes to Shopify/Supabase.
---

# Spec first

Step 1 of the `CLAUDE.md` workflow. Nothing gets edited until the founder approves the spec.

## 1. Understand
- Read `CLAUDE.md`, `docs/PRD.md`, `docs/ROADMAP.md` and the code involved. Use the `luxella-context` skill for the map.
- Check the real data first with read-only queries (the Luxella MCP `luxella_query`), so the spec is based on facts. Example: "236 pushed products have price 0", not "some products are wrong".
- If something is ambiguous or touches money or customers, ask **one** short question.

## 2. Write `docs/specs/<yyyy-mm-dd>-<slug>.md`

```markdown
# <Feature>
**Goal:** one sentence, the outcome for the founder or customer.
**Why now:** the data or incident behind it (numbers).
**In scope:** bullets.
**Out of scope:** bullets (this matters as much as scope).
**Acceptance checks:** numbered, each verifiable by a command or query, e.g.
  1. `test_luxella_mcp.py` passes.
  2. Dry-run lists N products; nothing is written.
  3. After confirm: `productsCount(query:"vendor:X")` = 0.
**Writes to production:** none, or what is written, where, how many rows, and how to undo it (backup path).
**Risks:** what could go wrong and how we would notice.
**Rollout:** dry-run → small batch (e.g. 5) → full, with the check at each step.
```

## 3. Show and wait
- Send the founder a 5–8 line Hinglish summary: goal, checks, and what gets written.
- Then **stop and wait for approval.**
- After approval, hand off to the `planner` agent for slices.

Small fixes (one file, no production writes, under about 20 lines) can use a 3-line spec in the chat instead of a file. You still need the founder's OK.
