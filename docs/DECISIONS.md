# Decisions log
Format: date, decision, why, alternatives considered.

- 2026-10: Moved dev from Chromebook (2.7 GB RAM, 21 GB disk) to a Contabo VPS (8 GB RAM, 100 GB). Why: constant hangs. Alternative: resize Crostini disk (RAM still too low).
- 2026-10: Built luxella_mcp.py with 4 tools; writes only with confirm=True. Why: the founder approves anything touching production.
- 2026-10: Bid-pricing agent kept separate from the catalog MCP. Why: different risk profile and ownership.
- 2026-10: Access via SSH key + tmux session. Why: no repeated passwords, sessions survive disconnects.
- 2026-10: New cron schedules ship disabled until tested at small batch size. Why: avoid unreviewed bulk writes to the live store.
- Default agent framework: Claude Agent SDK reusing MCP tools. Why: tools already exist, no rewrite.
