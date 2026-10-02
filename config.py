from os import getenv
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "database" / "data.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

token = (getenv("TOKEN") or "").strip()
BOT_USERNAME = (getenv("BOT_USERNAME") or "CraftCoffee_Kyiv_Bot").strip().lstrip("@")

def _parse_administrators() -> list[int]:
    raw = (getenv("ADMINISTRATORS") or "").strip()
    if not raw:
        return []
    inner = raw[1:-1] if raw.startswith("[") and raw.endswith("]") else raw
    return [int(x.strip()) for x in inner.split(",") if x.strip()]


administrators = _parse_administrators()

POSTER_TOKEN = getenv("POSTER_TOKEN", "")
POSTER_CLIENT_GROUP_ID = int(getenv("POSTER_CLIENT_GROUP_ID", "1"))
POSTER_BONUS_MULT = int(getenv("POSTER_BONUS_MULT", "100"))  # 100 = копійки
WELCOME_BONUS_UAH = float(getenv("WELCOME_BONUS_UAH", "50"))

WEBAPP_URL = (getenv("WEBAPP_URL") or "").rstrip("/")
WEBAPP_HOST = getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(getenv("WEBAPP_PORT", "8080"))
WEBAPP_DEV = getenv("WEBAPP_DEV", "0") == "1"

# Apple Wallet (.pkpass) — потрібен Apple Developer Pass Type ID
APPLE_PASS_TYPE_ID = getenv("APPLE_PASS_TYPE_ID", "")
APPLE_TEAM_ID = getenv("APPLE_TEAM_ID", "")
APPLE_ORG_NAME = getenv("APPLE_ORG_NAME", "Craft Coffee")
APPLE_PASS_CERT = getenv("APPLE_PASS_CERT", "certs/pass_cert.pem")
APPLE_PASS_KEY = getenv("APPLE_PASS_KEY", "certs/pass_key.pem")
APPLE_PASS_KEY_PASSWORD = getenv("APPLE_PASS_KEY_PASSWORD", "")
APPLE_WWDR_CERT = getenv("APPLE_WWDR_CERT", "certs/wwdr.pem")
APPLE_WALLET_SECRET = getenv("APPLE_WALLET_SECRET") or (token or "craft-wallet-secret")

# Poster webhooks (application secret з кабінету розробника; опційно)
POSTER_APP_SECRET = getenv("POSTER_APP_SECRET", "")
CASHBACK_PERCENT = float(getenv("CASHBACK_PERCENT", "5"))

# Google Maps (мініап — плашка «використай бонуси»). Якщо порожньо — з першої точки Poster.
MAPS_URL = (getenv("MAPS_URL") or "").strip()

# Фонова перевірка закритих чеків (якщо webhook пропустив)
LOYALTY_CRON_ENABLED = getenv("LOYALTY_CRON_ENABLED", "1") == "1"
LOYALTY_CRON_INTERVAL_SEC = int(getenv("LOYALTY_CRON_INTERVAL_SEC", "60"))
LOYALTY_CRON_LOOKBACK_DAYS = int(getenv("LOYALTY_CRON_LOOKBACK_DAYS", "2"))
