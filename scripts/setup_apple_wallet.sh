#!/usr/bin/env bash
# Підготовка сертифікатів Apple Wallet.
# Потрібен акаунт Apple Developer + Pass Type ID.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs

echo "1) Завантажую Apple WWDR G4…"
curl -fsSL -A "Mozilla/5.0" \
  -o certs/AppleWWDRCAG4.cer \
  "https://www.apple.com/certificateauthority/AppleWWDRCAG4.cer"
openssl x509 -inform DER -in certs/AppleWWDRCAG4.cer -out certs/wwdr.pem
echo "   OK → certs/wwdr.pem"

if [[ "${1:-}" == *.p12 || "${1:-}" == *.pfx ]]; then
  P12="$1"
  echo "2) Конвертую $P12 → PEM…"
  read -rsp "Пароль від .p12: " P12PASS
  echo
  openssl pkcs12 -in "$P12" -clcerts -nokeys -out certs/pass_cert.pem -passin pass:"$P12PASS"
  openssl pkcs12 -in "$P12" -nocerts -nodes -out certs/pass_key.pem -passin pass:"$P12PASS"
  echo "   OK → certs/pass_cert.pem, certs/pass_key.pem"
else
  echo "2) Поклади Pass Type ID сертифікат:"
  echo "   - експортуй .p12 з Keychain (Certificates → Pass Type ID)"
  echo "   - або запусти: ./scripts/setup_apple_wallet.sh path/to/Certificates.p12"
fi

echo
echo "У .env додай:"
echo "  APPLE_PASS_TYPE_ID=pass.com.your.craftcoffee"
echo "  APPLE_TEAM_ID=YOURTEAMID"
echo "  APPLE_PASS_CERT=certs/pass_cert.pem"
echo "  APPLE_PASS_KEY=certs/pass_key.pem"
echo "  APPLE_WWDR_CERT=certs/wwdr.pem"
