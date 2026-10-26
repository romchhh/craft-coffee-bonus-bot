#!/usr/bin/env python3
"""
Тест Google Wallet: бонусна картка «Крафт Кава».

Що робить:
  1. (опційно) створює Loyalty Class, якщо його ще немає
  2. створює Loyalty Object (картку клієнта) або знаходить наявний
  3. друкує посилання "Add to Google Wallet"
  4. (опційно) оновлює баланс бонусів: --set-points 150

Встановлення:
  pip install google-auth requests

Запуск (змінні в .env або export):
  export GOOGLE_APPLICATION_CREDENTIALS=/шлях/до/service-account.json
  export GOOGLE_WALLET_ISSUER_ID=3388000000023224873
  export GOOGLE_WALLET_CLASS_SUFFIX=craft_coffee_loyalty
  python wallet_test.py --card-number 1000001 --name "Тест Тестович" --points 50
  python test.py   # те саме з дефолтами (без аргументів)

Не комітьте JSON-ключ у репозиторій.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

from google.auth import crypt, jwt
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

BASE = "https://walletobjects.googleapis.com/walletobjects/v1"
SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]

ISSUER_ID = os.environ.get("GOOGLE_WALLET_ISSUER_ID", "3388000000023224873")
CLASS_SUFFIX = os.environ.get("GOOGLE_WALLET_CLASS_SUFFIX", "craft_coffee_loyalty")

CLASS_ID = f"{ISSUER_ID}.{CLASS_SUFFIX}"

ISSUER_NAME = "Крафт Кава"
PROGRAM_NAME = "Бонусна картка Крафт Кава"
WEBAPP_URL = (os.environ.get("WEBAPP_URL") or "").rstrip("/")
LOGO_URL = (
    os.environ.get("WALLET_LOGO_URL")
    or (f"{WEBAPP_URL}/logo.png" if WEBAPP_URL else "")
)
BG_COLOR = os.environ.get("WALLET_BG_COLOR", "#35221A")


def _resolve_key_file() -> str | None:
    explicit = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if explicit:
        return explicit
    for path in sorted(PROJECT_ROOT.glob("telebots-e-commerce-*.json")):
        return str(path)
    return None


KEY_FILE = _resolve_key_file()


def get_session():
    if not KEY_FILE or not os.path.exists(KEY_FILE):
        sys.exit(
            "Вкажіть GOOGLE_APPLICATION_CREDENTIALS у .env або export "
            "(шлях до JSON-ключа сервісного акаунта Google)."
        )
    creds = service_account.Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    return AuthorizedSession(creds)


def show_error(resp):
    print(f"Помилка {resp.status_code}: {resp.text}")
    if resp.status_code == 403:
        print(
            "→ Додайте email сервісного акаунта в консолі Wallet (блок REST API) "
            "і увімкніть Google Wallet API в Google Cloud."
        )


def ensure_class(session, create):
    r = session.get(f"{BASE}/loyaltyClass/{CLASS_ID}")
    if r.status_code == 200:
        print(f"Клас знайдено: {CLASS_ID}")
        return
    if r.status_code != 404:
        show_error(r)
        sys.exit(1)
    if not create:
        sys.exit(
            f"Клас {CLASS_ID} не знайдено. Створіть його в консолі "
            f"або запустіть з --create-class (потрібен WALLET_LOGO_URL або WEBAPP_URL)."
        )
    if not LOGO_URL:
        sys.exit(
            "Для --create-class задайте WALLET_LOGO_URL або WEBAPP_URL "
            "(публічне HTTPS-посилання на логотип, напр. …/logo.png)."
        )
    body = {
        "id": CLASS_ID,
        "issuerName": ISSUER_NAME,
        "programName": PROGRAM_NAME,
        "programLogo": {
            "sourceUri": {"uri": LOGO_URL},
            "contentDescription": {"defaultValue": {"language": "uk", "value": "Логотип Крафт Кава"}},
        },
        "hexBackgroundColor": BG_COLOR,
        "reviewStatus": "UNDER_REVIEW",
    }
    r = session.post(f"{BASE}/loyaltyClass", json=body)
    if r.status_code != 200:
        show_error(r)
        sys.exit(1)
    print(f"Клас створено: {CLASS_ID}")


def build_object(object_id, card_number, name, points, barcode_type):
    return {
        "id": object_id,
        "classId": CLASS_ID,
        "state": "ACTIVE",
        "accountId": card_number,
        "accountName": name,
        "barcode": {
            "type": barcode_type,
            "value": card_number,
            "alternateText": card_number,
        },
        "loyaltyPoints": {
            "label": "Бонуси",
            "balance": {"int": points},
        },
    }


def ensure_object(session, object_id, card_number, name, points, barcode_type):
    r = session.get(f"{BASE}/loyaltyObject/{object_id}")
    if r.status_code == 200:
        print(f"Картка вже існує: {object_id}")
        return
    if r.status_code != 404:
        show_error(r)
        sys.exit(1)
    r = session.post(
        f"{BASE}/loyaltyObject",
        json=build_object(object_id, card_number, name, points, barcode_type),
    )
    if r.status_code != 200:
        show_error(r)
        sys.exit(1)
    print(f"Картку створено: {object_id}")


def set_points(session, object_id, points):
    r = session.patch(
        f"{BASE}/loyaltyObject/{object_id}",
        json={"loyaltyPoints": {"label": "Бонуси", "balance": {"int": points}}},
    )
    if r.status_code != 200:
        show_error(r)
        sys.exit(1)
    print(f"Баланс оновлено: {points}")


def save_link(object_id):
    signer = crypt.RSASigner.from_service_account_file(KEY_FILE)
    with open(KEY_FILE, encoding="utf-8") as f:
        sa_email = json.load(f)["client_email"]
    claims = {
        "iss": sa_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": [],
        "payload": {"loyaltyObjects": [{"id": object_id}]},
    }
    token = jwt.encode(signer, claims).decode("utf-8")
    return f"https://pay.google.com/gp/v/save/{token}"


DEFAULT_CARD = "1000001"
DEFAULT_NAME = "Тест Тестович"
DEFAULT_POINTS = 50


def main():
    bare_run = len(sys.argv) == 1
    p = argparse.ArgumentParser(description="Тест Google Wallet loyalty")
    p.add_argument(
        "--card-number",
        default=DEFAULT_CARD,
        help=f"номер картки / штрихкод (за замовч.: {DEFAULT_CARD})",
    )
    p.add_argument("--name", default=DEFAULT_NAME, help="ім'я власника картки")
    p.add_argument("--points", type=int, default=DEFAULT_POINTS, help="початковий баланс")
    p.add_argument(
        "--barcode",
        default="CODE_128",
        choices=["CODE_128", "QR_CODE", "EAN_13"],
        help="тип штрихкода (має збігатися з Poster)",
    )
    p.add_argument("--create-class", action="store_true", help="створити клас, якщо його немає")
    p.add_argument("--set-points", type=int, help="оновити баланс наявної картки")
    args = p.parse_args()

    if bare_run:
        print(
            f"Демо без аргументів: картка {args.card_number}, "
            f"«{args.name}», {args.points} бонусів.\n"
        )

    session = get_session()
    create_class = args.create_class or (bare_run and bool(LOGO_URL))
    ensure_class(session, create_class)

    object_id = f"{ISSUER_ID}.card_{args.card_number}"
    ensure_object(session, object_id, args.card_number, args.name, args.points, args.barcode)

    if args.set_points is not None:
        set_points(session, object_id, args.set_points)

    print("\nВідкрийте на Android (акаунт має бути доданий як тестовий):\n")
    print(save_link(object_id))


if __name__ == "__main__":
    main()
