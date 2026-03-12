#!/usr/bin/env bash
set -euo pipefail

# slack_post.sh
# Usage:
#   ./slack_post.sh CODEX "message"
#   ./slack_post.sh CLAUDE "message"
#   ./slack_post.sh GEMINI "message"
#
# Requires in environment or .env:
#   SLACK_BOT_TOKEN
#   TRIAD_SLACK_CHANNEL

ROLE="${1:-}"
shift || true
MESSAGE="${*:-}"

# Auto-load .env if present (project root)
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "$ROLE" || -z "$MESSAGE" ]]; then
  echo "Usage: $0 <CLAUDE|CODEX|GEMINI> \"message\""
  exit 1
fi

if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
  echo "ERROR: SLACK_BOT_TOKEN not set. Put it in .env and re-run."
  exit 1
fi

if [[ -z "${TRIAD_SLACK_CHANNEL:-}" ]]; then
  echo "ERROR: TRIAD_SLACK_CHANNEL not set (e.g., triad-cryptotrader). Put it in .env and re-run."
  exit 1
fi

PREFIX=""
case "${ROLE^^}" in
  CLAUDE) PREFIX="🧠 [CLAUDE]" ;;
  CODEX)  PREFIX="🛠 [CODEX]" ;;
  GEMINI) PREFIX="🔍 [GEMINI]" ;;
  *) echo "ERROR: Unknown role '$ROLE' (use CLAUDE, CODEX, or GEMINI)"; exit 1 ;;
esac

# Build JSON payload safely using python (no heredocs, no argv assumptions)
PAYLOAD="$(python3 -c 'import json,os,sys
channel=os.environ["TRIAD_SLACK_CHANNEL"]
prefix=sys.argv[1]
msg=sys.argv[2]
print(json.dumps({"channel":channel,"text":prefix + "\n" + msg}))
' "$PREFIX" "$MESSAGE")"

# Post to Slack
RESP="$(curl -sS -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer ${SLACK_BOT_TOKEN}" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data "$PAYLOAD" || true)"

if [[ -z "$RESP" ]]; then
  echo "ERROR: Empty response from Slack (likely DNS/network/proxy)."
  echo "Try: curl -sS https://slack.com/api/api.test ; echo"
  exit 1
fi

# Parse Slack response
python3 -c 'import json,sys
resp_text=sys.stdin.read()
try:
  resp=json.loads(resp_text)
except Exception:
  print("ERROR: Slack response not JSON. Raw:")
  print(resp_text[:1000])
  raise
if not resp.get("ok"):
  print("Slack error:", resp.get("error"))
  sys.exit(1)
print("Posted ✅")
' <<< "$RESP"
