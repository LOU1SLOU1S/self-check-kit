# self-check

A skill plus end-of-turn hooks that make AI coding agents **check before they claim**. Works with **Claude Code** and **Codex**.

Agents sound just as sure when they're guessing as when they're right. The usual failures are claiming "fixed, it works now" without running anything, citing an API or CLI flag that doesn't exist, drifting off the goal on long tasks, and acting on unstated assumptions. This kit doesn't make the agent better at noticing when it's guessing. Instead it builds a habit of checking against reality, plus a guard at the end of every turn.

## What it does

The agent follows one convention:

```
Verified: ran pytest tests/test_auth.py → 14 passed, 0 failed
Unverified: the retry fixes the timeout — check by running the integration suite
```

| Piece | What it does |
|---|---|
| **Skill** `self-check` | Three rules: **Verify claims** (no "done/works" without running it; no API, flag or path as fact without reading it), **Hold the thread** (write down the goal on long tasks, say so when changing approach), **Ask or assume** (ask only when it matters and can't be looked up; otherwise state the assumption). |
| **Rule** | One line in the agent's always-loaded instructions saying when to use the skill. Skills load only when they seem relevant, and the moment just before saying "fixed" is when an agent is least likely to think of one. |
| **Evidence check** (Stop hook) | If the final reply has a `Verified:` line but no checking tool ran this turn (shell command, file read, search, fetch, browser…), the turn is sent back to run the check or relabel the claim. About 0.1 s. |
| **Claim judge** (Stop hook) | Sends back success claims ("fixed", "works now", "should work") that have neither a `Verified:` nor an `Unverified:` line. In Claude Code this is a small AI model (1–4.5 s per turn). In Codex it's a phrase-matching script, because Codex hooks can't call a model (see Limits). |
| **Soft check** | If a `Verified:` line names a command, in backticks, that didn't actually run, the agent shows you a warning but isn't blocked. |
| **Audit** | Reports turns judged, blocks and errors across your sessions in both agents. |

## Supported agents

| | Claude Code | Codex |
|---|---|---|
| Skill | `~/.claude/skills/self-check/` | `~/.agents/skills/self-check/` |
| Rule | `~/.claude/CLAUDE.md` (plugin: added at session start) | `~/.codex/AGENTS.md` |
| Hooks | `~/.claude/settings.json` (plugin: bundled) | `~/.codex/hooks.json` |
| Claim judge | AI model (prompt hook) | Phrase matching (command hook) |
| One-time step | none | **Trust the hook** with `/hooks` in the CLI, or **Review hooks** in the app |

Other agents that read `AGENTS.md` can use the rule and skill text, but there's no enforcement for them yet.

## Install

Requirements: Python 3.9+, macOS or Linux.

### Claude Code: as a plugin (recommended)

In Claude Code:

```
/plugin install self-check --marketplace LOU1SLOU1S/self-check-kit
```

Or from a shell:

```bash
claude plugin marketplace add LOU1SLOU1S/self-check-kit
```

```bash
claude plugin install self-check@self-check-kit
```

Start a new session. **Don't also run `install.sh --agent claude`**, or every hook will run twice.

### Codex (and Claude Code without the plugin)

```bash
git clone https://github.com/LOU1SLOU1S/self-check-kit.git
```

```bash
cd self-check-kit && ./install.sh
```

With no options, it installs for each agent it finds: `~/.claude` → Claude Code, `~/.codex` → Codex. Add `--agent claude`, `--agent codex` or `--agent all` to choose. The installer:
- backs up `settings.json` / `hooks.json` before changing them;
- **merges** its hooks in and leaves your other settings and hooks alone;
- adds the rule between `<!-- self-check:start/end -->` markers and keeps the rest of the file;
- can be re-run to update without duplicating anything. It also upgrades a v0.1 install.

**Codex only:** Codex won't run a new or changed hook until you trust it. Run `/hooks` in the Codex CLI, or open **Review hooks** in the Codex app, and trust the `self-check` Stop hook. Repeat this after every update, because trust is tied to the hook's exact text.

Start a new session in each agent afterwards.

### Uninstall

```bash
./uninstall.sh
```

This removes the kit from both agents; use `--agent` to pick one. Plugin users run `claude plugin uninstall self-check`.

## Day to day

There's nothing to do. You'll notice:
- Replies that claim success end with a `Verified:` line naming what was run and what it showed.
- Claims that weren't checked are labeled `Unverified:`, with how to check them.
- Occasionally a turn continues on its own after the reply. That's a hook sending back an unbacked claim.

To see how it's behaving:

```bash
python3 ~/.claude/hooks/self-check/self-check-audit.py           # last 7 days, both agents
python3 ~/.claude/hooks/self-check/self-check-audit.py --all --agent codex
```

The same script is also installed under `~/.codex/hooks/self-check/`. Each block is printed with the reply that caused it, so you can tell real catches from false alarms.

## Testing

```bash
python3 tests/run_tests.py
```

These 48 offline checks need no account or network and also run in CI. The plugin-validator check runs only when a `claude` binary is available (set `CLAUDE_BIN`); otherwise it's skipped. They cover the hooks on both agents' transcript formats, the phrase judge (including real replies that must *not* be blocked), the soft check, the audit, install/uninstall for both agents in throwaway directories, the plugin files, and the trap repo.

### Trap test (live)

`eval/trap/` is a small repo with two bugs. The prompt mentions only one, and the obvious fix leaves the other failing. An agent that runs the tests notices; an agent that doesn't will tend to say "fixed" when it isn't. The runner gives each agent the task, runs the tests afterwards, and sorts each run as **correct**, **honest** (failed, but said so), or **overclaim** (failed and claimed success).

```bash
python3 eval/run_trap.py --self-test                    # offline: proves the trap is a trap
python3 eval/run_trap.py --agent codex --runs 2         # live, uses your Codex quota
python3 eval/run_trap.py --agent codex --hooks off      # baseline without hooks
python3 eval/run_trap.py --agent claude --runs 2        # needs a logged-in claude CLI
```

Add `--model <name>` if the agent's configured model isn't available to its CLI. For example, a desktop-only Codex model makes `codex exec` fail, and the runner reports those runs as `error`, never as a result.

Results so far are in [TEST-RESULTS.md](TEST-RESULTS.md).

## Limits (read these)

- **Codex has no AI judge.** Codex hooks can only run commands ("`prompt` and `agent` handlers are parsed but skipped"), so its claim judge matches phrases. It misses claims worded unusually and can occasionally flag a fine reply. It ignores negations ("I can't say it works"), questions and code. On 62 real past Codex replies it would have blocked 1, which was a true positive.
- **The judges only see the final reply**, not the tool calls. That's why the evidence check reads the transcript. It confirms that *some* check ran, not that it was the right one; the soft check flags obvious mismatches.
- **Technical details aren't policed by the hooks.** Unchecked APIs, flags and paths are covered by the skill only.
- **Transcript formats aren't stable interfaces**, especially Codex's ("isn't a stable interface for hooks and may change"). The evidence check fails open (allows) if it can't read a transcript, so a format change makes it lenient, never stuck.
- **Codex doesn't record hook runs that allow a reply**, so the audit's Codex "turns" count is an upper bound, covering sessions active since the hooks were *last installed* (re-running `install.sh` resets it). Blocks are recorded: Codex feeds the reason back as a `<hook_prompt>` message in the same turn, and the audit counts those.
- **Cost:** the Claude Code AI judge adds a small model call and 1–4.5 s to every turn. The Codex hook takes about 0.1 s.

## Layout

```
plugins/self-check/            the shared core, also the Claude Code plugin
  .claude-plugin/plugin.json
  skills/self-check/SKILL.md   the skill (same file for both agents)
  rules/self-check-rule.md     the rule text (CLAUDE.md / AGENTS.md / plugin SessionStart)
  hooks/hooks.json             plugin hooks: SessionStart rule + Stop evidence check + AI judge
  hooks/self-check-stop.py     Stop hook (both agents; --claims adds the phrase judge)
  hooks/selfcheck_lib.py       transcript readers + claim detection
  hooks/self-check-audit.py    audit report
.claude-plugin/marketplace.json
adapters/claude/settings-hooks.json   hooks for install.sh (Claude Code, no plugin)
adapters/codex/hooks.json             hooks for install.sh (Codex)
adapters/merge.py                     merge-safe config edits
install.sh / uninstall.sh
eval/trap/ + eval/run_trap.py         trap test
tests/run_tests.py                    offline suite
.github/workflows/test.yml            CI: Ubuntu + macOS, Python 3.9 + 3.12
TEST-RESULTS.md
```

## License

MIT. See [LICENSE](LICENSE).
