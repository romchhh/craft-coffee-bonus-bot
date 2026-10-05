"""Квести та досягнення MVP (D571–D580) + винагороди з адмінки."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from database_functions import quests_db as qdb
from database_functions.client_db import get_user
from database_functions.settings_db import (
    get_ach_days_15_reward_uah,
    get_ach_days_30_reward_uah,
    get_ach_days_5_reward_uah,
    get_birthday_bonus_uah,
    get_quest_combo_reward_uah,
    get_quest_drinks_reward_uah,
    get_quest_visits_reward_uah,
    get_quest_window_days,
    rewards_snapshot,
)
from services import poster
from services.charge_loyalty import parse_purchase_datetime
from services.poster_client_cache import invalidate_client
from utils.kyiv_time import KYIV_TZ, kyiv_now_str, now_kyiv

log = logging.getLogger(__name__)

MIN_VISIT_GAP_HOURS = 2
DAYS_STEPS = (5, 15, 30)

_DRINK_RE = re.compile(
    r"кав|кофе|coffee|еспрес|латте|лате|капуч|американо|раф|чай|tea|лимонад|смузі|"
    r"фреш|сік|какао|матча|напій|флет|мокко|мока|глясе|айс|мілкшейк|бабл|пунш|"
    r"кола|лимонад",
    re.I,
)
_FOOD_RE = re.compile(
    r"їжа|їст|сендвіч|паніні|бургер|торт|десерт|тістеч|печив|круасан|снідан|"
    r"омлет|тост|салат|суп|пиріг|сирник|вафл|пончик|ролл|запікан|солодощ|"
    r"морозив|батончик|шоколад|жуйк|food|snack",
    re.I,
)
# Категорії Poster важливіші за назву позиції (добавки/атракціони — other)
_CAT_DRINK_RE = re.compile(
    r"напої|кав|лимонад|смузі|мілкшейк|какао|матча|ча[їи]|раф|глясе|еспресо|"
    r"американо|капуч|лат|флет|мока|бабл|пунш|холодна\s*кав|зимов(і|е)\s*напо",
    re.I,
)
_CAT_FOOD_RE = re.compile(r"їжа|солодощ|морозив|снідан", re.I)
_CAT_OTHER_RE = re.compile(r"добавк|молоко|атракціон|бариста", re.I)


def _cycle_id_for_user(user: dict) -> str:
    """Один 14-денний цикл від реєстрації / join_date (без автоповтору D581)."""
    raw = (user.get("join_date") or user.get("last_activity") or "")[:10]
    if not raw or len(raw) < 10:
        raw = now_kyiv().strftime("%Y-%m-%d")
    return f"c-{raw}"


def _cycle_bounds(cycle_id: str) -> tuple[datetime, datetime]:
    day = cycle_id.replace("c-", "")[:10]
    try:
        start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KYIV_TZ)
    except ValueError:
        start = now_kyiv().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=get_quest_window_days())
    return start, end


def _ensure_cycle_quests(user_id: int, user: dict) -> str:
    cycle_id = _cycle_id_for_user(user)
    start, _ = _cycle_bounds(cycle_id)
    started = start.strftime("%Y-%m-%d %H:%M:%S")
    specs = [
        (qdb.QUEST_VISITS, 3.0, get_quest_visits_reward_uah()),
        (qdb.QUEST_COMBO, 1.0, get_quest_combo_reward_uah()),
        (qdb.QUEST_DRINKS, 2.0, get_quest_drinks_reward_uah()),
    ]
    for key, target, reward in specs:
        if qdb.get_progress(user_id, key, cycle_id) is None:
            qdb.upsert_progress(
                user_id,
                key,
                cycle_id,
                progress=0,
                target=target,
                reward_uah=reward,
                meta={},
                started_at=started,
            )
    if qdb.get_progress(user_id, qdb.ACH_FIRST, "permanent") is None:
        qdb.upsert_progress(
            user_id,
            qdb.ACH_FIRST,
            "permanent",
            progress=0,
            target=1,
            reward_uah=0,
            meta={},
        )
    if qdb.get_progress(user_id, qdb.ACH_DAYS, "permanent") is None:
        qdb.upsert_progress(
            user_id,
            qdb.ACH_DAYS,
            "permanent",
            progress=0,
            target=float(DAYS_STEPS[-1]),
            reward_uah=0,
            meta={"days": [], "claimed_steps": []},
        )
    return cycle_id


def classify_product(product: dict | None, category: dict | None = None) -> str:
    """Повертає drink | food | other."""
    cat = ((category or {}).get("category_name") or (category or {}).get("name") or "").strip()
    if cat and _CAT_OTHER_RE.search(cat):
        return "other"
    if cat and _CAT_DRINK_RE.search(cat):
        return "drink"
    if cat and _CAT_FOOD_RE.search(cat):
        return "food"

    name = ((product or {}).get("product_name") or "").strip()
    blob = f"{name} {cat}".strip()
    if _DRINK_RE.search(blob):
        return "drink"
    if _FOOD_RE.search(blob):
        return "food"
    return "other"


def _tx_items(tx: dict) -> list[dict]:
    """[{product_id, name, kind, base_key}]"""
    products_map = {str(p.get("product_id")): p for p in (poster.get_products() or [])}
    cats_map = {str(c.get("category_id")): c for c in (poster.get_categories() or [])}
    items = []
    for row in tx.get("products") or []:
        pid = str(row.get("product_id") or "")
        if not pid:
            continue
        p = products_map.get(pid) or {}
        cat = cats_map.get(str(p.get("menu_category_id") or p.get("category_id") or ""))
        kind = classify_product(p, cat)
        name = (p.get("product_name") or pid).strip()
        # базова позиція напою: без об'єму / молока (груба нормалізація)
        base = re.sub(r"\d+\s*(мл|ml|л|g|гр)?", "", name, flags=re.I)
        base = re.sub(r"\s+", " ", base).strip().lower()
        items.append({"product_id": pid, "name": name, "kind": kind, "base_key": base or pid})
    return items


def _pay_reward(user: dict, amount: float, *, note: str) -> float:
    if amount <= 0:
        return 0.0
    cid = user.get("poster_client_id")
    if not cid:
        return 0.0
    try:
        poster.change_client_bonus(int(cid), amount)
        invalidate_client(int(cid))
        log.info("quest reward user=%s +%s (%s)", user.get("user_id"), amount, note)
        return amount
    except Exception as exc:
        log.warning("quest reward failed user=%s: %s", user.get("user_id"), exc)
        return 0.0


def _days_reward_for_step(step: int) -> float:
    if step == 5:
        return get_ach_days_5_reward_uah()
    if step == 15:
        return get_ach_days_15_reward_uah()
    if step == 30:
        return get_ach_days_30_reward_uah()
    return 0.0


def on_purchase_for_quests(
    telegram_user_id: int,
    tx: dict,
    *,
    closed_at: datetime | None = None,
) -> list[dict]:
    """
    Оновити прогрес квестів після закритого чека.
    Повертає список подій {quest_key, title, reward_uah, completed}.
    """
    user = get_user(telegram_user_id)
    if not user or not user.get("registered"):
        return []

    tid = str(tx.get("transaction_id") or tx.get("id") or "")
    at = closed_at or parse_purchase_datetime(str(tx.get("date_close_date") or "")) or now_kyiv()
    if at.tzinfo is None:
        at = at.replace(tzinfo=KYIV_TZ)

    cycle_id = _ensure_cycle_quests(int(telegram_user_id), user)
    start, end = _cycle_bounds(cycle_id)
    in_cycle = start <= at < end
    items = _tx_items(tx)
    events: list[dict] = []
    uid = int(telegram_user_id)

    # --- постійне: перша покупка ---
    first = qdb.get_progress(uid, qdb.ACH_FIRST, "permanent")
    if first and not first.get("completed"):
        qdb.upsert_progress(
            uid,
            qdb.ACH_FIRST,
            "permanent",
            progress=1,
            target=1,
            completed=True,
            reward_paid=True,
            reward_uah=0,
            completed_at=kyiv_now_str(),
            meta={"transaction_id": tid},
        )
        qdb.log_quest_event(uid, transaction_id=tid, quest_key=qdb.ACH_FIRST, note="first_purchase")
        events.append(
            {
                "quest_key": qdb.ACH_FIRST,
                "title": "Перша покупка",
                "reward_uah": 0,
                "completed": True,
                "symbolic": True,
            }
        )

    # --- постійне: дні з покупками ---
    days_row = qdb.get_progress(uid, qdb.ACH_DAYS, "permanent") or {}
    meta = dict(days_row.get("meta") or {})
    day_list = list(meta.get("days") or [])
    claimed = list(meta.get("claimed_steps") or [])
    day_key = at.strftime("%Y-%m-%d")
    if day_key not in day_list:
        day_list.append(day_key)
        day_list = sorted(set(day_list))
    progress_days = float(len(day_list))
    for step in DAYS_STEPS:
        if progress_days >= step and step not in claimed:
            reward = _days_reward_for_step(step)
            paid = _pay_reward(user, reward, note=f"days_{step}")
            claimed.append(step)
            events.append(
                {
                    "quest_key": qdb.ACH_DAYS,
                    "title": f"Досягнення: {step} днів із покупками",
                    "reward_uah": paid,
                    "completed": True,
                    "step": step,
                }
            )
    qdb.upsert_progress(
        uid,
        qdb.ACH_DAYS,
        "permanent",
        progress=progress_days,
        target=float(DAYS_STEPS[-1]),
        completed=progress_days >= DAYS_STEPS[-1],
        reward_paid=bool(claimed),
        meta={"days": day_list, "claimed_steps": claimed},
        completed_at=kyiv_now_str() if progress_days >= DAYS_STEPS[-1] else None,
    )

    if not in_cycle:
        return events

    # --- visits ---
    visits = qdb.get_progress(uid, qdb.QUEST_VISITS, cycle_id)
    if visits and not visits.get("completed") and not qdb.has_event_for_tx(uid, tid, qdb.QUEST_VISITS):
        vmeta = dict(visits.get("meta") or {})
        stamps = list(vmeta.get("visits") or [])
        last = stamps[-1] if stamps else None
        ok = True
        if last:
            try:
                last_dt = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KYIV_TZ)
                if (at - last_dt).total_seconds() < MIN_VISIT_GAP_HOURS * 3600:
                    ok = False
            except ValueError:
                pass
        if ok:
            stamps.append(at.strftime("%Y-%m-%d %H:%M:%S"))
            prog = float(len(stamps))
            target = float(visits.get("target") or 3)
            done = prog >= target
            reward = get_quest_visits_reward_uah() if done else 0.0
            paid = 0.0
            if done:
                paid = _pay_reward(user, reward, note="quest_visits")
            qdb.upsert_progress(
                uid,
                qdb.QUEST_VISITS,
                cycle_id,
                progress=min(prog, target),
                target=target,
                completed=done,
                reward_paid=done,
                reward_uah=paid if done else reward,
                meta={"visits": stamps},
                completed_at=kyiv_now_str() if done else None,
            )
            qdb.log_quest_event(uid, transaction_id=tid, quest_key=qdb.QUEST_VISITS, note="visit")
            if done:
                events.append(
                    {
                        "quest_key": qdb.QUEST_VISITS,
                        "title": "Квест: 3 візити",
                        "reward_uah": paid,
                        "completed": True,
                    }
                )

    # --- drinks ---
    drinks = qdb.get_progress(uid, qdb.QUEST_DRINKS, cycle_id)
    if drinks and not drinks.get("completed"):
        dmeta = dict(drinks.get("meta") or {})
        bases = set(dmeta.get("bases") or [])
        for it in items:
            if it["kind"] == "drink" and it["base_key"]:
                bases.add(it["base_key"])
        prog = float(len(bases))
        target = float(drinks.get("target") or 2)
        done = prog >= target
        reward = get_quest_drinks_reward_uah() if done else 0.0
        paid = 0.0
        already = bool(drinks.get("reward_paid"))
        if done and not already:
            paid = _pay_reward(user, reward, note="quest_drinks")
        qdb.upsert_progress(
            uid,
            qdb.QUEST_DRINKS,
            cycle_id,
            progress=min(prog, target),
            target=target,
            completed=done,
            reward_paid=done or already,
            reward_uah=paid if paid else float(drinks.get("reward_uah") or reward),
            meta={"bases": sorted(bases)},
            completed_at=kyiv_now_str() if done else None,
        )
        if done and paid:
            qdb.log_quest_event(uid, transaction_id=tid, quest_key=qdb.QUEST_DRINKS, note="drinks_done")
            events.append(
                {
                    "quest_key": qdb.QUEST_DRINKS,
                    "title": "Квест: 2 різні напої",
                    "reward_uah": paid,
                    "completed": True,
                }
            )

    # --- combo drink+food ---
    combo = qdb.get_progress(uid, qdb.QUEST_COMBO, cycle_id)
    if combo and not combo.get("completed"):
        cmeta = dict(combo.get("meta") or {})
        pending = list(cmeta.get("pending") or [])  # {kind, at}
        has_drink = any(it["kind"] == "drink" for it in items)
        has_food = any(it["kind"] == "food" for it in items)
        stamp = at.strftime("%Y-%m-%d %H:%M:%S")
        if has_drink and has_food:
            done = True
        else:
            if has_drink:
                pending.append({"kind": "drink", "at": stamp})
            if has_food:
                pending.append({"kind": "food", "at": stamp})
            # trim old > 2h
            fresh = []
            for p in pending:
                try:
                    pdt = datetime.strptime(p["at"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KYIV_TZ)
                except (ValueError, KeyError):
                    continue
                if abs((at - pdt).total_seconds()) <= MIN_VISIT_GAP_HOURS * 3600:
                    fresh.append(p)
            pending = fresh
            kinds = {p["kind"] for p in pending}
            done = "drink" in kinds and "food" in kinds

        if done:
            reward = get_quest_combo_reward_uah()
            paid = _pay_reward(user, reward, note="quest_combo")
            qdb.upsert_progress(
                uid,
                qdb.QUEST_COMBO,
                cycle_id,
                progress=1,
                target=1,
                completed=True,
                reward_paid=True,
                reward_uah=paid,
                meta={"pending": []},
                completed_at=kyiv_now_str(),
            )
            qdb.log_quest_event(uid, transaction_id=tid, quest_key=qdb.QUEST_COMBO, note="combo_done")
            events.append(
                {
                    "quest_key": qdb.QUEST_COMBO,
                    "title": "Квест: напій + їжа",
                    "reward_uah": paid,
                    "completed": True,
                }
            )
        else:
            qdb.upsert_progress(
                uid,
                qdb.QUEST_COMBO,
                cycle_id,
                progress=0.5 if pending else 0,
                target=1,
                completed=False,
                meta={"pending": pending},
            )

    return events


def build_quests_ui(user_id: int) -> dict:
    """Дані для мініапу + сумісність зі старим quests_payload."""
    from services.referrals import referral_ui_payload

    user = get_user(user_id) or {}
    if user.get("registered"):
        cycle_id = _ensure_cycle_quests(int(user_id), user)
    else:
        cycle_id = ""

    start, end = _cycle_bounds(cycle_id) if cycle_id else (None, None)
    now = now_kyiv()
    rows = qdb.list_progress_for_user(int(user_id)) if user.get("registered") else []

    def _row(key: str, cycle: str) -> dict | None:
        for r in rows:
            if r["quest_key"] == key and r["cycle_id"] == cycle:
                return r
        return None

    active = []
    done = []

    def push_quest(key: str, title: str, hint: str, cycle: str, reward_fn):
        r = _row(key, cycle)
        if not r:
            return
        expired = bool(end and now >= end and not r.get("completed"))
        item = {
            "key": key,
            "title": title,
            "hint": hint,
            "progress": float(r.get("progress") or 0),
            "target": float(r.get("target") or 1),
            "reward_uah": float(r.get("reward_uah") or reward_fn()),
            "completed": bool(r.get("completed")),
            "expired": expired,
            "cycle_id": cycle,
        }
        if item["completed"]:
            done.append(item)
        elif not expired:
            active.append(item)
        else:
            done.append({**item, "hint": "Строк минув — квест не виконано"})

    if cycle_id:
        push_quest(
            qdb.QUEST_VISITS,
            "Зроби 3 візити",
            f"3 зараховані візити за {get_quest_window_days()} днів (мін. 2 год між ними)",
            cycle_id,
            get_quest_visits_reward_uah,
        )
        push_quest(
            qdb.QUEST_COMBO,
            "Напій + їжа",
            "Купи напій і їжу разом або з інтервалом до 2 годин",
            cycle_id,
            get_quest_combo_reward_uah,
        )
        push_quest(
            qdb.QUEST_DRINKS,
            "2 різні напої",
            "Дві різні базові позиції напоїв за період квесту",
            cycle_id,
            get_quest_drinks_reward_uah,
        )

    first = _row(qdb.ACH_FIRST, "permanent")
    if first:
        item = {
            "key": qdb.ACH_FIRST,
            "title": "Перша покупка",
            "hint": "Символічна відзнака за першу покупку з карткою",
            "progress": float(first.get("progress") or 0),
            "target": 1,
            "reward_uah": 0,
            "completed": bool(first.get("completed")),
            "symbolic": True,
        }
        (done if item["completed"] else active).append(item)

    days = _row(qdb.ACH_DAYS, "permanent")
    if days:
        claimed = list((days.get("meta") or {}).get("claimed_steps") or [])
        prog = float(days.get("progress") or 0)
        next_step = next((s for s in DAYS_STEPS if s not in claimed), None)
        item = {
            "key": qdb.ACH_DAYS,
            "title": "Дні з покупками",
            "hint": f"Сходинки 5 → 15 → 30 різних днів. Зараз: {int(prog)}"
            + (f" · наступна: {next_step}" if next_step else " · усі сходинки виконано"),
            "progress": prog,
            "target": float(DAYS_STEPS[-1]),
            "reward_uah": _days_reward_for_step(next_step) if next_step else 0,
            "completed": prog >= DAYS_STEPS[-1] and set(DAYS_STEPS).issubset(set(claimed)),
            "claimed_steps": claimed,
        }
        if item["completed"]:
            done.append(item)
        else:
            active.append(item)
            for s in claimed:
                done.append(
                    {
                        "key": f"days_{s}",
                        "title": f"Досягнення: {s} днів",
                        "hint": "Виконано",
                        "progress": s,
                        "target": s,
                        "reward_uah": _days_reward_for_step(s),
                        "completed": True,
                    }
                )

    birthday = user.get("birthday")
    has_bday = bool(birthday and birthday != "0000-00-00")
    ref_ui = referral_ui_payload(int(user_id))

    return {
        "birthday_bonus_uah": get_birthday_bonus_uah(),
        "birthday_filled": has_bday,
        "birthday_bonus_claimed": bool(user.get("birthday_bonus_given")),
        **ref_ui,
        "cycle_id": cycle_id,
        "cycle_ends": end.strftime("%Y-%m-%d") if end else None,
        "active": active,
        "done": done,
        "rewards": rewards_snapshot(),
    }
