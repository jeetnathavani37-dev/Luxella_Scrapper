# Luxella: Project Operating Rules

Luxella is a luxury goods resale and concierge business. The long-term goal is an AI-led Luxella:
agents do the repetitive work, the founder approves anything that touches money or customers.

Read these before any non-trivial task:
- docs/PRD.md (what and why)
- docs/ARCHITECTURE.md (how the pieces fit)
- docs/DESIGN.md (design system, read before ANY UI work)
- docs/DECISIONS.md (why we chose what we chose)
- docs/ROADMAP.md (what is next)

## Workflow (every feature, no exceptions)
1. SPEC: use the spec-first skill. Write the goal, scope and acceptance checks.
2. PLAN: list small slices. Show the plan and wait for approval before editing.
3. BUILD: one slice at a time. Smallest change that works.
4. TEST: run the offline self-check (python test_luxella_mcp.py) after every change.
5. REVIEW: use the reviewer sub-agent before merging.
6. COMMIT: one clear commit per working slice.

## Hard rules
- Anything that writes to Shopify or Supabase is dry-run by default and needs an explicit confirm=True. See the safe-writes skill.
- Never read, print, log or edit ~/.luxella.env or any secret. Refer to variables by name only.
- Never run git push --force. Open a PR instead.
- Never claim "done" without running the check and showing the result.
- If a request is ambiguous or touches money or customers, ask one short question first.
- The bid-pricing agent is a SEPARATE project. Do not add bidding logic to luxella_mcp.py.

## Agents and skills in this repo
Sub-agents (.claude/agents): planner, builder, reviewer, designer, qa.
Skills (.claude/skills): spec-first, agent-spec, safe-writes, ui-design-system, ship-check, luxella-context.

## Style
- Reply to the founder in Hinglish, short and direct.
- Prefer boring, readable code over clever code. No new dependency without a reason in DECISIONS.md.
- Python: type hints, small functions, errors handled explicitly. UI: Next.js + Tailwind + shadcn/ui + Motion.
