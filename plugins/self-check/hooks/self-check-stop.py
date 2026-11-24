#!/usr/bin/env python3
"""Stop hook for the self-check skill (Claude Code and Codex).

Checks, in order:
  1. Evidence check (always): a `Verified:` line with no evidence tool call since
     the turn started -> block, and tell the agent to run it or relabel `Unverified:`.
  2. Phrase judge (--claims, used for Codex, which has no AI judge hook): a success
     claim like "fixed" / "works now" / "should work" with no Verified:/Unverified:
     line -> block.
  3. Soft check (always): a `Verified:` line naming a backticked command that
     doesn't match anything run this turn -> warning to the user, no block.

Blocks at most once per turn (respects stop_hook_active). Fails open on any error.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selfcheck_lib as lib  # noqa: E402

EVIDENCE_REASON = (
    "self-check: your reply has a `Verified:` line, but no evidence tool call "
    "(a shell command, file read, search, fetch, browser or simulator check, ...) happened "
    "this turn. Either run the check now and report its real output, or replace the line "
    "with `Unverified: <claim> — check by <how>`."
)
CLAIM_REASON = (
    "self-check: you claimed \"%s\" without evidence. Run the check and add "
    "`Verified: <what you ran> → <result>`, or add `Unverified: <claim> — check by <how>`."
)


def decide(data, claims):
    """Return the hook's JSON output as a dict, or None to allow silently."""
    if data.get("stop_hook_active"):
        return None
    message = data.get("last_assistant_message") or ""
    path = data.get("transcript_path")
    has_verified = bool(lib.VERIFIED_RE.search(message))

    calls = None
    if has_verified:
        if not path or not os.path.exists(path):
            return None  # can't check; fail open
        calls = lib.tools_this_turn(path, data.get("turn_id"))
        if not any(c["evidence"] for c in calls):
            return {"decision": "block", "reason": EVIDENCE_REASON}

    if claims:
        claim = lib.find_unlabeled_claim(message)
        if claim:
            return {"decision": "block", "reason": CLAIM_REASON % claim}

    if has_verified and calls:
        missing = lib.unmatched_commands(message, calls)
        if missing:
            return {"systemMessage": "self-check (warning): the Verified line names `%s`, "
                                     "which doesn't match any command run this turn." % missing[0]}
    return None


def main():
    claims = "--claims" in sys.argv[1:]
    data = json.load(sys.stdin)
    out = decide(data, claims)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail open
        sys.stderr.write("self-check-stop: %s\n" % exc)
        sys.exit(0)
