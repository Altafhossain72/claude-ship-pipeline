#!/usr/bin/env bash
# Installs the /ship pipeline for Claude Code into ~/.claude (all repos).
# Existing files are kept as *.bak. Needs python3 and git >= 2.25.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude"
mkdir -p "$DEST/agents" "$DEST/skills/ship" "$DEST/hooks"

install_file() {  # src dest
  if [ -e "$2" ] && ! cmp -s "$1" "$2"; then cp "$2" "$2.bak"; echo "backed up $2 -> $2.bak"; fi
  cp "$1" "$2"
}
for f in "$SRC"/agents/*.md; do install_file "$f" "$DEST/agents/$(basename "$f")"; done
for f in "$SRC"/hooks/*.py; do install_file "$f" "$DEST/hooks/$(basename "$f")"; done
install_file "$SRC/skills/ship/SKILL.md" "$DEST/skills/ship/SKILL.md"
[ -e "$DEST/ship.json" ] || cp "$SRC/ship.json.example" "$DEST/ship.json"

echo "Installed to $DEST. Checking the hooks..."
"$SRC/tests/hook-tests.sh" "$DEST/hooks"
echo "Restart Claude Code, then run: /ship <feature request>"
