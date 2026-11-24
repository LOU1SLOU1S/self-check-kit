#!/usr/bin/env python3
"""Merge or remove self-check's hooks and rule in an agent's config. Used by install.sh / uninstall.sh.

    merge.py install   <agent> <home> <hooks.json|settings.json> <template> <rules file> <rule text file>
    merge.py uninstall <agent> <home> <hooks.json|settings.json> <rules file>

Only touches entries that belong to self-check; everything else is kept.
"""
import json
import os
import shutil
import sys
import time

START, END = "<!-- self-check:start -->", "<!-- self-check:end -->"
# Rule lines written by earlier versions without markers.
OLD_RULES = (
    "Before saying work is done/fixed/passing, or stating an API, flag, config key, version, or path "
    "as fact, load the `self-check` skill. On tasks over ~5 steps, or when a request is ambiguous, load it too.",
)


def ours(hook):
    return "self-check-stop.py" in hook.get("command", "") or "verification judge" in hook.get("prompt", "")


def strip_ours(settings):
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
    return settings


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        text = fh.read().strip()
    return json.loads(text) if text else {}


def write_json(path, data):
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def install(agent, home, hooks_path, template, rules_path, rule_file):
    os.makedirs(home, exist_ok=True)
    settings = load_json(hooks_path)
    if os.path.exists(hooks_path):
        backup = "%s.bak-%d" % (hooks_path, int(time.time()))
        shutil.copy2(hooks_path, backup)
        print("✓ backup → %s" % backup)
    with open(template) as fh:
        groups = json.load(fh)["hooks"]["Stop"]
    for group in groups:
        for h in group["hooks"]:
            if "command" in h:
                h["command"] = h["command"].replace("$HOME/.claude", home).replace("$CODEX_HOME", home)
    settings = strip_ours(settings)
    settings.setdefault("hooks", {}).setdefault("Stop", []).extend(groups)
    write_json(hooks_path, settings)
    print("✓ hooks  → %s" % hooks_path)

    with open(rule_file) as fh:
        block = "%s\n%s\n%s\n" % (START, fh.read().strip(), END)
    text = open(rules_path).read() if os.path.exists(rules_path) else ""
    if START in text and END in text:
        pre, rest = text.split(START, 1)
        text = pre + block + rest.split(END, 1)[1].lstrip("\n")
    else:
        for old in OLD_RULES:
            if old in text:
                text = text.replace(old + "\n", "").replace(old, "")
        text = (text.rstrip() + "\n\n" if text.strip() else "") + block
    with open(rules_path, "w") as fh:
        fh.write(text)
    print("✓ rule   → %s" % rules_path)


def uninstall(agent, home, hooks_path, rules_path):
    if os.path.exists(hooks_path):
        settings = strip_ours(load_json(hooks_path))
        if not settings.get("hooks"):
            settings.pop("hooks", None)
        write_json(hooks_path, settings)
    if os.path.exists(rules_path):
        text = open(rules_path).read()
        if START in text and END in text:
            pre, rest = text.split(START, 1)
            text = pre.rstrip() + "\n" + rest.split(END, 1)[1].lstrip("\n")
        for old in OLD_RULES:
            text = text.replace(old, "")
        text = text.strip()
        with open(rules_path, "w") as fh:
            fh.write(text + "\n" if text else "")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "install":
        install(*sys.argv[2:8])
    elif cmd == "uninstall":
        uninstall(*sys.argv[2:6])
    else:
        sys.exit("usage: merge.py install|uninstall ...")
