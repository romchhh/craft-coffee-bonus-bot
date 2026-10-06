#!/usr/bin/env python3
"""
Poster API helpers: clients, bonuses, test data.

  pip install requests
  python scripts/poster_tool.py

Token: full personal token from Access -> Integrations ("number:hash").
Loads POSTER_TOKEN from project-root .env when present.
"""
import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://joinposter.com/api"
TIMEOUT = 20
STATE_FILE = Path(__file__).resolve().parent / "test_clients.json"
SETTINGS = {"mult": int(os.environ.get("POSTER_BONUS_MULT", "100"))}
CARD_SEQ_START = 900001  # separate card-number range for test clients

# Fake data. Phones from a range unlikely to be real.
TEST_CLIENTS = [
    {"name": "TEST Іван Тестовий",   "phone": "0500000001", "bonus": 0,    "sex": 1, "birthday": "1990-05-12"},
    {"name": "TEST Олена Тестова",   "phone": "0500000002", "bonus": 50,   "sex": 2, "birthday": "1995-11-03"},
    {"name": "TEST Андрій Баланс",   "phone": "0500000003", "bonus": 120,  "sex": 1, "birthday": "1988-02-27"},
    {"name": "TEST Марія Бонусна",   "phone": "0500000004", "bonus": 250,  "sex": 2, "birthday": "2000-08-19"},
    {"name": "TEST Петро Постійний", "phone": "0500000005", "bonus": 1000, "sex": 1, "birthday": "1982-12-30"},
]


# ---------- helpers ----------

def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Задай змінну оточення {name}")
    return value


def get_token() -> str:
    token = os.environ.get("POSTER_TOKEN")
    if not token:
        token = getpass.getpass("Встав токен Poster (число:хеш, ввід прихований): ").strip()
        if not token:
            sys.exit("Токен не введено.")
        os.environ["POSTER_TOKEN"] = token
    return token


def normalize_phone(raw: str) -> str:
    """0501234567 / 380501234567 / +38 (050) 123-45-67 -> +380501234567"""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    if not (len(digits) == 12 and digits.startswith("380")):
        sys.exit(f"Не схоже на український номер: {raw}")
    return "+" + digits


def ean13_from_seq(seq: int) -> str:
    """Unique EAN-13 card number (prefix 2 = internal use)."""
    base = "2" + f"{seq:011d}"
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    return base + str((10 - total % 10) % 10)


def to_minor(amount) -> int:
    return int(round(float(amount) * SETTINGS["mult"]))


def call(method: str, data: dict | None = None, params: dict | None = None) -> dict:
    """Poster API method. GET without data, POST with form data."""
    url = f"{API}/{method}"
    query = {"token": get_token(), **(params or {})}
    if data is None:
        resp = requests.get(url, params=query, timeout=TIMEOUT)
    else:
        resp = requests.post(url, params=query, data=data, timeout=TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        sys.exit(f"Помилка Poster: {json.dumps(body, ensure_ascii=False)}")
    return body


def load_state() -> list:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else []


def save_state(items: list) -> None:
    STATE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def show(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------- commands (CLI args and menu) ----------

def cmd_auth_url(_a):
    query = urlencode({"application_id": env("POSTER_APP_ID"),
                       "redirect_uri": env("POSTER_REDIRECT_URI"),
                       "response_type": "code"})
    print(f"{API}/auth?{query}")


def cmd_token(a):
    resp = requests.post(
        f"https://{a.account}.joinposter.com/api/v2/auth/access_token",
        data={"application_id": env("POSTER_APP_ID"),
              "application_secret": env("POSTER_APP_SECRET"),
              "grant_type": "authorization_code",
              "code": a.code,
              "redirect_uri": env("POSTER_REDIRECT_URI")},
        timeout=TIMEOUT)
    print(resp.status_code)
    show(resp.json())


def cmd_groups(_a):
    show(call("clients.getGroups"))


def build_create_payload(a) -> dict:
    card = a.card or ean13_from_seq(a.card_seq)
    payload = {"client_name": a.name,
               "client_groups_id_client": a.group,
               "card_number": card,
               "phone": normalize_phone(a.phone)}
    if a.email:
        payload["email"] = a.email
    if a.birthday:
        payload["birthday"] = a.birthday  # YYYY-MM-DD
    if a.sex is not None:
        payload["client_sex"] = a.sex
    if a.bonus:
        payload["bonus"] = to_minor(a.bonus)
    return payload


def cmd_create(a):
    payload = build_create_payload(a)
    if a.dry_run:
        show(payload)
        return
    result = call("clients.createClient", payload)
    print("Клієнта створено. client_id =", result.get("response"),
          "| картка:", payload["card_number"])


def cmd_seed(a):
    state = load_state()
    for i, item in enumerate(TEST_CLIENTS):
        card = ean13_from_seq(CARD_SEQ_START + i)
        payload = {"client_name": item["name"],
                   "client_groups_id_client": a.group,
                   "card_number": card,
                   "phone": normalize_phone(item["phone"]),
                   "client_sex": item["sex"],
                   "birthday": item["birthday"]}
        if item["bonus"]:
            payload["bonus"] = to_minor(item["bonus"])

        if a.dry_run:
            print(json.dumps(payload, ensure_ascii=False))
            continue
        try:
            result = call("clients.createClient", payload)
        except SystemExit as exc:  # e.g. duplicate: continue
            print(f"[пропуск] {item['name']}: {exc}")
            continue
        client_id = result.get("response")
        state.append({"client_id": client_id, "name": item["name"],
                      "card": card, "bonus_uah": item["bonus"]})
        print(f"[ok] {item['name']}: client_id={client_id}, картка={card}, бонус={item['bonus']} грн")

    if not a.dry_run:
        save_state(state)
        print(f"\nid збережено у {STATE_FILE}. Перевір у Poster: баланс бонусів і групу.")


def cmd_list(_a):
    show(call("clients.getClients"))


def cmd_get(a):
    show(call("clients.getClient", params={"client_id": a.id}))


def cmd_set_bonus(a):
    show(call("clients.updateClient", {"client_id": a.id, "bonus": to_minor(a.amount)}))


def cmd_cleanup(a):
    state = load_state()
    if not state:
        print(f"{STATE_FILE} порожній: нічого видаляти.")
        return
    if not a.yes:
        for s in state:
            print(f"буде видалено: {s['client_id']} {s['name']}")
        sys.exit("Додай --yes, щоб справді видалити.")
    left = []
    for s in state:
        try:
            call("clients.removeClient", {"client_id": s["client_id"]})
            print(f"[видалено] {s['client_id']} {s['name']}")
        except SystemExit as exc:
            print(f"[не вийшло] {s['name']}: {exc}")
            left.append(s)
    save_state(left)


# ---------- interactive mode ----------

def ask(prompt: str, default=None, required: bool = True) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return str(default)
        if not required:
            return ""
        print("  Це поле обов'язкове.")


def ask_int(prompt: str, default=None) -> int:
    while True:
        try:
            return int(ask(prompt, default))
        except ValueError:
            print("  Потрібне ціле число.")


def ask_float(prompt: str, default=None) -> float:
    while True:
        try:
            return float(ask(prompt, default).replace(",", "."))
        except ValueError:
            print("  Потрібне число.")


def confirm(prompt: str, default: bool = False) -> bool:
    hint = "Т/н" if default else "т/Н"
    answer = input(f"{prompt} ({hint}): ").strip().lower()
    if not answer:
        return default
    return answer in ("т", "так", "y", "yes")


def pick_group() -> int:
    """Show Poster client groups and ask for an id."""
    try:
        body = call("clients.getGroups")
        items = body.get("response", [])
        rows = []
        if isinstance(items, list):
            for g in items:
                gid = g.get("client_groups_id") or g.get("id")
                name = g.get("client_groups_name") or g.get("name") or "?"
                if gid:
                    rows.append((gid, name))
        if rows:
            print("\nГрупи клієнтів:")
            for gid, name in rows:
                print(f"  {gid} - {name}")
        else:
            print("Не вдалося розпізнати список груп. Відповідь Poster:")
            show(body)
    except (SystemExit, requests.RequestException) as exc:
        print(f"Не вдалося отримати групи: {exc}")
    return ask_int("Id групи клієнтів з кешбеком")


def i_groups():
    cmd_groups(None)


def i_create():
    name = ask("Ім'я клієнта")
    phone = ask("Телефон (наприклад 0501234567)")
    group = pick_group()
    bonus = ask_float("Стартові бонуси, грн", 0)
    email = ask("Email (Enter - пропустити)", required=False)
    birthday = ask("Дата народження YYYY-MM-DD (Enter - пропустити)", required=False)
    sex_raw = ask("Стать: 1 - чол., 2 - жін. (Enter - пропустити)", required=False)
    card = ask("Номер картки (Enter - згенерувати EAN-13)", required=False)
    card_seq = 1
    if not card:
        card_seq = ask_int("Порядковий номер для генерації картки (має бути унікальним)", 1)
    args = argparse.Namespace(name=name, phone=phone, group=group, bonus=bonus,
                              email=email or None, birthday=birthday or None,
                              sex=int(sex_raw) if sex_raw in ("0", "1", "2") else None,
                              card=card or None, card_seq=card_seq, dry_run=True)
    print("\nБуде надіслано:")
    cmd_create(args)
    if confirm("Створити клієнта в Poster?", True):
        args.dry_run = False
        cmd_create(args)


def i_seed():
    group = pick_group()
    print("\nТестові клієнти:")
    cmd_seed(argparse.Namespace(group=group, dry_run=True))
    if confirm("\nСтворити їх у Poster?", False):
        cmd_seed(argparse.Namespace(group=group, dry_run=False))


def i_list():
    cmd_list(None)


def i_get():
    cmd_get(argparse.Namespace(id=ask_int("Id клієнта")))


def i_set_bonus():
    client_id = ask_int("Id клієнта")
    amount = ask_float("Новий баланс бонусів, грн")
    cmd_set_bonus(argparse.Namespace(id=client_id, amount=amount))


def i_cleanup():
    state = load_state()
    if not state:
        print(f"{STATE_FILE} порожній: тестових клієнтів, створених цим скриптом, немає.")
        return
    for s in state:
        print(f"  {s['client_id']} {s['name']}")
    if confirm("Видалити цих клієнтів із Poster?", False):
        cmd_cleanup(argparse.Namespace(yes=True))


def i_multiplier():
    print(f"Поточний множник: {SETTINGS['mult']} (100 = бонуси в копійках, 1 = в гривнях)")
    SETTINGS["mult"] = ask_int("Новий множник", SETTINGS["mult"])


MENU = [
    ("1", "Показати групи клієнтів", i_groups),
    ("2", "Створити одного клієнта", i_create),
    ("3", "Створити 5 тестових клієнтів з бонусами", i_seed),
    ("4", "Список усіх клієнтів", i_list),
    ("5", "Показати клієнта за id (баланс бонусів)", i_get),
    ("6", "Змінити бонуси клієнта", i_set_bonus),
    ("7", "Видалити тестових клієнтів, створених скриптом", i_cleanup),
    ("8", "Налаштування: множник бонусів", i_multiplier),
    ("0", "Вийти", None),
]


def interactive() -> None:
    actions = {key: fn for key, _, fn in MENU}
    while True:
        print("\n=== Poster: клієнти і бонуси ===")
        for key, title, _ in MENU:
            print(f"  {key}. {title}")
        choice = input("Обери пункт: ").strip()
        if choice == "0":
            print("Бувай!")
            return
        if choice not in actions:
            print("Такого пункту немає.")
            continue
        try:
            actions[choice]()
        except (SystemExit, requests.RequestException) as exc:
            print(f"\n[помилка] {exc}")


# ---------- entrypoint ----------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth-url").set_defaults(func=cmd_auth_url)

    p = sub.add_parser("token")
    p.add_argument("--account", required=True)
    p.add_argument("--code", required=True)
    p.set_defaults(func=cmd_token)

    sub.add_parser("groups").set_defaults(func=cmd_groups)

    p = sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--phone", required=True)
    p.add_argument("--group", type=int, required=True)
    p.add_argument("--card", help="готовий номер картки")
    p.add_argument("--card-seq", type=int, default=1, help="порядковий номер для генерації EAN-13")
    p.add_argument("--email")
    p.add_argument("--birthday", help="YYYY-MM-DD")
    p.add_argument("--sex", type=int, choices=[0, 1, 2])
    p.add_argument("--bonus", type=float, help="стартові бонуси в грн")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("seed")
    p.add_argument("--group", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_seed)

    sub.add_parser("list").set_defaults(func=cmd_list)

    p = sub.add_parser("get")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("set-bonus")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--amount", type=float, required=True, help="бонуси в грн")
    p.set_defaults(func=cmd_set_bonus)

    p = sub.add_parser("cleanup")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_cleanup)
    return parser


def main() -> None:
    load_dotenv()
    if len(sys.argv) == 1:
        try:
            interactive()
        except (KeyboardInterrupt, EOFError):
            print("\nПерервано.")
        return
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()