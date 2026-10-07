"""Telegram Bot API send helpers (spec docs/specs/2026-10-07-telegram-approvals.md). No poll loop here.

Key file (600): /root/.config/agent-keys/telegram-bot.env  (override: LUXELLA_TELEGRAM_KEYFILE; off: LUXELLA_TELEGRAM=0)
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_FOUNDER_CHAT_ID=...
The token lives only in the URL of each request; errors are re-raised WITHOUT the cause (the URL) so it never
reaches a log. send/edit/answer never raise - they return False/None.
"""
import json
import os
import sys
import urllib.request

DEFAULT_KEYFILE = "/root/.config/agent-keys/telegram-bot.env"


class TelegramError(Exception):
    pass


def keyfile():
    return os.environ.get("LUXELLA_TELEGRAM_KEYFILE", DEFAULT_KEYFILE)


def config():
    """{'token', 'chat_id' (int or None)} ya None (band / file nahi / token nahi)."""
    if os.environ.get("LUXELLA_TELEGRAM", "1") == "0":
        return None
    try:
        if os.stat(keyfile()).st_mode & 0o077:  # token file sirf root padh sake
            print("[telegram] key file is group/world readable - chmod 600 it; telegram disabled", file=sys.stderr)
            return None
        with open(keyfile()) as f:
            raw = f.read()
    except OSError:
        return None
    vals = {}
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip("'\"")
    if not vals.get("TELEGRAM_BOT_TOKEN"):
        return None
    cid = vals.get("TELEGRAM_FOUNDER_CHAT_ID", "")
    return {"token": vals["TELEGRAM_BOT_TOKEN"], "chat_id": int(cid) if cid.lstrip("-").isdigit() else None}


def api(method, params, timeout=15, cfg=None):
    cfg = cfg or config()
    if not cfg:
        raise TelegramError("telegram not configured")
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['token']}/{method}",
                                 data=json.dumps(params).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.load(r)
    except Exception as e:  # cause/URL mein token hai - chain mat karo
        raise TelegramError(f"{method}: {type(e).__name__} {getattr(e, 'code', '')}".strip()) from None
    if not body.get("ok"):
        raise TelegramError(f"{method}: not ok {body.get('error_code', '')}")
    return body.get("result")


def _markup(buttons):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}


def send(text, buttons=None, chat_id=None):
    cfg = config()
    if not cfg or not (chat_id or cfg["chat_id"]):
        return False
    params = {"chat_id": chat_id or cfg["chat_id"], "text": text[:4000], "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = _markup(buttons)
    try:
        api("sendMessage", params, cfg=cfg)
        return True
    except TelegramError:
        return False


def edit(chat_id, message_id, text):
    try:
        api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text[:4000]})
        return True
    except TelegramError:
        return False


def answer(callback_id, text=""):
    try:
        api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})
        return True
    except TelegramError:
        return False
