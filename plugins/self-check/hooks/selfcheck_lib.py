"""Shared core for the self-check hooks: transcript reading and claim detection.

Supports two transcript formats:
  - Claude Code: ~/.claude/projects/<project>/<session>.jsonl
  - Codex:       ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
Neither format is a stable public interface, so every reader here fails soft:
unknown rows are skipped, never raised on.
"""
import json
import re

# ---------------------------------------------------------------- lines & markers

# A line starting with "Verified:" / "Unverified:" (after optional bullets, quote, bold).
# Case-sensitive, so "Unverified:" never matches VERIFIED_RE.
VERIFIED_RE = re.compile(r"^[\s>*_\-]*Verified\**\s*:(.*)$", re.MULTILINE)
UNVERIFIED_RE = re.compile(r"^[\s>*_\-]*Unverified\**\s*:", re.MULTILINE)

# Exact openings of the block reasons, used by the audit to count blocks.
BLOCK_MARKERS = (
    "self-check: your reply has a `Verified:` line",  # evidence check
    "self-check: you claimed",                         # prompt judge (Claude) / phrase judge (Codex)
)


# ---------------------------------------------------------------- transcript reading

def load_rows(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def detect_format(rows):
    for row in rows[:50]:
        if row.get("type") in ("session_meta", "response_item", "event_msg", "turn_context"):
            return "codex"
        if row.get("type") in ("user", "assistant") and "message" in row:
            return "claude"
    return "claude"


# --- Claude Code

CLAUDE_EVIDENCE = {
    "Bash", "Read", "Grep", "Glob", "WebFetch", "WebSearch", "Agent", "Task",
    "NotebookRead", "Monitor",
}
CLAUDE_EVIDENCE_PREFIXES = (
    "mcp__Claude_Browser__", "mcp__claude-in-chrome__", "mcp__computer-use__",
    "mcp__Claude_Code_iOS_Simulator__", "mcp__terminal__",
)


def _claude_is_human_prompt(row):
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain"):
        return False
    origin = row.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list) and content:
        return isinstance(content[0], dict) and content[0].get("type") != "tool_result"
    return False


def _claude_tools_this_turn(rows):
    start = 0
    for i, row in enumerate(rows):
        if _claude_is_human_prompt(row):
            start = i
    calls = []
    for row in rows[start:]:
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        for block in (row.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                inp = block.get("input") or {}
                cmd = inp.get("command") if isinstance(inp, dict) else None
                calls.append({
                    "name": name,
                    "command": cmd if isinstance(cmd, str) else None,
                    "evidence": name in CLAUDE_EVIDENCE or name.startswith(CLAUDE_EVIDENCE_PREFIXES),
                })
    return calls


# --- Codex

# Codex tool names change between versions, so this is a deny-list: anything
# that isn't plainly an edit/planning/UI tool counts as a check.
CODEX_NOT_EVIDENCE = {
    "apply_patch", "update_plan", "request_user_input", "request_user_input_async", "sleep",
}


def _payload(row):
    p = row.get("payload")
    return p if isinstance(p, dict) else {}


def _codex_tools_this_turn(rows, turn_id=None):
    start = None
    for i, row in enumerate(rows):
        p = _payload(row)
        if row.get("type") == "event_msg" and p.get("type") == "task_started":
            if turn_id is None or p.get("turn_id") == turn_id:
                start = i
    if start is None:  # fall back to the last real user message
        start = 0
        for i, row in enumerate(rows):
            p = _payload(row)
            if p.get("type") == "message" and p.get("role") == "user":
                content = p.get("content") or []
                text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
                if text.lstrip()[:1] not in ("<", "#"):
                    start = i
    calls = []
    for row in rows[start:]:
        p = _payload(row)
        kind = p.get("type")
        if kind in ("function_call", "custom_tool_call", "local_shell_call", "web_search_call"):
            name = p.get("name") or kind
            cmd = None
            if kind == "custom_tool_call" and isinstance(p.get("input"), str):
                cmd = p["input"]
            elif kind == "function_call":
                try:
                    args = json.loads(p.get("arguments") or "{}")
                    c = args.get("cmd") or args.get("command")
                    cmd = " ".join(c) if isinstance(c, list) else c
                except (ValueError, AttributeError):
                    cmd = None
            elif kind == "local_shell_call":
                c = (p.get("action") or {}).get("command")
                cmd = " ".join(c) if isinstance(c, list) else c
            calls.append({"name": name, "command": cmd if isinstance(cmd, str) else None,
                          "evidence": name not in CODEX_NOT_EVIDENCE})
    return calls


def tools_this_turn(path, turn_id=None):
    """Tool calls since the start of the current turn: [{name, command, evidence}]."""
    rows = load_rows(path)
    if detect_format(rows) == "codex":
        return _codex_tools_this_turn(rows, turn_id)
    return _claude_tools_this_turn(rows)


# ---------------------------------------------------------------- claim detection (phrase judge)

# Success claims and "should work" hedges. Deliberately narrow: a false block
# is more annoying than a miss, because the AI judge (Claude) or the user catches misses.
CLAIM_RE = re.compile(
    r"\b("
    r"(?:it|this|that|everything)(?:'s| is)? (?:now )?(?:works?|working)(?: now)?"
    r"|works now|working now|now works"
    r"|(?:is|are|has been|have been|got) (?:now )?(?:fixed|resolved)"
    r"|i(?:'ve| have)? (?:fixed|resolved)"
    r"|fixed it|bug is fixed|issue is (?:fixed|resolved)"
    r"|all (?:\d+ )?tests (?:now )?pass(?:ed|ing)?|tests (?:now )?pass(?:ed|ing)?"
    r"|should (?:now )?(?:work|fix|resolve|pass)"
    r"|(?:that|this) (?:will|should) (?:fix|resolve)"
    r")\b",
    re.IGNORECASE,
)
# A claim this close after a negation is a disclaimer, not a claim:
# "I didn't run it, so I can't say it works".
NEGATION_RE = re.compile(
    r"\b(not|n't|never|no|cannot|can't|unverified|untested|unclear|unsure|if|whether|until)\b[^.!?\n]{0,40}$",
    re.IGNORECASE,
)
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
# A reply that admits something still fails is a partial report, not a success claim:
# "I fixed the commas, but one test still fails."
FAILURE_RE = re.compile(
    r"\b(still (?:fails?|failing|broken|errors?)"
    r"|(?:\d+ )?tests? (?:still )?fail(?:s|ed|ing)?"
    r"|fail(?:ed|ing|ures?)\b"
    r"|not (?:yet )?(?:passing|working)"
    r"|(?:doesn't|does not|didn't|did not|don't|won't) (?:pass|work)"
    r")",
    re.IGNORECASE,
)


def find_unlabeled_claim(message):
    """Return the first success claim with no Verified:/Unverified: label, else None."""
    if not message or VERIFIED_RE.search(message) or UNVERIFIED_RE.search(message):
        return None
    text = CODE_RE.sub(" ", message)
    if FAILURE_RE.search(text):
        return None
    for match in CLAIM_RE.finditer(text):
        before = text[max(0, match.start() - 60):match.start()]
        if NEGATION_RE.search(before):
            continue
        if text[match.end():match.end() + 1] == "?":
            continue  # a question, not a claim
        return match.group(0)
    return None


# ---------------------------------------------------------------- soft check: does the Verified line match a real command?

def verified_commands(message):
    """Backticked spans in Verified: lines that look like commands."""
    spans = []
    for m in VERIFIED_RE.finditer(message or ""):
        for span in re.findall(r"`([^`\n]+)`", m.group(1)):
            span = span.strip()
            if " " in span or "/" in span or "." in span:
                spans.append(span)
    return spans


def _norm(s):
    return re.sub(r"\s+", " ", s.replace('"', "").replace("'", "")).strip().lower()


def unmatched_commands(message, calls):
    ran = [_norm(c["command"]) for c in calls if c.get("command")]
    missing = []
    for span in verified_commands(message):
        key = " ".join(_norm(span).split()[:3])
        if key and not any(key in r for r in ran):
            missing.append(span)
    return missing
