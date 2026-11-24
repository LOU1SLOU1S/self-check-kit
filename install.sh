#!/usr/bin/env bash
# Install self-check at user level for Claude Code and/or Codex.
#
#   ./install.sh                  # every agent found on this machine
#   ./install.sh --agent claude   # Claude Code only (~/.claude)
#   ./install.sh --agent codex    # Codex only (~/.codex + ~/.agents/skills)
#
# Safe to re-run: it replaces its own pieces and leaves everything else alone.
# Claude Code users can install the plugin instead (see README); don't do both.
# Overrides (used by the tests): SELF_CHECK_CLAUDE_HOME, SELF_CHECK_CODEX_HOME, SELF_CHECK_AGENTS_HOME.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
CORE="$SRC/plugins/self-check"
CLAUDE_HOME="${SELF_CHECK_CLAUDE_HOME:-$HOME/.claude}"
CODEX_DIR="${SELF_CHECK_CODEX_HOME:-${CODEX_HOME:-$HOME/.codex}}"
AGENTS_HOME="${SELF_CHECK_AGENTS_HOME:-$HOME/.agents}"

AGENT="auto"
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) AGENT="${2:-}"; shift 2 ;;
    --agent=*) AGENT="${1#*=}"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

command -v python3 >/dev/null || { echo "python3 is required (the hooks are Python 3.9+)."; exit 1; }

if [ "$AGENT" = "auto" ]; then
  AGENT=""
  [ -d "$CLAUDE_HOME" ] && AGENT="claude"
  [ -d "$CODEX_DIR" ] && AGENT="${AGENT:+$AGENT,}codex"
  [ -n "$AGENT" ] || { echo "Found neither $CLAUDE_HOME nor $CODEX_DIR. Use --agent claude|codex."; exit 1; }
fi
[ "$AGENT" = "all" ] && AGENT="claude,codex"

copy_scripts() {  # $1 = destination dir
  mkdir -p "$1"
  cp "$CORE/hooks/self-check-stop.py" "$CORE/hooks/selfcheck_lib.py" "$CORE/hooks/self-check-audit.py" "$1/"
  chmod +x "$1/self-check-stop.py" "$1/self-check-audit.py"
}

merge() {  # $1 = agent, $2 = home dir, $3 = hooks file, $4 = hooks template, $5 = rules file
  python3 "$SRC/adapters/merge.py" install "$1" "$2" "$3" "$4" "$5" "$CORE/rules/self-check-rule.md"
}

IFS=',' read -r -a AGENTS <<< "$AGENT"
for a in "${AGENTS[@]}"; do
  case "$a" in
    claude)
      echo "== Claude Code ($CLAUDE_HOME)"
      mkdir -p "$CLAUDE_HOME/skills/self-check"
      cp "$CORE/skills/self-check/SKILL.md" "$CLAUDE_HOME/skills/self-check/SKILL.md"
      rm -f "$CLAUDE_HOME/hooks/self-check-stop.py" "$CLAUDE_HOME/hooks/self-check-audit.py"  # v0.1 locations
      copy_scripts "$CLAUDE_HOME/hooks/self-check"
      echo "✓ skill  → $CLAUDE_HOME/skills/self-check/SKILL.md"
      echo "✓ hooks  → $CLAUDE_HOME/hooks/self-check/"
      merge claude "$CLAUDE_HOME" "$CLAUDE_HOME/settings.json" "$SRC/adapters/claude/settings-hooks.json" "$CLAUDE_HOME/CLAUDE.md"
      echo "  Audit: python3 \"$CLAUDE_HOME/hooks/self-check/self-check-audit.py\""
      ;;
    codex)
      echo "== Codex ($CODEX_DIR, skills in $AGENTS_HOME/skills)"
      mkdir -p "$AGENTS_HOME/skills/self-check"
      cp "$CORE/skills/self-check/SKILL.md" "$AGENTS_HOME/skills/self-check/SKILL.md"
      copy_scripts "$CODEX_DIR/hooks/self-check"
      echo "✓ skill  → $AGENTS_HOME/skills/self-check/SKILL.md"
      echo "✓ hooks  → $CODEX_DIR/hooks/self-check/"
      merge codex "$CODEX_DIR" "$CODEX_DIR/hooks.json" "$SRC/adapters/codex/hooks.json" "$CODEX_DIR/AGENTS.md"
      echo "  ⚠ Codex skips new or changed hooks until you trust them:"
      echo "    run /hooks in the Codex CLI, or use \"Review hooks\" in the Codex app."
      ;;
    *) echo "Unknown agent: $a (use claude, codex or all)"; exit 1 ;;
  esac
done

echo
echo "Done. Start a NEW session in each agent to pick everything up."
