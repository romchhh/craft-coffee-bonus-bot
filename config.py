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
# Poster loyalty group (bonus system, 0%). Account 965187 → «Бонуси Телеграм бот» id=10
POSTER_CLIENT_GROUP_NAME = (getenv("POSTER_CLIENT_GROUP_NAME") or "Бонуси Телеграм бот").strip()
POSTER_CLIENT_GROUP_ID = int(getenv("POSTER_CLIENT_GROUP_ID", "10") or "10")
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
# Purchase quests / achievements (visits, combo, drinks, days). Off until Mini App UI returns.
# Cashback from Заряд and birthday/referral are independent of this flag.
QUESTS_ENABLED = getenv("QUESTS_ENABLED", "0") == "1"

# Telegram username for client support (editable in admin → Контакт підтримки)
SUPPORT_USERNAME = (getenv("SUPPORT_USERNAME") or "Oleksandr_Hniezdilov").strip().lstrip("@")

WEBAPP_URL = (getenv("WEBAPP_URL") or "").rstrip("/")
WEBAPP_HOST = getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(getenv("WEBAPP_PORT", "8080"))
WEBAPP_DEV = getenv("WEBAPP_DEV", "0") == "1"

# Apple Wallet (.pkpass) — requires Apple Developer Pass Type ID
APPLE_PASS_TYPE_ID = getenv("APPLE_PASS_TYPE_ID", "")
APPLE_TEAM_ID = getenv("APPLE_TEAM_ID", "")
APPLE_ORG_NAME = getenv("APPLE_ORG_NAME", "Крафт Кава")
APPLE_PASS_CERT = getenv("APPLE_PASS_CERT", "apple_wallet_certs/pass_cert.pem")
APPLE_PASS_KEY = getenv("APPLE_PASS_KEY", "apple_wallet_certs/pass_key.pem")
APPLE_PASS_KEY_PASSWORD = getenv("APPLE_PASS_KEY_PASSWORD", "")
APPLE_WWDR_CERT = getenv("APPLE_WWDR_CERT", "apple_wallet_certs/wwdr.pem")
APPLE_WALLET_SECRET = getenv("APPLE_WALLET_SECRET") or (token or "craft-wallet-secret")

GOOGLE_WALLET_ISSUER_ID = (getenv("GOOGLE_WALLET_ISSUER_ID") or "3388000000023224873").strip()
GOOGLE_WALLET_CLASS_SUFFIX = (getenv("GOOGLE_WALLET_CLASS_SUFFIX") or "craft_coffee_loyalty").strip()
WALLET_BG_COLOR = (getenv("WALLET_BG_COLOR") or "#35221A").strip()
WALLET_LOGO_URL = (getenv("WALLET_LOGO_URL") or "").strip()


def _resolve_google_wallet_key_file() -> str:
    explicit = (getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if explicit:
        return explicit
    for path in sorted(PROJECT_ROOT.glob("telebots-e-commerce-*.json")):
        return str(path)
    return ""


GOOGLE_WALLET_KEY_FILE = _resolve_google_wallet_key_file()

# Poster webhooks (application secret from developer cabinet; optional)
POSTER_APP_SECRET = getenv("POSTER_APP_SECRET", "")
CASHBACK_PERCENT = float(getenv("CASHBACK_PERCENT", "1"))

# Google Maps (mini app «use bonuses» block). If empty — first Poster spot.
MAPS_URL = (getenv("MAPS_URL") or "").strip()

# Background scan of closed receipts (if webhook was missed)
LOYALTY_CRON_ENABLED = getenv("LOYALTY_CRON_ENABLED", "1") == "1"
LOYALTY_CRON_INTERVAL_SEC = int(getenv("LOYALTY_CRON_INTERVAL_SEC", "60"))
LOYALTY_CRON_LOOKBACK_DAYS = int(getenv("LOYALTY_CRON_LOOKBACK_DAYS", "2"))

# Daily SQLite backup → admin Telegram DMs (Europe/Kyiv clock)
BACKUP_ENABLED = getenv("BACKUP_ENABLED", "1") == "1"
BACKUP_HOUR_KYIV = int(getenv("BACKUP_HOUR_KYIV", "3") or "3")
BACKUP_MINUTE_KYIV = int(getenv("BACKUP_MINUTE_KYIV", "15") or "15")
BACKUP_KEEP_DAYS = int(getenv("BACKUP_KEEP_DAYS", "14") or "14")
