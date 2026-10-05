---
name: eval-gate
description: Run a Luxella department agent's eval set before any prompt, tool or permission change and block the change unless it passes (>=90% and no critical regression). Use when editing departments/*/agents/*.md, changing an agent's tools, adding auto-approved actions, or when asked whether an agent is ready.
---

# Eval gate

The cases live in `departments/<dept>/evals/<agent>.jsonl`. Each line is `{"id","input","expected","pass_rule"}`, plus an optional `"critical": true`. The target is 20–30 **real** cases per agent; the `agent-spec` skill covers how to collect them.

## Steps
1. Run the agent on every case in dry-run or read-only mode. Save its answers as JSONL: `{"id": "1", "output": "..."}`. Add `"verdict": "pass" | "fail"` if they're graded by hand.
2. Run the gate:
```bash
.venv/bin/python -m packages.core.eval_gate <agent> --outputs <file>                 # offline verdicts
.venv/bin/python -m packages.core.eval_gate <agent> --outputs <file> --judge gemini  # free Gemini key, cached
```
3. **Gate rule:** the pass rate must be at least 90%, and no critical case that passed last time may fail now. A missing output for a critical case counts as a fail.
4. The result is saved to `evals/results/<agent>-<time>.json` (gitignored), and a fail exits with code 1. Paste the table into the PR.

## Rules
- A change merges only after the gate passes on the new version. Put the before and after results in the PR.
- A department's "auto-approved actions" stay **off** until its evals are green (and pricer's stay off for 2 weeks).
- Never edit cases to make a change pass. If a case is wrong, fix it in a separate PR and give the reason.
- The judge only reads text. It never runs tools and never writes to production.
