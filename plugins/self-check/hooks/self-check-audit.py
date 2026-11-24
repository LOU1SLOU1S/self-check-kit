#!/usr/bin/env python3
"""Report how the self-check Stop hooks behaved across your sessions (Claude Code and Codex).

Usage:
    python3 self-check-audit.py              # last 7 days, both agents
    python3 self-check-audit.py --days 30
    python3 self-check-audit.py --all
    python3 self-check-audit.py --agent codex
    python3 self-check-audit.py --path <transcript.jsonl>

Per session:
  judged - Claude Code: turns where the self-check hooks ran (stop_hook_summary records).
           Codex: completed turns (Codex doesn't record hook runs, so this is an upper bound).
  blocks - times a self-check block reason was fed back to the agent.
  errors - Claude Code only: hook runs that reported an error.
Each block is printed with the reply that triggered it.
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selfcheck_lib as lib  # noqa: E402

CLAUDE_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
CODEX_GLOB = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"),
                          "sessions", "*", "*", "*", "rollout-*.jsonl")
# Text that only appears where the hooks' own source/prompt is quoted, not in a real block.
EXCLUDE = ("<quote the claim briefly>", "EVIDENCE_REASON", "BLOCK_MARKERS", "CLAIM_REASON")


def find_marker(txt):
    if not txt or any(x in txt for x in EXCLUDE):
        return None
    for marker in lib.BLOCK_MARKERS:
        if marker in txt:
            start = txt.find(marker)
            return txt[start:start + 300].replace("\n", " ")
    return None


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    return None
                parts.append(block.get("text") or "")
        return "\n".join(parts)
    return None


def is_ours(info):
    cmd = (info.get("command") or "") + (info.get("promptText") or "")
    return "self-check-stop.py" in cmd or "verification judge" in cmd


def audit_claude(rows):
    title, judged, errors, blocks, last = None, 0, 0, [], ""
    for row in rows:
        kind = row.get("type")
        if row.get("isSidechain"):
            continue
        if kind == "custom-title":
            title = row.get("customTitle")
        elif kind == "assistant":
            for b in (row.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    last = b["text"]
        elif kind == "system" and row.get("subtype") == "stop_hook_summary":
            if any(is_ours(i) for i in row.get("hookInfos") or []):
                judged += 1
                errors += len(row.get("hookErrors") or [])
        # Only rows that carry feedback to the agent; others (e.g. api-request-blob)
        # hold copies of the agent's own tool calls and would give false positives.
        reason = None
        if kind == "user":
            reason = find_marker(text_of((row.get("message") or {}).get("content")))
        elif kind == "attachment":
            reason = find_marker(json.dumps(row.get("attachment")))
        if reason:
            blocks.append((reason, last[:200].replace("\n", " ")))
    return title, judged, blocks, errors


def audit_codex(rows):
    turns, blocks, last = 0, [], ""
    for row in rows:
        p = lib._payload(row)
        if row.get("type") == "event_msg" and p.get("type") == "task_complete":
            turns += 1
        if p.get("type") == "message" and p.get("role") in ("assistant", "user"):
            text = "\n".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
            if p.get("role") == "assistant":
                last = text or last
            else:  # Codex feeds a block reason back as a new user prompt
                reason = find_marker(text)
                if reason:
                    blocks.append((reason, last[:200].replace("\n", " ")))
    return None, turns, blocks, 0


def audit(path):
    rows = lib.load_rows(path)
    fmt = lib.detect_format(rows)
    result = audit_codex(rows) if fmt == "codex" else audit_claude(rows)
    return (fmt,) + result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--agent", choices=("claude", "codex", "both"), default="both")
    ap.add_argument("--path", help="audit a single transcript file")
    args = ap.parse_args()

    if args.path:
        files = [args.path]
    else:
        cutoff = 0 if args.all else time.time() - args.days * 86400
        pats = {"claude": [CLAUDE_GLOB], "codex": [CODEX_GLOB], "both": [CLAUDE_GLOB, CODEX_GLOB]}[args.agent]
        files = [f for p in pats for f in glob.glob(p) if os.path.getmtime(f) >= cutoff]
        # Codex keeps no record of hook runs, so only count sessions active since the hooks were installed.
        codex_script = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"),
                                    "hooks", "self-check", "self-check-stop.py")
        installed = os.path.getmtime(codex_script) if os.path.exists(codex_script) else None
        files = [f for f in files if f.startswith(CLAUDE_GLOB.split("*")[0])
                 or (installed is not None and os.path.getmtime(f) >= installed)]
    files.sort(key=os.path.getmtime)

    totals = {"claude": [0, 0, 0], "codex": [0, 0, 0]}
    for f in files:
        fmt, title, judged, blocks, errors = audit(f)
        if fmt == "claude" and not judged and not blocks:
            continue  # session from before the hooks were installed
        if fmt == "codex" and not blocks and not args.path:
            totals["codex"][0] += judged
            continue  # keep Codex output short: only sessions with blocks
        t = totals[fmt]
        t[0] += judged
        t[1] += len(blocks)
        t[2] += errors
        name = title or os.path.basename(f)[:40]
        label = "judged" if fmt == "claude" else "turns"
        print("[%s] %-40s %s=%-4d blocks=%-3d errors=%d" % (fmt, name[:40], label, judged, len(blocks), errors))
        for reason, reply in blocks:
            print("    BLOCK: %s" % reason)
            print("      after reply: %s" % reply)
    print("-" * 70)
    for fmt, (j, b, e) in totals.items():
        if not j and not b:
            continue
        label = "judged" if fmt == "claude" else "turns (upper bound)"
        rate = (100.0 * b / j) if j else 0.0
        print("%-6s %s=%d blocks=%d (%.1f%%) errors=%d" % (fmt.upper(), label, j, b, rate, e))
    if not any(t[1] for t in totals.values()):
        print("No blocks found.")


if __name__ == "__main__":
    main()
