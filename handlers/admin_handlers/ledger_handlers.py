"""Admin: centralized Craftyki operations journal (factual bonus_ledger)."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

from keyboards.admin_keyboards import (
    get_ledger_hub_keyboard,
    get_ledger_list_keyboard,
    get_ledger_op_keyboard,
    get_ledger_reasons_keyboard,
)
from utils.filters import IsAdmin
from utils.kyiv_time import format_dt_ua

log = logging.getLogger(__name__)
router = Router()


def _esc(s: object) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _uah(n: float) -> str:
    v = float(n or 0)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):+d}" if v != 0 else "0"
    s = f"{v:+.2f}".rstrip("0").rstrip(".")
    return s


def _hub_text_sync() -> str:
    from database_functions.bonus_ledger_db import summary_admin

    s = summary_admin()
    return (
        "📒 <b>Журнал Крафтиків</b>\n\n"
        "Фактичні нарахування й списання з ledger — "
        "суми не перераховуються від поточних налаштувань.\n\n"
        f"Усього записів: <b>{s['total_ops']}</b>\n"
        f"Проведено: <b>{s['posted']}</b> · "
        f"в процесі: <b>{s['incomplete']}</b> · "
        f"помилок: <b>{s['failed']}</b>\n"
        f"Нараховано (posted): <b>+{_uah(s['credited_uah']).lstrip('+')}</b> К\n"
        f"Списано (posted): <b>{_uah(s['debited_uah'])}</b> К\n"
        f"З відміткою адміна: <b>{s['admin_ops']}</b>\n\n"
        "<i>Картки й баланси не змінюються цим екраном — лише перегляд історії.</i>"
    )


def _client_label(uid: object, users: dict[int, dict] | None = None) -> str:
    from database_functions.anomalies_db import user_name_link

    if uid is None:
        return "—"
    try:
        iuid = int(uid)
    except (TypeError, ValueError):
        return _esc(uid)
    u = (users or {}).get(iuid) or {}
    name = (
        u.get("display_name")
        or u.get("user_first_name")
        or (f"@{u['user_name']}" if u.get("user_name") else None)
        or str(iuid)
    )
    return user_name_link(iuid, name, u.get("user_name"))


def _purchase_line(row: dict, purchases: dict[str, dict] | None = None) -> str:
    """One-line purchase context for cashback/spend ops."""
    from database_functions.bonus_ledger_db import (
        REASON_CASHBACK,
        REASON_SPEND,
        purchase_items_summary,
    )

    reason = str(row.get("reason") or "")
    if reason not in (REASON_CASHBACK, REASON_SPEND):
        return ""
    tid = str(row.get("ref_id") or "")
    if not tid:
        return ""
    tx = (purchases or {}).get(tid)
    if not tx:
        return f"  чек <code>{_esc(tid)}</code>"
    items = purchase_items_summary(tx.get("products_json"), max_items=4)
    spot = (tx.get("spot_name") or "").strip()
    try:
        payed = float(tx.get("payed_sum_uah") or 0)
    except (TypeError, ValueError):
        payed = 0.0
    bits: list[str] = []
    if items:
        bits.append(_esc(items))
    if spot:
        bits.append(_esc(spot))
    if payed:
        bits.append(f"{payed:g} грн")
    if not bits:
        return f"  чек <code>{_esc(tid)}</code>"
    return "  🛒 " + " · ".join(bits)


def _format_op_line(
    row: dict,
    *,
    users: dict[int, dict] | None = None,
    purchases: dict[str, dict] | None = None,
) -> str:
    from database_functions.bonus_ledger_db import STATUS_LABELS_UK, history_title

    amt = float(row.get("amount_uah") or 0)
    when = format_dt_ua(row.get("posted_at") or row.get("created_at"))
    st = STATUS_LABELS_UK.get(str(row.get("status") or ""), row.get("status") or "?")
    title = history_title(row)
    if len(title) > 36:
        title = title[:35] + "…"
    lines = [
        f"• <code>#{row.get('id')}</code> {_esc(when)} · "
        f"<b>{_uah(amt)}</b> · {_esc(title)}",
        f"  {_client_label(row.get('user_id'), users)} · {_esc(st)}",
    ]
    buy = _purchase_line(row, purchases)
    if buy:
        lines.append(buy)
    return "\n".join(lines)


def _format_op_detail(row: dict) -> str:
    from database_functions.bonus_ledger_db import (
        REASON_CASHBACK,
        REASON_SPEND,
        STATUS_LABELS_UK,
        fetch_purchases_by_tx_ids,
        fetch_users_brief,
        history_title,
        purchase_items_summary,
    )
    import json

    amt = float(row.get("amount_uah") or 0)
    st = STATUS_LABELS_UK.get(str(row.get("status") or ""), row.get("status") or "?")
    uid = row.get("user_id")
    users = fetch_users_brief([int(uid)] if uid else [])
    u = users.get(int(uid)) if uid else None
    phone = ((u or {}).get("user_phone") or "").strip()

    lines = [
        f"📒 <b>Операція #{row.get('id')}</b>",
        f"<b>{_esc(history_title(row))}</b>",
        "",
        f"Сума: <b>{_uah(amt)}</b> Крафтиків",
        f"Статус: <b>{_esc(st)}</b>",
        f"Причина: <code>{_esc(row.get('reason'))}</code>",
        f"op_key: <code>{_esc(row.get('op_key'))}</code>",
        "",
        f"Клієнт: {_client_label(uid, users)}",
    ]
    if uid:
        lines.append(f"Telegram ID: <code>{uid}</code>")
    if phone:
        lines.append(f"Телефон: <code>{_esc(phone)}</code>")
    if row.get("poster_client_id"):
        lines.append(f"Poster ID: <code>{row['poster_client_id']}</code>")
    if row.get("admin_user_id"):
        lines.append(f"Адмін (ручне): <code>{row['admin_user_id']}</code>")

    reason = str(row.get("reason") or "")
    tid = str(row.get("ref_id") or "")
    if reason in (REASON_CASHBACK, REASON_SPEND) and tid:
        tx = fetch_purchases_by_tx_ids([tid]).get(tid)
        lines.append("")
        lines.append(f"<b>Покупка</b> · чек <code>{_esc(tid)}</code>")
        if tx:
            spot = (tx.get("spot_name") or "").strip()
            if spot:
                lines.append(f"Кавʼярня: {_esc(spot)}")
            try:
                payed = float(tx.get("payed_sum_uah") or 0)
            except (TypeError, ValueError):
                payed = 0.0
            if payed:
                lines.append(f"Сума чека: <b>{payed:g}</b> грн")
            try:
                items = json.loads(tx.get("products_json") or "[]")
            except Exception:
                items = []
            if items:
                lines.append("Позиції:")
                for it in items[:12]:
                    if not isinstance(it, dict):
                        continue
                    name = _esc(it.get("name") or "Товар")
                    try:
                        qty = float(it.get("count") or 1)
                    except (TypeError, ValueError):
                        qty = 1
                    qty_s = f"{qty:g}× " if qty > 1 else ""
                    lines.append(f"  · {qty_s}{name}")
            else:
                summary = purchase_items_summary(tx.get("products_json"))
                if summary:
                    lines.append(_esc(summary))
        else:
            lines.append("<i>Чек ще не в локальній БД</i>")

    if row.get("balance_before") is not None:
        lines.append(f"Баланс до: {_uah(float(row['balance_before'])).lstrip('+')}")
    if row.get("balance_after") is not None:
        lines.append(f"Баланс після: {_uah(float(row['balance_after'])).lstrip('+')}")
    lines.append(f"Створено: {_esc(format_dt_ua(row.get('created_at')))}")
    if row.get("posted_at"):
        lines.append(f"Проведено: {_esc(format_dt_ua(row.get('posted_at')))}")
    if row.get("error"):
        lines.append(f"⚠️ Помилка: {_esc(row.get('error'))}")
    return "\n".join(lines)


def _enrich_page(rows: list[dict]) -> tuple[dict[int, dict], dict[str, dict]]:
    from database_functions.bonus_ledger_db import (
        REASON_CASHBACK,
        REASON_SPEND,
        fetch_purchases_by_tx_ids,
        fetch_users_brief,
    )

    uids = [int(r["user_id"]) for r in rows if r.get("user_id") is not None]
    tx_ids = [
        str(r["ref_id"])
        for r in rows
        if r.get("ref_id")
        and str(r.get("reason") or "") in (REASON_CASHBACK, REASON_SPEND)
    ]
    return fetch_users_brief(uids), fetch_purchases_by_tx_ids(tx_ids)


async def _edit_or_send(
    target: types.Message,
    text: str,
    kb,
    *,
    replace: bool = True,
) -> None:
    if replace:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(IsAdmin(), F.text == "📒 Журнал Крафтиків")
async def ledger_hub_msg(message: types.Message, state: FSMContext):
    await state.clear()
    text = await asyncio.to_thread(_hub_text_sync)
    await message.answer(
        text, parse_mode="HTML", reply_markup=get_ledger_hub_keyboard()
    )


@router.callback_query(IsAdmin(), F.data == "ledger_hub")
async def ledger_hub_cb(callback: types.CallbackQuery):
    text = await asyncio.to_thread(_hub_text_sync)
    await _edit_or_send(callback.message, text, get_ledger_hub_keyboard())
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "ledger_noop")
async def ledger_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "ledger_reasons")
async def ledger_reasons(callback: types.CallbackQuery):
    await _edit_or_send(
        callback.message,
        "🏷 <b>Фільтр журналу за типом операції</b>\n"
        "Показуються фактичні записи ledger.",
        get_ledger_reasons_keyboard(),
    )
    await callback.answer()


async def _render_list(
    callback: types.CallbackQuery,
    *,
    offset: int,
    reason: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    admin_only: bool = False,
    title: str,
    prefix: str,
) -> None:
    from database_functions.bonus_ledger_db import PAGE_SIZE, list_admin

    rows, total = await asyncio.to_thread(
        lambda: list_admin(
            offset=offset,
            limit=PAGE_SIZE,
            reason=reason,
            status=status,
            user_id=user_id,
            admin_only=admin_only,
        )
    )
    if not rows and total == 0:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        await callback.answer("Записів немає")
        text = (
            f"{title}\n\nПоки немає операцій у журналі.\n"
            "<i>Якщо в історії покупок є чеки — вони мали підтягнутись автоматично. "
            "Перевір «Історію покупок» у картці клієнта.</i>"
        )
        kb_rows: list[list[InlineKeyboardButton]] = []
        if user_id is not None:
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        text="◀️ До картки",
                        callback_data=f"client_view:{int(user_id)}",
                    )
                ]
            )
            kb_rows.append(
                [InlineKeyboardButton(text="🏠 Меню клієнтів", callback_data="clients_hub")]
            )
        else:
            kb_rows.append(
                [InlineKeyboardButton(text="◀️ Назад", callback_data="ledger_hub")]
            )
        kb_rows.append(
            [InlineKeyboardButton(text="🏠 Журнал", callback_data="ledger_hub")]
        )
        await _edit_or_send(
            callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb_rows)
        )
        return

    users, purchases = await asyncio.to_thread(_enrich_page, rows)
    lines = [
        f"{title}",
        f"Всього: <b>{total}</b> · стор. {(offset // PAGE_SIZE) + 1}",
        "",
    ]
    for row in rows:
        lines.append(_format_op_line(row, users=users, purchases=purchases))
        lines.append("")
    # Inline buttons per op (max ~8 to keep keyboard small)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    back_cb = f"client_view:{int(user_id)}" if user_id is not None else "ledger_hub"
    back_label = "◀️ До картки" if user_id is not None else "◀️ Назад"
    base_kb = get_ledger_list_keyboard(
        offset=offset,
        total=total,
        page_size=PAGE_SIZE,
        prefix=prefix,
        back_cb=back_cb,
        back_label=back_label,
    )
    view_suffix = ":c" if user_id is not None else ""
    op_rows: list[list[InlineKeyboardButton]] = []
    for row in rows[:8]:
        amt = float(row.get("amount_uah") or 0)
        op_rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{row['id']} {_uah(amt)}",
                    callback_data=f"ledger_view:{row['id']}{view_suffix}",
                )
            ]
        )
    kb = InlineKeyboardMarkup(inline_keyboard=op_rows + list(base_kb.inline_keyboard))
    text = "\n".join(lines).rstrip()
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    await _edit_or_send(callback.message, text, kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("ledger_list:"))
async def ledger_list(callback: types.CallbackQuery):
    try:
        offset = int((callback.data or "").split(":")[-1])
    except ValueError:
        offset = 0
    await _render_list(
        callback,
        offset=offset,
        title="📋 <b>Останні операції</b>",
        prefix="ledger_list",
    )


@router.callback_query(IsAdmin(), F.data.startswith("ledger_admin:"))
async def ledger_admin_only(callback: types.CallbackQuery):
    try:
        offset = int((callback.data or "").split(":")[-1])
    except ValueError:
        offset = 0
    await _render_list(
        callback,
        offset=offset,
        admin_only=True,
        title="🎁 <b>Ручні операції адмінів</b>",
        prefix="ledger_admin",
    )


@router.callback_query(IsAdmin(), F.data.startswith("ledger_bad:"))
async def ledger_bad(callback: types.CallbackQuery):
    """Incomplete + failed — show as two-step: failed first page via status filter rotation.
    Simpler: list without posted filter using custom query in list_admin for statuses.
    """
    from database_functions.bonus_ledger_db import (
        PAGE_SIZE,
        STATUS_FAILED,
        STATUS_PENDING,
        STATUS_SUBMITTED,
    )

    try:
        offset = int((callback.data or "").split(":")[-1])
    except ValueError:
        offset = 0

    # Fetch pending/submitted/failed by three queries merge — keep simple: failed + then incomplete
    # Use SQL via list_admin status=None and filter in Python is bad for pagination.
    # Add a dedicated helper call: list with status in (...)
    def _load():
        from database_functions.bonus_ledger_db import cursor

        rows = cursor.execute(
            """
            SELECT * FROM bonus_ledger
            WHERE status IN (?, ?, ?)
            ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (STATUS_PENDING, STATUS_SUBMITTED, STATUS_FAILED, PAGE_SIZE, offset),
        ).fetchall()
        total = int(
            cursor.execute(
                """
                SELECT COUNT(*) FROM bonus_ledger
                WHERE status IN (?, ?, ?)
                """,
                (STATUS_PENDING, STATUS_SUBMITTED, STATUS_FAILED),
            ).fetchone()[0]
            or 0
        )
        return [dict(r) for r in rows], total

    rows, total = await asyncio.to_thread(_load)
    if not rows and total == 0:
        await callback.answer("Немає проблемних записів", show_alert=True)
        return

    users, purchases = await asyncio.to_thread(_enrich_page, rows)
    lines = [
        "⚠️ <b>Незавершені / помилки</b>",
        f"Всього: <b>{total}</b>",
        "",
    ]
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    op_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        lines.append(_format_op_line(row, users=users, purchases=purchases))
        lines.append("")
        op_rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{row['id']}",
                    callback_data=f"ledger_view:{row['id']}",
                )
            ]
        )
    base_kb = get_ledger_list_keyboard(
        offset=offset,
        total=total,
        page_size=PAGE_SIZE,
        prefix="ledger_bad",
        back_cb="ledger_hub",
        back_label="◀️ Назад",
    )
    kb = InlineKeyboardMarkup(inline_keyboard=op_rows + list(base_kb.inline_keyboard))
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    await _edit_or_send(callback.message, text, kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("ledger_reason:"))
async def ledger_by_reason(callback: types.CallbackQuery):
    from database_functions.bonus_ledger_db import REASON_TITLES_UK

    parts = (callback.data or "").split(":")
    # ledger_reason:cashback:0
    reason = parts[1] if len(parts) > 1 else ""
    try:
        offset = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        offset = 0
    title = REASON_TITLES_UK.get(reason, reason)
    await _render_list(
        callback,
        offset=offset,
        reason=reason,
        title=f"🏷 <b>{_esc(title)}</b>",
        prefix=f"ledger_reason:{reason}",
    )


@router.callback_query(IsAdmin(), F.data.startswith("ledger_user:"))
async def ledger_by_user(callback: types.CallbackQuery):
    parts = (callback.data or "").split(":")
    try:
        uid = int(parts[1])
        offset = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        await callback.answer("Помилка", show_alert=True)
        return
    # Старі чеки жили лише в processed_transactions — підтягуємо в journal.
    if offset == 0:
        try:
            from database_functions.bonus_ledger_db import backfill_user_ledger

            added = await asyncio.to_thread(backfill_user_ledger, uid)
            n = sum(added.values()) if isinstance(added, dict) else 0
            if n:
                log.info("ledger backfill user=%s added=%s", uid, added)
        except Exception as exc:
            log.warning("ledger backfill user=%s failed: %s", uid, exc)
    await _render_list(
        callback,
        offset=offset,
        user_id=uid,
        title=f"📒 <b>Операції клієнта</b> <code>{uid}</code>",
        prefix=f"ledger_user:{uid}",
    )


@router.callback_query(IsAdmin(), F.data.startswith("ledger_view:"))
async def ledger_view(callback: types.CallbackQuery):
    from database_functions.bonus_ledger_db import get_by_id

    parts = (callback.data or "").split(":")
    # ledger_view:123 or ledger_view:123:c (з картки клієнта)
    try:
        op_id = int(parts[1])
    except (ValueError, IndexError):
        await callback.answer("Невірний id", show_alert=True)
        return
    from_client = len(parts) > 2 and parts[2] == "c"
    row = await asyncio.to_thread(get_by_id, op_id)
    if not row:
        await callback.answer("Не знайдено", show_alert=True)
        return
    uid = int(row["user_id"]) if row.get("user_id") else None
    text = await asyncio.to_thread(_format_op_detail, row)
    await _edit_or_send(
        callback.message,
        text,
        get_ledger_op_keyboard(op_id, uid, from_client=from_client),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "ledger_export")
async def ledger_export(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "📊 Формую Excel з журналу Крафтиків (фактичні операції)…"
    )

    def _build() -> tuple[str, int]:
        import pandas as pd

        from database_functions.bonus_ledger_db import (
            STATUS_LABELS_UK,
            history_title,
            iter_for_export,
        )
        from database_functions.client_db import get_user
        from utils.admin_functions import style_excel_sheet

        rows = iter_for_export(limit=20000)
        export = []
        for r in rows:
            uid = r.get("user_id")
            name = ""
            phone = ""
            if uid:
                u = get_user(int(uid))
                if u:
                    name = (
                        u.get("display_name")
                        or u.get("user_first_name")
                        or ""
                    )
                    phone = u.get("user_phone") or ""
            export.append(
                {
                    "ID": r.get("id"),
                    "Дата створення": format_dt_ua(r.get("created_at"), empty=""),
                    "Дата проведення": format_dt_ua(r.get("posted_at"), empty=""),
                    "Сума Крафтиків": round(float(r.get("amount_uah") or 0), 2),
                    "Назва": history_title(r),
                    "Причина": r.get("reason") or "",
                    "Статус": STATUS_LABELS_UK.get(
                        str(r.get("status") or ""), r.get("status") or ""
                    ),
                    "op_key": r.get("op_key") or "",
                    "Telegram ID": uid or "",
                    "Імʼя": name,
                    "Телефон": phone,
                    "Poster client_id": r.get("poster_client_id") or "",
                    "Адмін ID": r.get("admin_user_id") or "",
                    "Баланс до": r.get("balance_before")
                    if r.get("balance_before") is not None
                    else "",
                    "Баланс після": r.get("balance_after")
                    if r.get("balance_after") is not None
                    else "",
                    "Помилка": r.get("error") or "",
                    "ref_type": r.get("ref_type") or "",
                    "ref_id": r.get("ref_id") or "",
                }
            )
        df = pd.DataFrame(export)
        stamp = datetime.now().strftime("%d.%m.%Y_%H-%M")
        filename = f"craftyki_ledger_{stamp}.xlsx"
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Журнал", index=False)
            ws = writer.sheets["Журнал"]
            widths = {
                "A": 8,
                "B": 18,
                "C": 18,
                "D": 12,
                "E": 28,
                "F": 14,
                "G": 12,
                "H": 22,
                "I": 14,
                "J": 18,
                "K": 14,
                "L": 14,
                "M": 12,
                "N": 12,
                "O": 12,
                "P": 24,
                "Q": 12,
                "R": 16,
            }
            for col, width in widths.items():
                ws.column_dimensions[col].width = width
            style_excel_sheet(
                ws,
                header_color="35221A",
                column_group_colors={
                    (1, 3): "35221A",   # id / дати
                    (4, 8): "5C4033",   # сума / тип
                    (9, 12): "3D5A80",  # клієнт
                    (13, 15): "3D5A40",  # баланси
                    (16, 18): "6B5344",  # службові
                },
            )
        return filename, len(export)

    try:
        filename, count = await asyncio.to_thread(_build)
    except Exception as exc:
        log.exception("ledger excel")
        await callback.message.answer(f"Не вдалося сформувати Excel: {_esc(exc)}")
        return

    try:
        await callback.message.answer_document(
            FSInputFile(filename),
            caption=(
                f"📒 <b>Журнал Крафтиків</b>\n"
                f"Записів: <b>{count}</b>\n"
                f"<i>Фактичні суми з ledger, без перерахунку від налаштувань.</i>"
            ),
            parse_mode="HTML",
        )
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass
