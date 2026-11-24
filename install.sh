#!/usr/bin/env bash
# Install the self-check skill, Stop hooks, and CLAUDE.md rule for Claude Code (user level).
# Safe to re-run: it replaces its own pieces and leaves everything else alone.
# Set SELF_CHECK_TARGET to install somewhere other than ~/.claude (used by the tests).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="${SELF_CHECK_TARGET:-$HOME/.claude}"

command -v python3 >/dev/null || { echo "python3 is required (the hooks are Python 3.9+)."; exit 1; }

mkdir -p "$TARGET/skills/self-check" "$TARGET/hooks"
cp "$SRC/skill/self-check/SKILL.md" "$TARGET/skills/self-check/SKILL.md"
cp "$SRC/hooks/self-check-stop.py" "$SRC/hooks/self-check-audit.py" "$TARGET/hooks/"
chmod +x "$TARGET/hooks/self-check-stop.py" "$TARGET/hooks/self-check-audit.py"
echo "✓ skill  → $TARGET/skills/self-check/SKILL.md"
echo "✓ hooks  → $TARGET/hooks/self-check-{stop,audit}.py"

python3 - "$SRC" "$TARGET" <<'PY'
import json, os, sys, time, shutil
src, target = sys.argv[1], sys.argv[2]

def ours(h):
    return "self-check-stop.py" in h.get("command", "") or "verification judge" in h.get("prompt", "")

# --- settings.json: merge our Stop hooks in, replacing any older copy of them ---
path = os.path.join(target, "settings.json")
settings = {}
if os.path.exists(path):
    with open(path) as fh:
        settings = json.load(fh)
    backup = "%s.bak-%d" % (path, int(time.time()))
    shutil.copy2(path, backup)
    print("✓ backup → %s" % backup)

with open(os.path.join(src, "config", "settings-hooks.json")) as fh:
    new_groups = json.load(fh)["hooks"]["Stop"]
for group in new_groups:
    for h in group["hooks"]:
        if "command" in h:
            h["command"] = h["command"].replace("$HOME/.claude", target)

hooks = settings.setdefault("hooks", {})
stop = hooks.get("Stop", [])
kept = []
for group in stop:
    rest = [h for h in group.get("hooks", []) if not ours(h)]
    if rest:
        group["hooks"] = rest
        kept.append(group)
hooks["Stop"] = kept + new_groups
with open(path, "w") as fh:
    json.dump(settings, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
print("✓ hooks  → %s (Stop: script check + prompt judge)" % path)

# --- CLAUDE.md: add the rule between markers, replacing an older copy ---
START, END = "<!-- self-check:start -->", "<!-- self-check:end -->"
md_path = os.path.join(target, "CLAUDE.md")
with open(os.path.join(src, "config", "CLAUDE-snippet.md")) as fh:
    block = "%s\n%s\n%s\n" % (START, fh.read().strip(), END)
text = open(md_path).read() if os.path.exists(md_path) else ""
if START in text and END in text:
    pre, rest = text.split(START, 1)
    post = rest.split(END, 1)[1].lstrip("\n")
    text = pre + block + post
elif "load the `self-check` skill" in text:
    block = None  # rule already present without markers; leave it
else:
    text = (text.rstrip() + "\n\n" if text.strip() else "") + block
if block is not None:
    with open(md_path, "w") as fh:
        fh.write(text)
print("✓ rule   → %s" % md_path)
PY

echo
echo "Done. Start a NEW Claude Code session to pick everything up."
echo "Check on it any time:  python3 \"$TARGET/hooks/self-check-audit.py\""
