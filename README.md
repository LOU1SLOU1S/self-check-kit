# self-check

A Claude Code skill and two Stop hooks that make Claude **check before it claims**.

Language models sound the same whether they're right or guessing. The usual failures are claiming "fixed, it works now" without running anything, stating an API name or CLI flag that doesn't exist, drifting away from the original goal on long tasks, and acting on unstated assumptions. This kit doesn't give Claude a better sense of when it's guessing. Instead it builds a habit of checking against reality, plus a guard at the end of every turn.

## What's in it

| Piece | Installed to | What it does |
|---|---|---|
| **Skill** `self-check` | `~/.claude/skills/self-check/SKILL.md` | Three rules: **Verify claims** (no "done/works" without running it; no API, flag or path as fact without reading it), **Hold the thread** (write down the goal on long tasks, say out loud when changing approach), **Ask or assume** (ask only when it matters and can't be looked up; otherwise state the assumption). |
| **CLAUDE.md rule** | `~/.claude/CLAUDE.md` | One line telling Claude when to load the skill. Skills only load when they seem relevant, and the moment just before saying "fixed" is when Claude is least likely to think of it. |
| **Script hook** | `~/.claude/hooks/self-check-stop.py` | If Claude's final reply has a `Verified:` line but no evidence tool (Bash, Read, Grep, a fetch, a browser check…) ran since your last message, it blocks the turn and makes Claude run the check or relabel the claim. Takes about 0.1 s. |
| **Prompt judge** | `~/.claude/settings.json` (Stop hook) | A small model reads Claude's final reply. If it claims done/fixed/works (or "should work") with neither a `Verified:` nor an `Unverified:` line, the judge sends it back. Takes about 1–4.5 s per turn. |
| **Audit** | `~/.claude/hooks/self-check-audit.py` | Reports how many turns were judged, blocked or errored across your sessions. |

The convention Claude follows:

```
Verified: ran pytest tests/test_auth.py → 14 passed, 0 failed
Unverified: the retry fixes the timeout — check by running the integration suite
```

## Install

Requirements: Claude Code, Python 3.9+, macOS or Linux (bash).

```bash
git clone <this repo> self-check-kit
cd self-check-kit
./install.sh
```

Then **start a new Claude Code session**.

The installer works at user level, so the kit applies in every project. It's safe on an existing setup:
- It backs up `settings.json` to `settings.json.bak-<timestamp>` first.
- It **merges** the hooks in and leaves your other settings and hooks alone.
- It adds the CLAUDE.md rule between `<!-- self-check:start/end -->` markers and keeps the rest of the file.
- Re-running it updates the kit in place and never duplicates anything.

### Manual install

1. Copy `skill/self-check/` to `~/.claude/skills/self-check/`.
2. Copy both files in `hooks/` to `~/.claude/hooks/`.
3. Merge `config/settings-hooks.json` into the `"hooks"` key of `~/.claude/settings.json`.
4. Append `config/CLAUDE-snippet.md` to `~/.claude/CLAUDE.md`.

### Uninstall

```bash
./uninstall.sh
```

This removes only this kit's skill, hooks and CLAUDE.md block.

## Using it

There's nothing to do day to day. Claude loads the skill when needed, and the hooks run at the end of each turn. You'll notice:
- Replies that claim success end with a `Verified:` line naming what was run and what it showed.
- Claims that weren't checked are labeled `Unverified:`, with how to check them.
- Occasionally a turn continues after Claude's reply. That's a hook sending back an unbacked claim.

To see how it's behaving:

```bash
python3 ~/.claude/hooks/self-check-audit.py            # last 7 days
python3 ~/.claude/hooks/self-check-audit.py --days 30
python3 ~/.claude/hooks/self-check-audit.py --all
```

Each block is printed with the reply that caused it, so you can tell real catches from false alarms.

## Tests

```bash
python3 tests/run_tests.py
```

This runs 14 offline checks: the script hook, the audit, and install/uninstall in a throwaway directory. No Claude account or network is needed. See [TEST-RESULTS.md](TEST-RESULTS.md) for those results and for the live tests in real Claude Code sessions.

## Limits (read these)

- **The judge's blocking hasn't been seen live yet.** In staged tests Claude refused to make the false claims, so there was nothing to block. Both hooks run without errors on every turn and allow correct replies. Whether the judge actually sends back a real unbacked claim is still unproven. Run the audit after normal use.
- **The judge only sees Claude's final message**, not its tool calls. That's why the script hook exists: it reads the transcript to confirm that a `Verified:` line has some real tool call behind it. It can't check that it was the *right* tool call.
- **The judge leans toward honest substance over format.** A plain admission like "I didn't run it, so I can't say it works" passes even without an `Unverified:` label.
- **Technical details aren't policed by the hooks.** Unchecked APIs, flags and paths are covered by the skill only. A judge that sees just the final message can't tell whether Claude read the docs, and it would block nearly every technical answer.
- **Cost:** the judge adds a small model call and 1–4.5 s to every turn, including plain chat.
- **The audit recognizes a block by the text of its reason.** Claude Code's exact transcript format for a real block hasn't been seen yet. If a reply is visibly blocked and the audit still shows `blocks=0`, the detection needs updating.

## Layout

```
skill/self-check/SKILL.md      the skill
hooks/self-check-stop.py       Stop script hook
hooks/self-check-audit.py      audit report
config/settings-hooks.json     the two Stop hooks (script + prompt judge)
config/CLAUDE-snippet.md       the CLAUDE.md rule
install.sh / uninstall.sh
tests/run_tests.py
TEST-RESULTS.md
```

## License

MIT. See [LICENSE](LICENSE).
