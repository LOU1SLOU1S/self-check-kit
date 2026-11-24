#!/usr/bin/env bash
# Remove the self-check skill, its Stop hooks, and its CLAUDE.md rule. Leaves everything else alone.
set -euo pipefail
TARGET="${SELF_CHECK_TARGET:-$HOME/.claude}"

rm -rf "$TARGET/skills/self-check"
rm -f "$TARGET/hooks/self-check-stop.py" "$TARGET/hooks/self-check-audit.py"

python3 - "$TARGET" <<'PY'
import json, os, sys
target = sys.argv[1]

def ours(h):
    return "self-check-stop.py" in h.get("command", "") or "verification judge" in h.get("prompt", "")

path = os.path.join(target, "settings.json")
if os.path.exists(path):
    with open(path) as fh:
        settings = json.load(fh)
    hooks = settings.get("hooks", {})
    kept = []
    for group in hooks.get("Stop", []):
        rest = [h for h in group.get("hooks", []) if not ours(h)]
        if rest:
            group["hooks"] = rest
            kept.append(group)
    if kept:
        hooks["Stop"] = kept
    else:
        hooks.pop("Stop", None)
    if not hooks:
        settings.pop("hooks", None)
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

START, END = "<!-- self-check:start -->", "<!-- self-check:end -->"
md = os.path.join(target, "CLAUDE.md")
if os.path.exists(md):
    text = open(md).read()
    if START in text and END in text:
        pre, rest = text.split(START, 1)
        text = (pre.rstrip() + "\n" + rest.split(END, 1)[1].lstrip("\n")).strip()
        with open(md, "w") as fh:
            fh.write(text + "\n" if text else "")
    elif "load the `self-check` skill" in text:
        print("Note: CLAUDE.md has the self-check rule without markers; remove it by hand.")
PY
echo "Removed self-check from $TARGET. Start a new session for it to take effect."
