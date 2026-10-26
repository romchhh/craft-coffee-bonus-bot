#!/usr/bin/env bash
# Копіює JSON-ключ Google Wallet на прод (не в git).
# Використання:
#   DEPLOY_HOST=user@craftcoffee.telebots.site DEPLOY_DIR=/path/to/CraftCoffeBot ./scripts/deploy_google_wallet_key.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$(ls "$ROOT"/telebots-e-commerce-*.json 2>/dev/null | head -1)"
HOST="${DEPLOY_HOST:-}"
REMOTE_DIR="${DEPLOY_DIR:-}"

if [[ -z "$KEY" || ! -f "$KEY" ]]; then
  echo "Немає telebots-e-commerce-*.json у $ROOT"
  exit 1
fi
if [[ -z "$HOST" || -z "$REMOTE_DIR" ]]; then
  echo "Задай DEPLOY_HOST і DEPLOY_DIR, наприклад:"
  echo "  DEPLOY_HOST=root@your-server DEPLOY_DIR=/opt/craft-coffee-bonus-bot ./scripts/deploy_google_wallet_key.sh"
  exit 1
fi

BASENAME="$(basename "$KEY")"
scp "$KEY" "$HOST:$REMOTE_DIR/$BASENAME"
echo "OK: $HOST:$REMOTE_DIR/$BASENAME"
echo "На сервері в .env має бути:"
echo "  GOOGLE_APPLICATION_CREDENTIALS=$BASENAME"
echo "  GOOGLE_WALLET_ISSUER_ID=3388000000023224873"
echo "  GOOGLE_WALLET_CLASS_SUFFIX=craft_coffee_loyalty"
echo "  WEBAPP_URL=https://craftcoffee.telebots.site"
echo "Потім: ./start_bot.sh restart"
