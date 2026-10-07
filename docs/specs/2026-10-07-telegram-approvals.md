# Telegram approval bot: approve, reject or stop agents from the phone with one tap

**Goal:** When a Luxella agent proposes something (a deal to feature, a buy, later a customer reply), the founder
gets a Telegram message with **✅ Approve / ❌ Reject** buttons and decides in one tap. He can also rate Deal
Finder items 👍/👎 and **stop any agent** (`/kill`) from the phone. No Claude session is needed.

**Why now (2026-10-07):**
- **Approvals exist but are clumsy:**
  - `packages/core/approvals.py` already has propose → founder `decide` → `assert_executable`, and the
    harness's approve mode creates proposals;
  - but deciding needs a Python call or a Claude session;
  - ntfy only notifies; it can't carry an authenticated answer back.
- **Deal Finder needs ratings:**
  - it is live in shadow mode (07:45 IST daily);
  - promotion needs ≥ 30 founder ratings at ≥ 95% 👍;
  - today that would mean typing ratings in chat.
- **Kill switch:** it works only from an SSH terminal (`python -m packages.core.agent kill …`).
- **No new opening in the server:**
  - after hardening, only port 22 is open;
  - Telegram **long polling** (`getUpdates`) is outbound-only;
  - so the bot needs **no inbound port, no domain and no webhook**.
- **Free:** the Telegram Bot API costs nothing.

## In scope
1. **`telegram_bot.py`**, stdlib (`urllib`) long-polling. No new dependency.
   - **Auth, the core of the design:**
     - it answers **only** the founder's chat id (`TELEGRAM_FOUNDER_CHAT_ID` in the key file);
     - every other chat or user id is ignored and logged by numeric id only;
     - callback buttons carry only the action plus the proposal id;
     - the bot re-reads the proposal and checks it is still `pending` before deciding.
   - **Commands:**
     - `/pending`: list pending proposals (id, agent, action, risk), each with ✅/❌ buttons;
     - `/status`: the output of `agent status` (killed list, last run per agent);
     - `/kill <agent|ALL>` and `/unkill <agent|ALL>`: the same names and regex as the CLI. **Kill needs a
       second confirm tap.**
     - `/help`.
   - **Buttons:**
     - ✅ calls `approvals.decide(pid, "approve", "founder", note="telegram")`;
     - ❌ calls `decide(..., "reject", ...)`;
     - the message is then edited to show the result.
   - **What the bot never does:**
     - it **never executes** anything. Approval only marks the proposal approved; the agent runs it next time
       through `ag.execute`, with the same tool and args. The bot has no Shopify or Supabase write access;
     - it never shows secrets. Proposal args are shown redacted (`agent.redact`), with long values cut short.
2. **Notifications.**
   - `approvals.push()` also sends to Telegram when it is configured (an approval card with buttons for new
     proposals; plain text for the daily report, deals and alerts).
   - ntfy stays as a fallback, so both channels work. If Telegram fails, it never blocks the caller.
3. **Deal Finder ratings.**
   - The deals digest goes to Telegram with 👍/👎 per item (top 10).
   - Ratings append to `<ops>/ratings.jsonl`: `{run_id, product_id, rating, at}`.
   - `deal_finder` adds "rated so far: N, 👍 X%" to its KPI block, which is the promotion data.
4. **systemd** `luxella-telegram-bot.service`:
   - `Restart=on-failure`;
   - env from the key file `/root/.config/agent-keys/telegram-bot.env` (600: `TELEGRAM_BOT_TOKEN`,
     `TELEGRAM_FOUNDER_CHAT_ID`);
   - **enabled only after the founder's test**.
5. **Offline tests (fake Telegram API):**
   - a stranger's chat id is ignored, and nothing is decided;
   - approve and reject go through `decide`, and the message is edited;
   - an already-decided proposal can't be decided twice;
   - `/kill ALL` without the confirm tap does nothing; with it, the kill file is created;
   - a bad agent name is refused;
   - ratings are written;
   - a token never appears in logs;
   - a Telegram outage leaves ntfy working.

## Out of scope
- Customer-facing Telegram chat. That is Concierge and Chatwoot, later.
- Executing approved actions from the bot.
- Voice, media, groups, or more than one approver.
- Replacing ntfy. Both are kept.

## Founder setup (5 minutes, once)
1. In Telegram, open **@BotFather**, send `/newbot`, and pick a name (for example "Luxella Ops") and a username.
   Copy the token.
2. In an SSH terminal (**not in chat**):
   `install -m 600 /dev/stdin /root/.config/agent-keys/telegram-bot.env`, paste
   `TELEGRAM_BOT_TOKEN=<token>`, then press Ctrl-D.
3. Send `/start` to the new bot. Claude then reads the chat id from `getUpdates` and appends
   `TELEGRAM_FOUNDER_CHAT_ID=…` to the same file. Claude never prints the token.

## Acceptance checks
1. `ruff`, `test_luxella_mcp.py` and CI pass, and the reviewer's verdict is OK.
2. **On the phone:**
   - `/status` replies;
   - a test proposal (the `test-bot` agent, risk low, a dummy tool) arrives with buttons;
   - ✅ makes `approvals.get(pid)["status"] == "approved"`, decided_by `founder`, note `telegram`.
3. **Stranger test:** a message from any other Telegram account gets no reply, and nothing is decided. The log
   shows the ignored numeric id only.
4. **Kill:**
   - `/kill deal-finder` → confirm → `agent status` lists it, and the next Deal Finder run is `killed`;
   - `/unkill deal-finder` restores it.
5. **Ratings:** the next deals digest arrives with 👍/👎. Tapping one writes `ratings.jsonl`, and the next KPI
   block shows "rated so far".
6. Port probe: still only 22 open from outside, because polling is outbound.

## Writes to production
**None to Shopify or Supabase.** Local only:
- `approvals.jsonl` decisions (the founder's own taps);
- kill files;
- `ratings.jsonl`.

**Undo:** `systemctl disable --now luxella-telegram-bot`. ntfy keeps working.

## Risks
- **Bot token leak.** Anyone with it can impersonate the bot, but they still can't decide anything, because
  decisions need the founder's chat id on incoming updates. Mitigation: 600 key file, never printed, rotatable in
  BotFather in one minute.
- **Founder's Telegram account taken over.** Same as phone/email compromise. A takeover could approve pending
  proposals, but it can't execute: execution stays with the agent and its budget.
- **Mis-tap.** Approve can't be undone from the bot. Mitigation: medium/high-risk cards show the full action and
  dry-run first; kill needs a confirm.
- **Telegram outage.** ntfy plus SSH remain.

## Rollout
1. The founder approves the spec and does the 5-minute setup.
2. The planner writes slices: (1) the bot core, auth, commands and tests; (2) the push integration and
   approval/digest cards; (3) Deal Finder ratings, the systemd unit, and docs/runbook.
3. Phone tests (checks 2-5), then the service is enabled.
