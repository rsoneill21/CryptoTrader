#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/slack_new_project.sh cryptotrader
# Creates: #triad-cryptotrader
# Invites: rsoneill21
#
# Expects: SLACK_BOT_TOKEN in environment (load via .env)

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <project-name>"
  echo "Example: $0 cryptotrader"
  exit 1
fi

PROJECT_RAW="$1"
PROJECT="$(echo "$PROJECT_RAW" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')"
CHANNEL_NAME="triad-${PROJECT}"

if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
  echo "SLACK_BOT_TOKEN is not set."
  echo "Load it first, e.g.:"
  echo "  set -a; source .env; set +a"
  exit 1
fi

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; exit 1; }; }
need_cmd curl
need_cmd jq

api_get() {
  local url="$1"
  curl -sS "$url" -H "Authorization: Bearer $SLACK_BOT_TOKEN"
}

api_post() {
  local method="$1"
  local data="$2"
  curl -sS -X POST "https://slack.com/api/${method}" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H "Content-Type: application/json; charset=utf-8" \
    --data "$data"
}

echo "Resolving Slack user ID for: rsoneill21"
USER_ID=$(
  api_get "https://slack.com/api/users.list" \
  | jq -r '.members[] | select(.name=="rsoneill21") | .id' \
  | head -n 1
)

if [[ -z "${USER_ID:-}" || "$USER_ID" == "null" ]]; then
  echo "Could not find Slack user with handle/name 'rsoneill21'."
  echo "Check your Slack handle, or ensure bot has users:read + app reinstalled."
  exit 1
fi
echo "User ID: $USER_ID"

echo "Creating channel: #$CHANNEL_NAME"
RESP=$(api_post "conversations.create" "{\"name\":\"$CHANNEL_NAME\",\"is_private\":false}")

OK=$(echo "$RESP" | jq -r '.ok')
if [[ "$OK" == "true" ]]; then
  CHANNEL_ID=$(echo "$RESP" | jq -r '.channel.id')
  echo "✅ Created: $CHANNEL_NAME ($CHANNEL_ID)"
else
  ERR=$(echo "$RESP" | jq -r '.error // empty')
  if [[ "$ERR" == "name_taken" ]]; then
    echo "ℹ️ Channel already exists, resolving ID..."
    LIST=$(api_get "https://slack.com/api/conversations.list?exclude_archived=true&limit=1000")
    CHANNEL_ID=$(echo "$LIST" | jq -r --arg n "$CHANNEL_NAME" '.channels[] | select(.name==$n) | .id' | head -n 1)
    if [[ -z "${CHANNEL_ID:-}" || "$CHANNEL_ID" == "null" ]]; then
      echo "Could not resolve existing channel ID. Ensure bot has channels:read + app reinstalled."
      exit 1
    fi
    echo "✅ Found: $CHANNEL_NAME ($CHANNEL_ID)"
  else
    echo "❌ Failed to create channel: ${ERR:-unknown}"
    echo "$RESP" | jq .
    exit 1
  fi
fi

echo "Inviting rsoneill21 to #$CHANNEL_NAME"
INV=$(api_post "conversations.invite" "{\"channel\":\"$CHANNEL_ID\",\"users\":\"$USER_ID\"}")
INV_OK=$(echo "$INV" | jq -r '.ok')
if [[ "$INV_OK" == "true" ]]; then
  echo "✅ Invited."
else
  INV_ERR=$(echo "$INV" | jq -r '.error // empty')
  if [[ "$INV_ERR" == "already_in_channel" ]]; then
    echo "ℹ️ Already in channel."
  else
    echo "⚠️ Invite error: ${INV_ERR:-unknown}"
    echo "$INV" | jq .
  fi
fi

# Optional: post a pinned “how to use Triad here” message
echo "Posting channel kickoff message..."
MSG=$(api_post "chat.postMessage" "$(jq -nc --arg ch "$CHANNEL_ID" --arg txt \
"Triad kickoff for *$PROJECT* ✅

Use *threads* to keep things clean:
- 🧠 *Plan* thread (Claude): PLAN.md updates, decisions, edge cases
- 🛠️ *Build* thread (Codex): status, test results, branch/PR link
- 🔍 *Review* thread (Gemini): punch list (P0/P1/P2), security notes

Golden rule: *only one agent edits code at a time.*" \
'{channel:$ch, text:$txt}')")

MSG_OK=$(echo "$MSG" | jq -r '.ok')
if [[ "$MSG_OK" == "true" ]]; then
  echo "✅ Posted kickoff message."
else
  echo "⚠️ Could not post kickoff message."
  echo "$MSG" | jq .
fi

echo "Done. Channel: #$CHANNEL_NAME"
