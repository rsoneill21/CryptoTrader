#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this script so outputs land in the repo root no matter where it runs from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Pull recent Slack messages into triad_inbox.md
# Usage:
#   ./scripts/slack_pull.sh
#
# Expects:
#   SLACK_BOT_TOKEN
#   TRIAD_SLACK_CHANNEL   (e.g., triad-cryptotrader)
#
# Output:
#   triad_inbox.md        (latest messages)
#   triad_handoff.json    (optional: parsed HANDOFF line)

# Auto-load .env if present
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

: "${SLACK_BOT_TOKEN:?Missing SLACK_BOT_TOKEN}"
: "${TRIAD_SLACK_CHANNEL:?Missing TRIAD_SLACK_CHANNEL}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }
need_cmd curl
need_cmd python3

# Resolve channel ID (cache it locally so we don't list channels every time)
CACHE_DIR="${PROJECT_ROOT}/.triad"
CACHE_FILE="${CACHE_DIR}/channel_id_${TRIAD_SLACK_CHANNEL}.txt"
mkdir -p "$CACHE_DIR"

get_channel_id() {
  if [[ -f "$CACHE_FILE" ]]; then
    cat "$CACHE_FILE"
    return
  fi

  resp="$(curl --fail -sS "https://slack.com/api/conversations.list?exclude_archived=true&limit=1000" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN")"

  echo "$resp" | python3 -c "
import json, sys
name = sys.argv[1]
cache = sys.argv[2]
data = json.load(sys.stdin)
if not data.get('ok'):
  raise SystemExit('Slack error: ' + str(data.get('error')))
cid = None
for ch in data.get('channels', []):
  if ch.get('name') == name:
    cid = ch.get('id')
    break
if not cid:
  raise SystemExit('Channel not found: ' + name)
open(cache, 'w').write(cid)
print(cid)
" "$TRIAD_SLACK_CHANNEL" "$CACHE_FILE"
}

CHANNEL_ID="$(get_channel_id)"

# Pull last N messages (tweak to taste)
LIMIT="${TRIAD_PULL_LIMIT:-60}"

history="$(curl --fail -sS "https://slack.com/api/conversations.history?channel=${CHANNEL_ID}&limit=${LIMIT}" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN")"

# Write triad_inbox.md + triad_handoff.json
echo "$history" | python3 -c "
import json, sys, datetime, re, os
channel_name = sys.argv[1]
out_dir = sys.argv[2]
data = json.load(sys.stdin)
if not data.get('ok'):
  raise SystemExit('Slack error: ' + str(data.get('error')))

msgs = data.get('messages', [])

# Slack returns newest-first; reverse for readability
msgs = list(reversed(msgs))

def ts_to_str(ts):
  try:
    dt = datetime.datetime.fromtimestamp(float(ts))
    return dt.strftime('%Y-%m-%d %H:%M:%S')
  except Exception:
    return ts

# Basic rendering: keep it readable for agents
lines = []
lines.append('# triad_inbox.md — Slack Pull')
lines.append('- Channel: #' + channel_name)
lines.append('- Pulled: ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
lines.append('')
lines.append('## Recent messages')
lines.append('')

handoff = {
  'next': None,
  'raw': None,
  'ts': None,
}

handoff_re = re.compile(r'^\s*HANDOFF:\s*(CLAUDE|CODEX|GEMINI)\s*$', re.IGNORECASE)

for m in msgs:
  text = (m.get('text') or '').strip()
  if not text:
    continue

  # Capture latest HANDOFF line (if present)
  for line in text.splitlines():
    match = handoff_re.match(line.strip())
    if match:
      handoff['next'] = match.group(1).upper()
      handoff['raw'] = line.strip()
      handoff['ts'] = m.get('ts')

  user = m.get('user') or m.get('username') or 'unknown'
  ts = ts_to_str(m.get('ts', ''))
  lines.append('### ' + ts + ' — ' + user)
  lines.append(text)
  lines.append('')

# Write the gathered inbox once after iterating.
open(os.path.join(out_dir, 'triad_inbox.md'), 'w', encoding='utf-8').write('\n'.join(lines))

# Also emit handoff JSON (useful for tooling)
if handoff['next']:
  out = {
    'channel': channel_name,
    'next': handoff['next'],
    'ts': handoff['ts'],
    'note': 'Derived from latest HANDOFF: line in channel history',
  }
  open(os.path.join(out_dir, 'triad_handoff.json'), 'w', encoding='utf-8').write(json.dumps(out, indent=2))
else:
  # Write an empty file so scripts do not fail
  open(os.path.join(out_dir, 'triad_handoff.json'), 'w', encoding='utf-8').write(json.dumps({'channel': channel_name, 'next': None}, indent=2))

print('Wrote triad_inbox.md and triad_handoff.json')
" "$TRIAD_SLACK_CHANNEL" "$PROJECT_ROOT"
