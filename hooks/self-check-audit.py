#!/usr/bin/env python3
"""Report how the self-check Stop hooks behaved across your Claude Code sessions.

Usage:
    python3 ~/.claude/hooks/self-check-audit.py            # last 7 days
    python3 ~/.claude/hooks/self-check-audit.py --days 30
    python3 ~/.claude/hooks/self-check-audit.py --all      # every session

For each session it counts:
  judged  - turns where the self-check hooks ran (stop_hook_summary records)
  blocks  - times a self-check block reason was fed back to Claude
  errors  - hook runs that reported an error
and prints each block with the reply that triggered it.
"""
import argparse
import glob
import json
import os
import time

PROJECTS = os.path.expanduser("~/.claude/projects")
# Exact openings of the two block reasons (script hook, prompt judge).
MARKERS = ("self-check: your reply has a `Verified:` line", "self-check: you claimed")
# Text that only appears where the hooks' own source/prompt is quoted, not in a real block.
EXCLUDE = ("<quote the claim briefly>", "EVIDENCE_TOOLS", "MARKERS = (")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    return None  # tool output, not hook feedback
                parts.append(block.get("text") or "")
        return "\n".join(parts)
    return None


def is_ours(info):
    cmd = info.get("command") or ""
    prompt = info.get("promptText") or ""
    return "self-check-stop.py" in cmd or "verification judge" in (cmd + prompt)


def block_reason(row):
    """Return the self-check block text if this row carries one, else None."""
    if row.get("isSidechain") or row.get("type") == "assistant":
        return None
    if row.get("type") == "system" and row.get("subtype") == "stop_hook_summary":
        return None  # contains the judge prompt, which includes the marker
    # Only rows that carry feedback to Claude. Others (e.g. api-request-blob)
    # hold copies of Claude's own tool calls and would give false positives.
    candidates = []
    if row.get("type") == "user":
        candidates.append(text_of((row.get("message") or {}).get("content")))
    elif row.get("type") == "attachment":
        candidates.append(json.dumps(row.get("attachment")))
    for txt in candidates:
        if not txt or any(x in txt for x in EXCLUDE):
            continue
        for marker in MARKERS:
            if marker in txt:
                start = txt.find(marker)
                return txt[start:start + 300].replace("\n", " ")
    return None


def audit(path):
    judged = errors = 0
    blocks = []
    title = None
    last_reply = ""
    with open(path) as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            kind = row.get("type")
            if kind == "custom-title":
                title = row.get("customTitle")
            elif kind == "assistant" and not row.get("isSidechain"):
                for block in (row.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                        last_reply = block["text"]
            elif kind == "system" and row.get("subtype") == "stop_hook_summary":
                if any(is_ours(i) for i in row.get("hookInfos") or []):
                    judged += 1
                    errors += len(row.get("hookErrors") or [])
            reason = block_reason(row)
            if reason:
                blocks.append((reason, last_reply[:200].replace("\n", " ")))
    return title, judged, blocks, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--path", help="audit a single transcript file")
    args = ap.parse_args()

    if args.path:
        files = [args.path]
    else:
        cutoff = 0 if args.all else time.time() - args.days * 86400
        files = [
            f for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl"))
            if os.path.getmtime(f) >= cutoff
        ]
    files.sort(key=os.path.getmtime)

    tot_j = tot_b = tot_e = 0
    for f in files:
        title, judged, blocks, errors = audit(f)
        if not judged and not blocks:
            continue
        tot_j += judged
        tot_b += len(blocks)
        tot_e += errors
        name = title or os.path.basename(f)[:8]
        folder = os.path.basename(os.path.dirname(f))
        print("%-40s judged=%-4d blocks=%-3d errors=%d   (%s)" % (name[:40], judged, len(blocks), errors, folder))
        for reason, reply in blocks:
            print("    BLOCK: %s" % reason)
            print("      after reply: %s" % reply)
    print("-" * 70)
    rate = (100.0 * tot_b / tot_j) if tot_j else 0.0
    print("TOTAL judged=%d blocks=%d (%.1f%%) errors=%d" % (tot_j, tot_b, rate, tot_e))
    if tot_j and not tot_b:
        print("No blocks yet. The block path is still unproven in live use, not confirmed broken.")


if __name__ == "__main__":
    main()
