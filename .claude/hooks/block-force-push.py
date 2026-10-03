#!/usr/bin/env python3
"""
Block Force Push Hook
Denies `git push` with --force / -f / --force-with-lease / +refspec.
Parses the command into tokens, so heredocs and flags like `cut -f` don't match.
"""

import json
import re
import shlex
import sys


def is_force_push(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        # unparseable (e.g. unbalanced quotes) - fall back to a plain text check
        return bool(re.search(r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*(\s--force|\s-[a-zA-Z]*f\b|\s\+\S)", command))

    segment = []
    for tok in tokens + [";"]:
        if tok and all(c in ";&|()" for c in tok):
            if segment_is_force_push(segment):
                return True
            segment = []
        else:
            segment.append(tok)
    return False


def segment_is_force_push(seg):
    if "git" not in seg:
        return False
    args = seg[seg.index("git") + 1:]
    if "push" not in args:
        return False
    for arg in args[args.index("push") + 1:]:
        if arg.startswith("--force"):
            return True
        if re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", arg):
            return True
        if arg.startswith("+"):
            return True
    return False


def main():
    data = json.load(sys.stdin)
    command = data.get("tool_input", {}).get("command", "")
    if is_force_push(command):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Force push is blocked by hook",
        }}))


if __name__ == "__main__":
    main()
