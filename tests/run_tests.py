#!/usr/bin/env python3
"""Offline tests for the self-check kit. No Claude account or network needed.

    python3 tests/run_tests.py

Covers the Stop script hook (7 cases), the audit script (no false positives on
ordinary rows, detects injected blocks), and install/uninstall in a throwaway
directory. The prompt judge cannot be tested offline; see TEST-RESULTS.md.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP = os.path.join(ROOT, "hooks", "self-check-stop.py")
AUDIT = os.path.join(ROOT, "hooks", "self-check-audit.py")

HUMAN = {"type": "user", "origin": {"kind": "human"}, "message": {"content": "fix it"}}
BASH = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}}
EDIT = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {}}]}}

failures = []


def check(name, cond):
    print("%s %s" % ("PASS" if cond else "FAIL", name))
    if not cond:
        failures.append(name)


def transcript(d, name, rows):
    path = os.path.join(d, name)
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def stop_hook(path, active, msg):
    payload = {"transcript_path": path, "stop_hook_active": active, "last_assistant_message": msg}
    r = subprocess.run([sys.executable, STOP], input=json.dumps(payload),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return "block" if '"block"' in r.stdout else "allow", r.returncode


with tempfile.TemporaryDirectory() as d:
    no_ev = transcript(d, "no_ev.jsonl", [HUMAN, EDIT])
    ev = transcript(d, "ev.jsonl", [HUMAN, EDIT, BASH])
    old_ev = transcript(d, "old_ev.jsonl", [BASH, HUMAN, EDIT])

    print("== Stop script hook")
    cases = [
        ("Verified line, no evidence -> block", no_ev, False, "Fixed.\nVerified: ran tests -> pass", "block"),
        ("Verified line, evidence this turn -> allow", ev, False, "Fixed.\nVerified: ran tests -> pass", "allow"),
        ("evidence only before user's message -> block", old_ev, False, "Fixed.\n**Verified:** ran tests", "block"),
        ("Unverified line only -> allow", no_ev, False, "Unverified: works - check by running tests", "allow"),
        ("stop_hook_active -> allow (no loops)", no_ev, True, "Verified: x", "allow"),
        ("plain chat -> allow", no_ev, False, "Hello there", "allow"),
        ("missing transcript -> allow (fails open)", os.path.join(d, "nope.jsonl"), False, "Verified: x", "allow"),
    ]
    for name, path, active, msg, want in cases:
        got, code = stop_hook(path, active, msg)
        check(name, got == want and code == 0)

    print("== Audit script")
    summary = {"type": "system", "subtype": "stop_hook_summary",
               "hookInfos": [{"command": "python3 ~/.claude/hooks/self-check-stop.py"}], "hookErrors": []}
    noise = [
        {"type": "attachment", "attachment": {"type": "skill_listing",
                                              "content": "- self-check: Load BEFORE telling the user..."}},
        {"type": "api-request-blob",
         "message": {"content": "self-check: your reply has a `Verified:` line, but no evidence"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "self-check: you claimed X"}]}},
    ]
    clean = transcript(d, "clean.jsonl", [HUMAN, summary] + noise)
    out = subprocess.run([sys.executable, AUDIT, "--path", clean], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    check("no false positives from skill list / request copies / Claude's own text",
          "judged=1" in out and "blocks=0" in out)

    blocked = transcript(d, "blocked.jsonl", [
        HUMAN, summary,
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done, it works now."}]}},
        {"type": "user", "isMeta": True, "message": {"content": "self-check: you claimed \"it works\" without evidence."}},
        {"type": "attachment", "attachment": {"content": "self-check: your reply has a `Verified:` line, but no evidence"}},
    ])
    out = subprocess.run([sys.executable, AUDIT, "--path", blocked], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    check("detects injected blocks (hidden message + attachment)", "blocks=2" in out)

    print("== Install / uninstall (throwaway directory)")
    home = os.path.join(d, "claude")
    os.makedirs(home)
    with open(os.path.join(home, "settings.json"), "w") as fh:
        json.dump({"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}, fh)
    with open(os.path.join(home, "CLAUDE.md"), "w") as fh:
        fh.write("# My rules\n\nBe nice.\n")
    env = dict(os.environ, SELF_CHECK_TARGET=home)
    for _ in range(2):  # twice: re-running must not duplicate anything
        subprocess.run(["bash", os.path.join(ROOT, "install.sh")], env=env, check=True,
                       stdout=subprocess.DEVNULL)
    s = json.load(open(os.path.join(home, "settings.json")))
    cmds = [h.get("command", "") or h.get("prompt", "")[:30] for g in s["hooks"]["Stop"] for h in g["hooks"]]
    md = open(os.path.join(home, "CLAUDE.md")).read()
    check("install keeps existing settings and hooks", s.get("theme") == "dark" and "echo mine" in cmds)
    check("install adds both hooks exactly once (re-run safe)",
          sum("self-check-stop.py" in c for c in cmds) == 1 and len(cmds) == 3)
    check("install adds CLAUDE.md rule once, keeps existing text",
          md.count("self-check:start") == 1 and "Be nice." in md)
    check("installed files present", os.path.exists(os.path.join(home, "skills", "self-check", "SKILL.md")))

    subprocess.run(["bash", os.path.join(ROOT, "uninstall.sh")], env=env, check=True, stdout=subprocess.DEVNULL)
    s = json.load(open(os.path.join(home, "settings.json")))
    md = open(os.path.join(home, "CLAUDE.md")).read()
    check("uninstall removes only our pieces",
          s.get("theme") == "dark" and s["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo mine"
          and len(s["hooks"]["Stop"]) == 1 and "self-check" not in md and "Be nice." in md
          and not os.path.exists(os.path.join(home, "skills", "self-check")))

print()
print("%d failed" % len(failures) if failures else "All tests passed.")
sys.exit(1 if failures else 0)
