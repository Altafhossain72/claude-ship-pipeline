#!/usr/bin/env bash
# Installs the /ship pipeline for Claude Code.
#   ./install.sh          -> user level (~/.claude), works in every repo
#   ./install.sh project  -> current repo only (./.claude)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
if [ "${1:-user}" = "project" ]; then DEST="./.claude"; else DEST="$HOME/.claude"; fi
mkdir -p "$DEST/agents" "$DEST/skills/ship"
for f in "$SRC"/agents/*.md; do
  t="$DEST/agents/$(basename "$f")"
  [ -e "$t" ] && cp "$t" "$t.bak" && echo "backed up $t -> $t.bak"
  cp "$f" "$t"
done
[ -e "$DEST/skills/ship/SKILL.md" ] && cp "$DEST/skills/ship/SKILL.md" "$DEST/skills/ship/SKILL.md.bak"
cp "$SRC/skills/ship/SKILL.md" "$DEST/skills/ship/SKILL.md"
echo "Installed to $DEST. Restart Claude Code, then run: /ship <feature request>"
