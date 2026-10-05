"""HTTP-сервер Mini App + JSON API для Craft Coffee."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from config import (
    APPLE_WALLET_SECRET,
    BOT_USERNAME,
    POSTER_APP_SECRET,
    WEBAPP_DEV,
    WEBAPP_HOST,
    WEBAPP_PORT,
    WEBAPP_URL,
    WELCOME_BONUS_UAH,
    token as BOT_TOKEN,
)
from database_functions.client_db import get_user, update_user_birthday
from utils.kyiv_time import kyiv_now_str
from services.quest_bonuses import grant_birthday_bonus, maybe_grant_annual_birthday, quests_payload
from database_functions.settings_db import get_welcome_bonus_uah, list_bonus_accruals_for_user
from services import apple_wallet, poster
from services import poster_media
from services.menu_visibility import category_visible, product_visible
from services.poster_cache import get_cached as poster_get_cached
from services.loyalty import process_closed_transaction
from services.charge_loyalty import build_loyalty_ui
from services.poster_client_cache import get_client_cached, invalidate_client
from services.telegram_webapp_auth import parse_telegram_user
import aiohttp as aiohttp_client
import hashlib as hashlib_std

log = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"
AVATAR_CACHE = Path("cache/avatars")
AVATAR_CACHE.mkdir(parents=True, exist_ok=True)


def _init_data_from_request(request: web.Request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("tma "):
        return auth[4:].strip()
    return (
        request.headers.get("X-Telegram-Init-Data")
        or request.rel_url.query.get("initData")
        or ""
    ).strip()


def _auth_user(request: web.Request) -> dict:
    if not BOT_TOKEN:
        log.error("webapp auth: TOKEN не задано в .env")
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "Сервер не налаштовано (немає TOKEN)"}),
            content_type="application/json",
        )

    init_data = _init_data_from_request(request)
    tg_user = parse_telegram_user(init_data, BOT_TOKEN, max_age_sec=0)
    if tg_user:
        return tg_user
    if WEBAPP_DEV:
        dev_id = request.rel_url.query.get("dev_user_id")
        if dev_id:
            return {"id": int(dev_id)}
    if not init_data:
        log.debug("webapp auth: немає initData")
        err = "Відкрий мініап з кнопки «Картка» в Telegram"
    else:
        log.info("webapp auth: невалідний підпис initData")
        err = "Не вдалося перевірити сесію Telegram. Закрий і відкрий мініап знову"
    raise web.HTTPUnauthorized(
        text=json.dumps({"error": err}),
        content_type="application/json",
    )


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_DIR / "index.html")


async def birthday_page(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_DIR / "birthday.html")


async def api_meta(_request: web.Request) -> web.Response:
    """Публічні дані для мініапу (посилання на бота для реєстрації)."""
    username = (BOT_USERNAME or "").strip().lstrip("@")
    bot_url = f"https://t.me/{username}" if username else None
    from Content.locations import INSTAGRAM_URL

    return web.json_response(
        {
            "bot_username": username or None,
            "bot_url": bot_url,
            "start_url": f"{bot_url}?start=card" if bot_url else None,
            "instagram_url": INSTAGRAM_URL,
        }
    )


async def _fetch_telegram_avatar(user_id: int) -> Path | None:
    """Завантажує аватар з Telegram Bot API у локальний кеш."""
    if not BOT_TOKEN:
        return None
    cached = list(AVATAR_CACHE.glob(f"{user_id}.*"))
    if cached:
        # оновлювати раз на добу
        age = datetime.now().timestamp() - cached[0].stat().st_mtime
        if age < 86400:
            return cached[0]

    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos",
                params={"user_id": user_id, "limit": 1},
                timeout=aiohttp_client.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
            photos = (((data or {}).get("result") or {}).get("photos") or [])
            if not photos:
                return None
            # найбільший розмір у першому наборі
            best = max(photos[0], key=lambda p: p.get("file_size") or 0)
            file_id = best["file_id"]

            async with session.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": file_id},
                timeout=aiohttp_client.ClientTimeout(total=15),
            ) as resp:
                file_info = await resp.json()
            file_path = ((file_info or {}).get("result") or {}).get("file_path")
            if not file_path:
                return None

            async with session.get(
                f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
                timeout=aiohttp_client.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return None
                body = await resp.read()

        ext = Path(file_path).suffix or ".jpg"
        out = AVATAR_CACHE / f"{user_id}{ext}"
        # прибрати старі варіанти
        for old in AVATAR_CACHE.glob(f"{user_id}.*"):
            if old != out:
                old.unlink(missing_ok=True)
        out.write_bytes(body)
        return out
    except Exception as exc:
        log.warning("avatar fetch failed for %s: %s", user_id, exc)
        return None


def _validate_birthday_iso(raw: str) -> str:
    try:
        parsed = datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Некоректна дата. Формат: РРРР-ММ-ДД"}),
            content_type="application/json",
        )
    today = date.today()
    try:
        youngest = date(today.year - 10, today.month, today.day)
        oldest = date(today.year - 90, today.month, today.day)
    except ValueError:
        youngest = date(today.year - 10, today.month, min(today.day, 28))
        oldest = date(today.year - 90, today.month, min(today.day, 28))
    if parsed < oldest or parsed > youngest:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Вік має бути від 10 до 90 років"}),
            content_type="application/json",
        )
    return parsed.strftime("%Y-%m-%d")


async def api_update_birthday(request: web.Request) -> web.Response:
    tg_user = _auth_user(request)
    db_user = get_user(tg_user["id"])
    if not db_user or not db_user.get("registered"):
        return web.json_response({"error": "Не зареєстровано"}, status=404)

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Некоректний JSON"}),
            content_type="application/json",
        )

    birthday = _validate_birthday_iso(body.get("birthday") or "")
    client_id = db_user.get("poster_client_id")
    if client_id:
        try:
            poster.update_client(client_id, birthday=birthday)
        except Exception as exc:
            log.warning("poster birthday update failed user=%s: %s", tg_user["id"], exc)
            raise web.HTTPBadGateway(
                text=json.dumps({"error": "Не вдалося оновити дату в касі. Спробуй пізніше"}),
                content_type="application/json",
            )

    update_user_birthday(int(tg_user["id"]), birthday)
    bonus_added = 0.0
    db_user = get_user(tg_user["id"]) or {}
    if not db_user.get("birthday_bonus_given"):
        try:
            bonus_added = grant_birthday_bonus(int(tg_user["id"]), client_id)
        except Exception:
            raise web.HTTPBadGateway(
                text=json.dumps({"error": "Дату зберегли, але бонус нарахувати не вдалося. Спробуй пізніше"}),
                content_type="application/json",
            )
    if client_id:
        invalidate_client(client_id)
    return web.json_response(
        {"ok": True, "birthday": birthday, "bonus_added": bonus_added, "quests": quests_payload(int(tg_user["id"]))}
    )


async def api_me(request: web.Request) -> web.Response:
    tg_user = _auth_user(request)
    db_user = get_user(tg_user["id"])
    if not db_user or not db_user.get("registered"):
        return web.json_response({"error": "Не зареєстровано"}, status=404)

    bonus = 0.0
    birthday = db_user.get("birthday")
    card_number = db_user.get("card_number")
    if db_user.get("poster_client_id"):
        try:
            client = await asyncio.to_thread(
                get_client_cached, int(db_user["poster_client_id"])
            )
            bonus = poster.from_minor(client.get("bonus"))
            if client.get("birthday") and client["birthday"] not in ("0000-00-00", None, ""):
                birthday = client["birthday"]
            poster_card = (client.get("card_number") or "").strip()
            if poster_card:
                card_number = poster_card
        except Exception as exc:
            log.warning("get_client failed: %s", exc)

    photo_url = None
    avatar = await _fetch_telegram_avatar(int(tg_user["id"]))
    if avatar:
        exp = int(datetime.now().timestamp()) + 86400
        photo_url = f"/api/avatar?t={_wallet_token(int(tg_user['id']), exp)}"

    try:
        annual = maybe_grant_annual_birthday(int(tg_user["id"]))
        if annual > 0:
            bonus = poster.get_client_bonus_uah(db_user["poster_client_id"]) if db_user.get("poster_client_id") else bonus
    except Exception as exc:
        log.warning("annual birthday check: %s", exc)

    loyalty = build_loyalty_ui(int(tg_user["id"]), bonus)
    phone_raw = db_user.get("user_phone") or ""
    phone_digits = ""
    phone_id_suffix = ""
    try:
        if phone_raw:
            phone_digits = poster.phone_digits(phone_raw)
            phone_id_suffix = phone_digits[-4:] if len(phone_digits) >= 4 else phone_digits
    except ValueError:
        phone_digits = re.sub(r"\D", "", str(phone_raw))
        phone_id_suffix = phone_digits[-4:] if phone_digits else ""

    return web.json_response(
        {
            "name": db_user.get("display_name") or db_user.get("user_first_name") or "Гість",
            "phone": phone_raw,
            "phone_id_suffix": phone_id_suffix,
            "phone_digits": phone_digits,
            "birthday": birthday,
            "card_number": card_number,
            "poster_client_id": db_user.get("poster_client_id"),
            "bonus": bonus,
            "photo_url": photo_url,
            "wallet": apple_wallet.status(),
            "loyalty": loyalty,
            "quests": quests_payload(int(tg_user["id"])),
        }
    )


async def api_avatar(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("t", "")
    user_id = _parse_wallet_token(token)
    if not user_id:
        raise web.HTTPForbidden(text="Forbidden")
    path = await _fetch_telegram_avatar(user_id)
    if not path or not path.exists():
        raise web.HTTPNotFound(text="No avatar")
    ctype = "image/jpeg"
    if path.suffix.lower() == ".png":
        ctype = "image/png"
    elif path.suffix.lower() == ".webp":
        ctype = "image/webp"
    return web.FileResponse(path, headers={"Content-Type": ctype, "Cache-Control": "private, max-age=3600"})


def _media_token(kind: str, item_id: int, exp: int) -> str:
    payload = f"{kind}:{item_id}:{exp}"
    sig = hmac.new(APPLE_WALLET_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _parse_media_token(token: str, kind: str, item_id: int) -> bool:
    try:
        kind_s, id_s, exp_s, sig = token.split(":", 3)
        if kind_s != kind or int(id_s) != int(item_id):
            return False
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if exp < int(datetime.now().timestamp()):
        return False
    expected = hmac.new(
        APPLE_WALLET_SECRET.encode(),
        f"{kind}:{item_id}:{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def _poster_media_url(kind: str, item_id: int, exp: int) -> str:
    return f"/api/poster/media?kind={kind}&id={item_id}&t={_media_token(kind, item_id, exp)}"


def _serialize_menu(spot_id_i: int | None) -> dict:
    categories_raw = poster.get_categories()
    cat_by_id = {str(c.get("category_id")): c for c in categories_raw}
    hidden_cats = {
        cid
        for cid, c in cat_by_id.items()
        if str(c.get("category_hidden")) == "1"
    }

    exp = int(datetime.now().timestamp()) + 86400 * 7
    items = []
    for p in poster.get_products(spot_id_i):
        if str(p.get("hidden")) == "1":
            continue
        cat_id = str(p.get("menu_category_id") or "")
        if cat_id in hidden_cats:
            continue
        cat_name = p.get("category_name") or cat_by_id.get(cat_id, {}).get("category_name")
        if not product_visible(p, cat_id, cat_name):
            continue
        price = poster.product_price_uah(p, spot_id_i)
        photo_path = (p.get("photo") or "").strip()
        photo_url = _poster_media_url("p", int(p["product_id"]), exp) if photo_path else None
        items.append(
            {
                "id": int(p.get("product_id")),
                "name": p.get("product_name") or "—",
                "category": p.get("category_name") or "Меню",
                "category_id": cat_id,
                "price": price,
                "photo_url": photo_url,
                "sort_order": int(p.get("sort_order") or 999),
            }
        )

    visible_cat_ids = {str(i["category_id"]) for i in items}

    categories = []
    for c in categories_raw:
        if str(c.get("category_hidden")) == "1":
            continue
        cid_s = str(c.get("category_id"))
        if cid_s not in visible_cat_ids:
            continue
        if not category_visible(cid_s, c.get("category_name")):
            continue
        cid = int(c.get("category_id"))
        photo_path = (c.get("category_photo") or "").strip()
        categories.append(
            {
                "id": str(c.get("category_id")),
                "name": c.get("category_name") or "Меню",
                "photo_url": _poster_media_url("c", cid, exp) if photo_path else None,
                "sort_order": int(c.get("sort_order") or 999),
            }
        )
    categories.sort(key=lambda x: (x["sort_order"], x["name"]))
    items.sort(key=lambda x: (x["category"], x["sort_order"], x["name"]))
    return {"items": items, "categories": categories}


def _build_menu_payload(spot_id_i: int | None) -> dict:
    key = f"menu_web_v3_{spot_id_i if spot_id_i is not None else 'all'}"
    return poster_get_cached(key, lambda: _serialize_menu(spot_id_i))


async def api_poster_media(request: web.Request) -> web.Response:
    kind = (request.rel_url.query.get("kind") or "").strip()
    item_id_s = request.rel_url.query.get("id", "")
    token = request.rel_url.query.get("t", "")
    if kind not in ("p", "c"):
        raise web.HTTPBadRequest(text="Bad kind")
    try:
        item_id = int(item_id_s)
    except ValueError:
        raise web.HTTPBadRequest(text="Bad id")
    if not _parse_media_token(token, kind, item_id):
        raise web.HTTPForbidden(text="Forbidden")

    if kind == "p":
        row = poster.product_by_id(item_id)
        poster_path = (row or {}).get("photo")
    else:
        row = poster.category_by_id(item_id)
        poster_path = (row or {}).get("category_photo")

    if not row or not poster_path:
        raise web.HTTPNotFound(text="Not found")

    path = await asyncio.to_thread(poster_media.ensure_cached, kind, item_id, poster_path)
    if not path or not path.exists():
        raise web.HTTPNotFound(text="Image unavailable")

    ctype = "image/jpeg"
    ext = path.suffix.lower()
    if ext == ".png":
        ctype = "image/png"
    elif ext == ".webp":
        ctype = "image/webp"
    elif ext == ".gif":
        ctype = "image/gif"
    return web.FileResponse(
        path,
        headers={"Content-Type": ctype, "Cache-Control": "public, max-age=86400"},
    )


async def api_spots(request: web.Request) -> web.Response:
    _auth_user(request)
    from Content.locations import INSTAGRAM_URL, locations_for_api

    return web.json_response(
        {
            "items": locations_for_api(),
            "instagram_url": INSTAGRAM_URL,
        }
    )


async def api_menu(request: web.Request) -> web.Response:
    _auth_user(request)
    spot_id = request.rel_url.query.get("spot_id")
    spot_id_i = int(spot_id) if spot_id else None
    refresh = request.rel_url.query.get("refresh") == "1"
    if refresh:
        from services.poster_cache import invalidate

        invalidate("products")
        invalidate("categories")
        invalidate(f"menu_web_v3_{spot_id_i if spot_id_i is not None else 'all'}")
    try:
        payload = await asyncio.to_thread(_build_menu_payload, spot_id_i)
    except Exception as exc:
        log.exception("menu")
        return web.json_response({"error": str(exc)}, status=502)
    if not payload.get("items"):
        log.warning("menu empty spot_id=%s refresh=%s", spot_id_i, refresh)
    return web.json_response(payload)


async def api_history(request: web.Request) -> web.Response:
    tg_user = _auth_user(request)
    db_user = get_user(tg_user["id"])
    if not db_user or not db_user.get("poster_client_id"):
        return web.json_response({"purchases": [], "bonuses": []})

    client_id = db_user["poster_client_id"]
    tg_id = int(tg_user["id"])
    accruals_by_tx: dict[str, dict] = {}
    for acc in list_bonus_accruals_for_user(tg_id):
        tid = str(acc.get("transaction_id") or "")
        if tid:
            accruals_by_tx[tid] = acc

    purchases = []
    try:
        txs = poster.get_transactions_for_client(client_id)
        spots = {int(s["spot_id"]): s.get("spot_name") or "" for s in poster.get_spots()}
        for t in sorted(txs, key=lambda x: x.get("date_close_date") or "", reverse=True)[:40]:
            tid = str(t.get("transaction_id") or poster.transaction_id_from_row(t) or "")
            acc = accruals_by_tx.get(tid)
            cashback_uah = float(acc.get("bonus_uah") or 0) if acc else 0.0
            close_date = t.get("date_close_date") or "—"
            purchases.append(
                {
                    "transaction_id": tid,
                    "date": close_date,
                    "spot": spots.get(int(t.get("spot_id") or 0), "Craft Coffee"),
                    "sum": poster.from_minor(t.get("sum")),
                    "payed": poster.from_minor(t.get("payed_sum")),
                    "bonus_spent": poster.from_minor(t.get("payed_bonus")),
                    "cashback_uah": cashback_uah,
                }
            )
    except Exception as exc:
        log.warning("history purchases: %s", exc)

    bonuses = []
    if db_user.get("welcome_bonus_given"):
        bonuses.append(
            {
                "date": (db_user.get("join_date") or "")[:19] or kyiv_now_str(),
                "title": "Вітальні бонуси за реєстрацію",
                "amount": get_welcome_bonus_uah(),
            }
        )
    if db_user.get("birthday_bonus_given"):
        from database_functions.settings_db import get_birthday_bonus_uah

        bonuses.append(
            {
                "date": (db_user.get("last_activity") or "")[:19] or kyiv_now_str(),
                "title": "Бонус за день народження",
                "amount": get_birthday_bonus_uah(),
            }
        )

    return web.json_response({"purchases": purchases, "bonuses": bonuses})


def _wallet_token(user_id: int, exp: int) -> str:
    payload = f"{user_id}:{exp}"
    sig = hmac.new(APPLE_WALLET_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _parse_wallet_token(token: str) -> int | None:
    try:
        user_id_s, exp_s, sig = token.split(":", 2)
        user_id = int(user_id_s)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return None
    if exp < int(datetime.now().timestamp()):
        return None
    expected = hmac.new(
        APPLE_WALLET_SECRET.encode(),
        f"{user_id}:{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    return user_id


async def api_wallet_link(request: web.Request) -> web.Response:
    """Повертає короткоживуче посилання на .pkpass (для openLink у Telegram)."""
    tg_user = _auth_user(request)
    db_user = get_user(tg_user["id"])
    if not db_user or not db_user.get("registered"):
        return web.json_response({"error": "Не зареєстровано"}, status=404)
    if not db_user.get("card_number"):
        return web.json_response({"error": "Немає номера картки"}, status=400)
    if not apple_wallet.is_configured():
        return web.json_response(
            {
                "error": "Apple Wallet ще не налаштовано на сервері. Потрібні сертифікати Pass Type ID з Apple Developer.",
                "configured": False,
            },
            status=503,
        )
    if not WEBAPP_URL:
        return web.json_response({"error": "WEBAPP_URL не задано"}, status=503)

    exp = int(datetime.now().timestamp()) + 300  # 5 хв
    token = _wallet_token(int(tg_user["id"]), exp)
    url = f"{WEBAPP_URL}/api/wallet/apple.pkpass?t={token}"
    return web.json_response({"url": url, "expires_in": 300})


async def api_wallet_pkpass(request: web.Request) -> web.Response:
    token = request.rel_url.query.get("t", "")
    user_id = _parse_wallet_token(token)
    if not user_id:
        return web.json_response({"error": "Посилання недійсне або прострочене"}, status=403)

    db_user = get_user(user_id)
    if not db_user or not db_user.get("registered") or not db_user.get("card_number"):
        return web.json_response({"error": "Картку не знайдено"}, status=404)

    bonus = 0.0
    if db_user.get("poster_client_id"):
        try:
            bonus = poster.get_client_bonus_uah(db_user["poster_client_id"])
        except Exception:
            pass

    try:
        pkpass = apple_wallet.create_pkpass(
            serial=f"craft-{db_user.get('poster_client_id') or user_id}-{db_user['card_number']}",
            name=db_user.get("display_name") or db_user.get("user_first_name") or "Гість",
            card_number=db_user["card_number"],
            phone=db_user.get("user_phone"),
            bonus=bonus,
        )
    except apple_wallet.AppleWalletError as exc:
        return web.json_response({"error": str(exc)}, status=503)
    except Exception as exc:
        log.exception("pkpass")
        return web.json_response({"error": f"Не вдалося створити pass: {exc}"}, status=500)

    return web.Response(
        body=pkpass,
        headers={
            "Content-Type": "application/vnd.apple.pkpass",
            "Content-Disposition": 'attachment; filename="craft-coffee.pkpass"',
            "Cache-Control": "no-store",
        },
    )


async def poster_webhook(request: web.Request) -> web.Response:
    """
    Poster webhook. У кабінеті вкажи URL:
      {WEBAPP_URL}/webhook/poster
    Увімкни сутності: transaction, client_payed_sum.
    """
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"status": "accept"})

    if POSTER_APP_SECRET:
        verify_original = payload.get("verify")
        check = [
            str(payload.get("account", "")),
            str(payload.get("object", "")),
            str(payload.get("object_id", "")),
            str(payload.get("action", "")),
        ]
        if "data" in payload and payload["data"] is not None:
            check.append(str(payload["data"]))
        check.append(str(payload.get("time", "")))
        check.append(POSTER_APP_SECRET)
        calc = hashlib_std.md5(";".join(check).encode()).hexdigest()
        if calc != verify_original:
            log.warning("Poster webhook bad verify")
            return web.json_response({"status": "accept"})

    obj = payload.get("object")
    action = payload.get("action")
    object_id = payload.get("object_id")

    # Закриття чека: transaction changed/closed або client_payed_sum
    should_process = False
    transaction_id = None

    if obj == "transaction" and action in ("changed", "closed", "added"):
        transaction_id = object_id
        should_process = True
    elif obj == "client_payed_sum":
        # іноді в data є transaction_id
        data = payload.get("data") or {}
        if isinstance(data, dict):
            transaction_id = data.get("transaction_id") or data.get("order_id") or object_id
        else:
            transaction_id = object_id
        should_process = True

    if should_process and transaction_id:
        try:
            from main import bot
            result = await process_closed_transaction(transaction_id, bot=bot)
            log.info("loyalty webhook tx=%s result=%s", transaction_id, result)
            # Повернення / зміна чека, що вже кваліфікував реферал
            if result.get("status") == "skip" and result.get("reason") == "already_processed":
                from services.referrals import review_transaction_for_referral

                rev = review_transaction_for_referral(str(transaction_id))
                if rev.get("status") != "skip":
                    log.info("referral review tx=%s result=%s", transaction_id, rev)
        except Exception:
            log.exception("loyalty webhook failed tx=%s", transaction_id)

    return web.json_response({"status": "accept"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/birthday", birthday_page)
    app.router.add_get("/api/meta", api_meta)
    app.router.add_get("/api/me", api_me)
    app.router.add_post("/api/me/birthday", api_update_birthday)
    app.router.add_get("/api/avatar", api_avatar)
    app.router.add_get("/api/spots", api_spots)
    app.router.add_get("/api/menu", api_menu)
    app.router.add_get("/api/poster/media", api_poster_media)
    app.router.add_get("/api/history", api_history)
    app.router.add_get("/api/wallet/link", api_wallet_link)
    app.router.add_get("/api/wallet/apple.pkpass", api_wallet_pkpass)
    app.router.add_post("/webhook/poster", poster_webhook)
    app.router.add_static("/static/", WEBAPP_DIR, show_index=False)
    return app


async def start_webapp(runner_holder: dict) -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
    await site.start()
    runner_holder["runner"] = runner
    log.info("Mini App server on http://%s:%s", WEBAPP_HOST, WEBAPP_PORT)
    print(f"Mini App server: http://{WEBAPP_HOST}:{WEBAPP_PORT}")


async def stop_webapp(runner_holder: dict) -> None:
    runner = runner_holder.get("runner")
    if runner:
        await runner.cleanup()
