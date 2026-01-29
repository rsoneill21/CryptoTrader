#!/usr/bin/env bash
set -euo pipefail

# Triad handoff coordination
# Usage:
#   ./scripts/triad_handoff.sh                    # Check who's next
#   ./scripts/triad_handoff.sh CODEX              # Hand off to CODEX
#   ./scripts/triad_handoff.sh CLAUDE "message"   # Hand off with context
#
# Valid agents: CLAUDE, CODEX, GEMINI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HANDOFF_FILE="${PROJECT_ROOT}/triad_handoff.json"

# Initialize file if missing
if [[ ! -f "$HANDOFF_FILE" ]]; then
  echo '{"next": null}' > "$HANDOFF_FILE"
fi

# No args = check who's next
if [[ $# -eq 0 ]]; then
  if command -v jq >/dev/null 2>&1; then
    jq -r '.next // "none"' "$HANDOFF_FILE"
  else
    python3 -c "import json; print(json.load(open('$HANDOFF_FILE')).get('next') or 'none')"
  fi
  exit 0
fi

NEXT="${1^^}"  # uppercase
MESSAGE="${2:-}"

# Validate agent name
if [[ ! "$NEXT" =~ ^(CLAUDE|CODEX|GEMINI)$ ]]; then
  echo "ERROR: Invalid agent '$NEXT'. Use CLAUDE, CODEX, or GEMINI." >&2
  exit 1
fi

# Write handoff
python3 -c "
import json, datetime
data = {
    'next': '$NEXT',
    'message': '''$MESSAGE''' if '''$MESSAGE''' else None,
    'ts': datetime.datetime.now().isoformat(),
}
# Remove None values
data = {k: v for k, v in data.items() if v is not None}
open('$HANDOFF_FILE', 'w').write(json.dumps(data, indent=2))
print('Handoff set: $NEXT')
"
