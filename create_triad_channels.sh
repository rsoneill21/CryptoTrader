CHANNELS=(
  triad-control
  triad-claude
  triad-codex
  triad-gemini
  triad-alerts
  triad-cryptotrader-control
  triad-cryptotrader-claude
  triad-cryptotrader-codex
  triad-cryptotrader-gemini
  triad-cryptotrader-strategy
)

for c in "${CHANNELS[@]}"; do
  echo "Creating: $c"
  curl -s -X POST "https://slack.com/api/conversations.create" \
    -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
    -H "Content-Type: application/json; charset=utf-8" \
    --data "{\"name\":\"$c\",\"is_private\":false}"
  echo
done
