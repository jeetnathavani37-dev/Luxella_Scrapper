"""
telegram_bot.py

Founder ka phone remote (spec docs/specs/2026-10-07-telegram-approvals.md): approval cards pe ✅/❌, agents ka
/status, /kill, /unkill, /pending. Long polling (getUpdates) - outbound only, server pe koi port nahi khulta.

Sirf founder ka private chat (TELEGRAM_FOUNDER_CHAT_ID) handle hota hai; baaki sab ignore (log mein sirf numeric id).
Bot kabhi kuch EXECUTE nahi karta: approve sirf approvals.jsonl mein "approved" likhta hai; agent agle run mein
ag.execute() se chalata hai (same tool + args, apne budget ke andar). Bot ke paas Shopify/Supabase keys nahi.

    python telegram_bot.py            # poll loop (systemd)
    python telegram_bot.py --whoami   # setup: /start bhejne wale chat ka id key file mein likho (token print nahi)
"""
import os
import sys
import time

from packages.core import _store, agent, approvals, telegram

OFFSET_FILE = "telegram_offset"
MAX_COMMAND_AGE = 3600  # restart ke baad 1 h se purana command (jaise /kill) mat chalao; buttons dobara check hote hain
HELP = ("/pending - pending approvals\n/status - agents (killed, last run)\n/kill <agent|ALL> - stop (confirm)\n"
        "/unkill <agent|ALL>\n/help")


def log(msg):
    print(f"[telegram_bot] {msg}", file=sys.stderr)


def is_founder(update, founder):
    if "callback_query" in update:
        cq = update["callback_query"]
        return cq.get("from", {}).get("id") == founder and cq.get("message", {}).get("chat", {}).get("id") == founder
    msg = update.get("message") or {}
    chat = msg.get("chat", {})
    return chat.get("type") == "private" and chat.get("id") == founder and msg.get("from", {}).get("id") == founder


def _sender_id(update):
    if "callback_query" in update:
        return update["callback_query"].get("from", {}).get("id")
    return (update.get("message") or {}).get("from", {}).get("id")


def kill_names():
    """Sirf registered agents + ALL (agents.json) - anjaan naam pe kill file nahi."""
    try:
        return set(agent.load_registry()) | {"ALL"}
    except (OSError, ValueError, KeyError):
        return {"ALL"}


def on_command(text, founder):
    parts = text.split()
    cmd, arg = parts[0].split("@")[0].lower(), (parts[1] if len(parts) > 1 else "")
    if cmd == "/status":
        telegram.send(agent.status_text()[:3500], chat_id=founder)
    elif cmd == "/pending":
        pending = approvals.list_pending()
        if not pending:
            telegram.send("No pending approvals.", chat_id=founder)
        for rec in pending[:10]:
            telegram.send(approvals.proposal_card(rec), approvals.approval_buttons(rec["id"]), chat_id=founder)
    elif cmd in ("/kill", "/unkill"):
        if arg not in kill_names() or len(arg) > 60:
            telegram.send(f"Unknown agent. Use one of: {', '.join(sorted(kill_names()))}", chat_id=founder)
        elif cmd == "/kill":
            telegram.send(f"Stop {arg}? It halts before its next read/write.",
                          [[("🛑 Yes, kill", f"k:{arg}"), ("Cancel", "x")]], chat_id=founder)
        else:
            telegram.send(agent.set_kill(arg, False), chat_id=founder)
    else:
        telegram.send(HELP, chat_id=founder)


def on_callback(cq, founder):
    data, cid, msg = cq.get("data", ""), cq.get("id"), cq.get("message", {})
    mid = msg.get("message_id")
    kind, _, rest = data.partition(":")
    if kind in ("a", "r"):
        try:
            status = approvals.decide(rest, "approve" if kind == "a" else "reject", "founder", note="telegram")
            telegram.answer(cid, status)
            telegram.edit(founder, mid, f"{msg.get('text', '')}\n\n→ {status.upper()} (telegram)")
        except (approvals.NotExecutable, KeyError) as e:
            telegram.answer(cid, f"not changed: {type(e).__name__}")
    elif kind == "k" and rest in kill_names():
        result = agent.set_kill(rest, True)
        telegram.answer(cid, "killed")
        telegram.edit(founder, mid, result)
    elif kind == "d":
        day, _, rest2 = rest.partition(":")
        pid, _, sign = rest2.partition(":")
        import deal_finder
        ok = pid.isdigit() and sign in "+-" and len(sign) == 1 and deal_finder.record_rating(day, int(pid), sign == "+")
        telegram.answer(cid, ("👍 saved" if sign == "+" else "👎 saved") if ok else "not a current deal")
    elif kind == "x":
        telegram.answer(cid, "cancelled")
        telegram.edit(founder, mid, "Cancelled.")
    else:
        telegram.answer(cid, "unknown button")


def handle(update, founder, now=None):
    if not is_founder(update, founder):
        log(f"ignored update from {_sender_id(update)}")
        return
    if "callback_query" in update:
        on_callback(update["callback_query"], founder)
        return
    msg = update["message"]
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    if (now or time.time()) - msg.get("date", 0) > MAX_COMMAND_AGE:
        log("skipped stale command")
        return
    on_command(text, founder)


def load_offset():
    try:
        with open(_store.path_for(OFFSET_FILE)) as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def save_offset(offset):
    path = _store.path_for(OFFSET_FILE)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(str(offset))
    os.replace(tmp, path)


def run_once(founder, poll_timeout=50):
    """Ek getUpdates pass. Har update ke BAAD offset save (crash = dobara handle; handlers idempotent hain)."""
    updates = telegram.api("getUpdates", {"offset": load_offset(), "timeout": poll_timeout,
                                          "allowed_updates": ["message", "callback_query"]}, timeout=poll_timeout + 10)
    for u in updates:
        handle(u, founder)
        save_offset(u["update_id"] + 1)
    return len(updates)


def whoami():
    """Setup: jisne bot ko /start bheja uska chat id key file mein append (exactly 1 private chat ho tabhi)."""
    cfg = telegram.config()
    if not cfg:
        print("no bot token in the key file - do the BotFather setup first")
        return 2
    if cfg["chat_id"]:
        print("TELEGRAM_FOUNDER_CHAT_ID already set - not changing it")
        return 2
    chats = {}
    for u in telegram.api("getUpdates", {"timeout": 0}, cfg=cfg):
        m = u.get("message") or {}
        if m.get("chat", {}).get("type") == "private":
            chats[m["chat"]["id"]] = m.get("from", {}).get("username", "")
    for cid, user in chats.items():
        print(f"chat id: {cid}  username: @{user}")
    if len(chats) != 1:
        print("need exactly 1 private chat that sent /start - nothing written")
        return 2
    with open(telegram.keyfile(), "a") as f:
        f.write(f"\nTELEGRAM_FOUNDER_CHAT_ID={next(iter(chats))}\n")
    os.chmod(telegram.keyfile(), 0o600)
    print("saved")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--whoami"]:
        return whoami()
    cfg = telegram.config()
    if not cfg or not cfg["chat_id"]:
        log("not configured (token + TELEGRAM_FOUNDER_CHAT_ID needed)")
        return 2
    backoff = 5
    while True:
        try:
            run_once(cfg["chat_id"])
            backoff = 5
        except telegram.TelegramError as e:
            if " 401" in str(e):
                log("token rejected (401) - stopping")
                return 1
            log(f"poll error: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    sys.exit(main())
