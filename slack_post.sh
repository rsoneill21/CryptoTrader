#!/usr/bin/env bash
set -euo pipefail

# triad_slack_post.sh
# Usage:
#   ./scripts/triad_slack_post.sh CODEX "message text"
#   ./scripts/triad_slack_post.sh CLAUDE "message text"
#   ./scripts/triad_slack_post.sh GEMINI "message text"
#
# Requires env:
#   SLACK_BOT_TOKEN
#   TRIAD_SLACK_CHANNEL  (e.g., triad-cryptotrader)

ROLE="${1:-}"
MESSAGE="${2:-}"

if [[ -z "$ROLE" || -z "$MESSAGE" ]]; then
  echo "Usage: $0 <CLAUDE|CODEX|GEMINI> \"message\""
  exit 1
fi

if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
  echo "SLACK_BOT_TOKEN is not set. Load .env first:"
  echo "  set -a; source .env; set +a"
  exit 1
fi

if [[ -z "${TRIAD_SLACK_CHANNEL:-}" ]]; then
  echo "TRIAD_SLACK_CHANNEL is not set (e.g., triad-cryptotrader)."
  echo "Add it to your project's .env:"
  echo "  TRIAD_SLACK_CHANNEL=triad-cryptotrader"
  exit 1
fi

# Role prefix
PREFIX="[TRIAD]"
case "${ROLE^^}" in
  CLAUDE) PREFIX="🧠 [CLAUDE]" ;;
  CODEX)  PREFIX="🛠️ [CODEX]" ;;
  GEMINI) PREFIX="🔍 [GEMINI]" ;;
  *) echo "Unknown role: $ROLE (use CLAUDE, CODEX, or GEMINI)"; exit 1 ;;
esac

# Post
RESP="$(curl -sS -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data "$(python3 - <<'PY'
import json, os, sys
channel = os.environ["TRIAD_SLACK_CHANNEL"]
prefix = sys.argv[1]
message = sys.argv[2]
print(json.dumps({"channel": channel, "text": f"{prefix}\n{message}"}))
PY
"$PREFIX" "$MESSAGE")" )"

# Debug: if empty, curl didn't return anything usable
if [[ -z "$RESP" ]]; then
  echo "ERROR: Empty response from Slack. This is usually DNS/network/proxy."
  echo "Try: curl -sS https://slack.com/api/api.test"
  exit 1
fi

python3 - <<'PY'
import json, sys
resp_text = sys.stdin.read()
try:
  resp = json.loads(resp_text)
except Exception as e:
  print("ERROR: Slack response was not JSON.")
  print("Raw response:")
  print(resp_text[:1000])
  raise

if not resp.get("ok"):
  print("Slack error:", resp.get("error"))
  sys.exit(1)

print("Posted ✅")
PY <<< "$RESP"

