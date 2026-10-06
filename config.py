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
# Poster: client group «Bonuses2» / Bonusi2 (loyalty), cabinet id = 2
POSTER_CLIENT_GROUP_NAME = "Бонуси2"
POSTER_CLIENT_GROUP_ID = 2
# Receipt/menu amounts in Poster are minor units (100 = 1 UAH). Not for client bonus field.
POSTER_MONEY_MULT = int(getenv("POSTER_BONUS_MULT", "100"))
WELCOME_BONUS_UAH = float(getenv("WELCOME_BONUS_UAH", "50"))
BIRTHDAY_BONUS_UAH = float(getenv("BIRTHDAY_BONUS_UAH", "20"))
ANNUAL_BIRTHDAY_BONUS_UAH = float(getenv("ANNUAL_BIRTHDAY_BONUS_UAH", "50"))
REFERRAL_BONUS_UAH = float(getenv("REFERRAL_BONUS_UAH", "10"))
# Referral: min cash payment, windows, daily auto limit
REFERRAL_MIN_CASH_UAH = float(getenv("REFERRAL_MIN_CASH_UAH", "50"))
REFERRAL_PURCHASE_WINDOW_DAYS = int(getenv("REFERRAL_PURCHASE_WINDOW_DAYS", "30"))
REFERRAL_INVITE_TTL_DAYS = int(getenv("REFERRAL_INVITE_TTL_DAYS", "30"))
REFERRAL_REWARD_VALID_DAYS = int(getenv("REFERRAL_REWARD_VALID_DAYS", "30"))
REFERRAL_DAILY_AUTO_LIMIT = int(getenv("REFERRAL_DAILY_AUTO_LIMIT", "5"))
# Quest/achievement rewards (editable in admin)
QUEST_VISITS_REWARD_UAH = float(getenv("QUEST_VISITS_REWARD_UAH", "15"))
QUEST_COMBO_REWARD_UAH = float(getenv("QUEST_COMBO_REWARD_UAH", "15"))
QUEST_DRINKS_REWARD_UAH = float(getenv("QUEST_DRINKS_REWARD_UAH", "15"))
ACH_DAYS_5_REWARD_UAH = float(getenv("ACH_DAYS_5_REWARD_UAH", "10"))
ACH_DAYS_15_REWARD_UAH = float(getenv("ACH_DAYS_15_REWARD_UAH", "20"))
ACH_DAYS_30_REWARD_UAH = float(getenv("ACH_DAYS_30_REWARD_UAH", "30"))
QUEST_WINDOW_DAYS = int(getenv("QUEST_WINDOW_DAYS", "14"))

WEBAPP_URL = (getenv("WEBAPP_URL") or "").rstrip("/")
WEBAPP_HOST = getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(getenv("WEBAPP_PORT", "8080"))
WEBAPP_DEV = getenv("WEBAPP_DEV", "0") == "1"

# Apple Wallet (.pkpass) — requires Apple Developer Pass Type ID
APPLE_PASS_TYPE_ID = getenv("APPLE_PASS_TYPE_ID", "")
APPLE_TEAM_ID = getenv("APPLE_TEAM_ID", "")
APPLE_ORG_NAME = getenv("APPLE_ORG_NAME", "Craft Coffee")
APPLE_PASS_CERT = getenv("APPLE_PASS_CERT", "certs/pass_cert.pem")
APPLE_PASS_KEY = getenv("APPLE_PASS_KEY", "certs/pass_key.pem")
APPLE_PASS_KEY_PASSWORD = getenv("APPLE_PASS_KEY_PASSWORD", "")
APPLE_WWDR_CERT = getenv("APPLE_WWDR_CERT", "certs/wwdr.pem")
APPLE_WALLET_SECRET = getenv("APPLE_WALLET_SECRET") or (token or "craft-wallet-secret")

# Poster webhooks (application secret from developer cabinet; optional)
POSTER_APP_SECRET = getenv("POSTER_APP_SECRET", "")
CASHBACK_PERCENT = float(getenv("CASHBACK_PERCENT", "5"))

# Google Maps (mini app «use bonuses» block). If empty — first Poster spot.
MAPS_URL = (getenv("MAPS_URL") or "").strip()

# Background scan of closed receipts (if webhook was missed)
LOYALTY_CRON_ENABLED = getenv("LOYALTY_CRON_ENABLED", "1") == "1"
LOYALTY_CRON_INTERVAL_SEC = int(getenv("LOYALTY_CRON_INTERVAL_SEC", "60"))
LOYALTY_CRON_LOOKBACK_DAYS = int(getenv("LOYALTY_CRON_LOOKBACK_DAYS", "2"))
