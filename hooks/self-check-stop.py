#!/usr/bin/env python3
"""Stop hook for the self-check skill.

If Claude's final message contains a `Verified:` line, confirm that at least one
evidence-type tool call happened since the user's last real message. If none did,
block the stop and tell Claude to run the check or relabel the claim `Unverified:`.

Fails open: any error -> allow the stop (exit 0), with a note on stderr.
"""
import json
import re
import sys

EVIDENCE_TOOLS = {
    "Bash", "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Agent", "Task",
    "NotebookRead", "Monitor",
}
EVIDENCE_PREFIXES = (
    "mcp__Claude_Browser__",
    "mcp__claude-in-chrome__",
    "mcp__computer-use__",
    "mcp__Claude_Code_iOS_Simulator__",
    "mcp__terminal__",
)
# A line starting with "Verified:" (optionally after markdown bullets/bold/quote).
# Case-sensitive, so "Unverified:" never matches.
VERIFIED_RE = re.compile(r"^[\s>*_\-]*Verified\**\s*:", re.MULTILINE)


def is_evidence(name):
    return name in EVIDENCE_TOOLS or name.startswith(EVIDENCE_PREFIXES)


def is_human_prompt(row):
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain"):
        return False
    origin = row.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    # Older transcripts without `origin`: a non-tool-result user message.
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list) and content:
        return content[0].get("type") != "tool_result"
    return False


def evidence_since_last_prompt(transcript_path):
    rows = []
    with open(transcript_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    start = 0
    for i, row in enumerate(rows):
        if is_human_prompt(row):
            start = i
    found = []
    for row in rows[start:]:
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use" and is_evidence(block.get("name", "")):
                found.append(block.get("name"))
    return found


def main():
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return 0
    message = data.get("last_assistant_message") or ""
    if not VERIFIED_RE.search(message):
        return 0
    path = data.get("transcript_path")
    if not path:
        return 0
    if evidence_since_last_prompt(path):
        return 0
    print(json.dumps({
        "decision": "block",
        "reason": (
            "self-check: your reply has a `Verified:` line, but no evidence tool call "
            "(Bash, Read, Grep, a fetch, a browser/simulator check, ...) happened since "
            "the user's last message. Either run the check now and report its real "
            "output, or replace the line with `Unverified: <claim> — check by <how>`."
        ),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail open
        sys.stderr.write("self-check-stop: %s\n" % exc)
        sys.exit(0)
