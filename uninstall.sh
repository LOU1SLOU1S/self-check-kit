#!/usr/bin/env bash
# Remove self-check from Claude Code and/or Codex. Leaves everything else alone.
#   ./uninstall.sh [--agent claude|codex|all]   (default: all)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${SELF_CHECK_CLAUDE_HOME:-$HOME/.claude}"
CODEX_DIR="${SELF_CHECK_CODEX_HOME:-${CODEX_HOME:-$HOME/.codex}}"
AGENTS_HOME="${SELF_CHECK_AGENTS_HOME:-$HOME/.agents}"

AGENT="all"
case "${1:-}" in
  --agent) AGENT="${2:-all}" ;;
  --agent=*) AGENT="${1#*=}" ;;
esac
[ "$AGENT" = "all" ] && AGENT="claude,codex"

IFS=',' read -r -a AGENTS <<< "$AGENT"
for a in "${AGENTS[@]}"; do
  case "$a" in
    claude)
      rm -rf "$CLAUDE_HOME/skills/self-check" "$CLAUDE_HOME/hooks/self-check"
      rm -f "$CLAUDE_HOME/hooks/self-check-stop.py" "$CLAUDE_HOME/hooks/self-check-audit.py"
      python3 "$SRC/adapters/merge.py" uninstall claude "$CLAUDE_HOME" "$CLAUDE_HOME/settings.json" "$CLAUDE_HOME/CLAUDE.md"
      echo "Removed self-check from Claude Code ($CLAUDE_HOME)." ;;
    codex)
      rm -rf "$AGENTS_HOME/skills/self-check" "$CODEX_DIR/hooks/self-check"
      python3 "$SRC/adapters/merge.py" uninstall codex "$CODEX_DIR" "$CODEX_DIR/hooks.json" "$CODEX_DIR/AGENTS.md"
      echo "Removed self-check from Codex ($CODEX_DIR)." ;;
    *) echo "Unknown agent: $a"; exit 1 ;;
  esac
done
echo "Start a new session in each agent for it to take effect."
