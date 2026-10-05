"""Shared append-only JSONL store for approvals and agent runs.

Phase 1 storage (spec docs/specs/2026-10-04-company-skills.md): files under LUXELLA_OPS_DIR
(default /root/luxella-ops, dir 700, files 600). Status changes are new event lines - the latest
line per id wins - so nothing is ever rewritten in place.
"""
import json
import os
import sys

DEFAULT_DIR = "/root/luxella-ops"


def ops_dir():
    path = os.environ.get("LUXELLA_OPS_DIR", DEFAULT_DIR)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def path_for(name):
    return os.path.join(ops_dir(), name)


def append(path, obj):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    os.chmod(path, 0o600)


def read_all(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = None
            if not isinstance(obj, dict) or "id" not in obj:
                print(f"[store] {os.path.basename(path)} line {n}: not a record, skipped", file=sys.stderr)
                continue
            out.append(obj)
    return out
