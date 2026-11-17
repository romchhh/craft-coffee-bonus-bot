"""Background Poster balance sync → users.last_known_bonus.

Never blocks the bot event loop: HTTP runs in worker threads, cron ticks
are spaced out so admin/client handlers stay responsive.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    BALANCE_SYNC_BATCH,
    BALANCE_SYNC_ENABLED,
    BALANCE_SYNC_INTERVAL_SEC,
    BALANCE_SYNC_STALE_HOURS,
    getenv,
)

log = logging.getLogger(__name__)

BALANCE_SYNC_PAUSE_SEC = float(getenv("BALANCE_SYNC_PAUSE_SEC", "0.15") or "0.15")

_task: asyncio.Task | None = None
_stop: asyncio.Event | None = None
_full_lock = asyncio.Lock()
_manual_running = False

NotifyFn = Callable[[str], Awaitable[None]]


def _list_stale_clients(limit: int) -> list[tuple[int, int]]:
    from database_functions.db import get_connection
    from utils.kyiv_time import now_kyiv

    cutoff = now_kyiv().timestamp() - BALANCE_SYNC_STALE_HOURS * 3600
    cutoff_str = datetime.fromtimestamp(cutoff, tz=ZoneInfo("Europe/Kyiv")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows = get_connection().execute(
        """
        SELECT user_id, poster_client_id
        FROM users
        WHERE registered = 1
          AND poster_client_id IS NOT NULL
          AND (
            last_known_bonus IS NULL
            OR last_known_bonus_at IS NULL
            OR last_known_bonus_at = ''
            OR last_known_bonus_at < ?
          )
        ORDER BY
          CASE WHEN last_known_bonus IS NULL THEN 0 ELSE 1 END,
          COALESCE(last_known_bonus_at, '') ASC
        LIMIT ?
        """,
        (cutoff_str, int(limit)),
    ).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


def _refresh_one_sync(user_id: int, poster_client_id: int) -> float:
    from database_functions.client_db import set_last_known_bonus
    from services import poster

    bal = float(poster.get_client_bonus_uah(poster_client_id, timeout=5.0))
    set_last_known_bonus(user_id, bal)
    return bal


def sync_batch_sync(pairs: list[tuple[int, int]]) -> dict:
    """Blocking batch refresh. Call only from to_thread."""
    ok = 0
    errors = 0
    total = 0.0
    for uid, cid in pairs:
        try:
            total += _refresh_one_sync(uid, cid)
            ok += 1
        except Exception as exc:
            errors += 1
            log.debug("balance sync user=%s: %s", uid, exc)
        if BALANCE_SYNC_PAUSE_SEC > 0:
            time.sleep(BALANCE_SYNC_PAUSE_SEC)
    try:
        from database_functions import loyalty_stats_db as lsd

        lsd._summary_cache = None  # type: ignore[attr-defined]
        lsd._poster_bal_cache = None  # type: ignore[attr-defined]
    except Exception:
        pass
    return {"ok": ok, "errors": errors, "sum_uah": total, "n": len(pairs)}


def sync_all_sync() -> dict:
    from database_functions.db import get_connection

    rows = get_connection().execute(
        """
        SELECT user_id, poster_client_id FROM users
        WHERE registered = 1 AND poster_client_id IS NOT NULL
        """
    ).fetchall()
    pairs = [(int(r[0]), int(r[1])) for r in rows]
    report = sync_batch_sync(pairs)
    report["clients_total"] = len(pairs)
    return report


async def refresh_user_balance(user_id: int) -> float | None:
    from database_functions.client_db import get_user

    user = get_user(user_id)
    if not user or not user.get("poster_client_id"):
        return None
    cid = int(user["poster_client_id"])
    return await asyncio.to_thread(_refresh_one_sync, int(user_id), cid)


async def run_full_sync(*, notify: NotifyFn | None = None) -> dict:
    """Full sweep in a worker thread; optional HTML notify messages."""
    global _manual_running
    async with _full_lock:
        if _manual_running:
            if notify:
                await notify("♻️ Повне оновлення вже йде у фоні — зачекай.")
            return {"status": "busy"}
        _manual_running = True
    try:
        if notify:
            await notify(
                "♻️ Фонове оновлення балансів з Poster запущено.\n"
                "Адмінка й бот працюють як звичайно — результат прийде сюди."
            )
        report = await asyncio.to_thread(sync_all_sync)
        if notify:
            await notify(
                f"✅ Баланси оновлено у фоні.\n"
                f"Ок: <b>{report.get('ok', 0)}</b> · "
                f"помилок: <b>{report.get('errors', 0)}</b> · "
                f"клієнтів: <b>{report.get('clients_total', report.get('n', 0))}</b>"
            )
        return {"status": "ok", **report}
    except Exception as exc:
        log.exception("full balance sync failed")
        if notify:
            await notify(f"⚠️ Фонове оновлення балансів не вдалося: {exc}")
        return {"status": "error", "error": str(exc)}
    finally:
        _manual_running = False


async def _cron_loop() -> None:
    assert _stop is not None
    await asyncio.sleep(20)
    tick = 0
    while not _stop.is_set():
        tick += 1
        if not _manual_running:
            try:
                pairs = await asyncio.to_thread(_list_stale_clients, BALANCE_SYNC_BATCH)
                if pairs:
                    report = await asyncio.to_thread(sync_batch_sync, pairs)
                    log.info(
                        "balance sync tick #%s: ok=%s errors=%s batch=%s",
                        tick,
                        report.get("ok"),
                        report.get("errors"),
                        report.get("n"),
                    )
                else:
                    log.debug("balance sync tick #%s: nothing stale", tick)
            except Exception:
                log.exception("balance sync tick #%s failed", tick)
        try:
            await asyncio.wait_for(_stop.wait(), timeout=BALANCE_SYNC_INTERVAL_SEC)
            break
        except asyncio.TimeoutError:
            continue


def start_balance_sync() -> None:
    global _task, _stop
    if not BALANCE_SYNC_ENABLED:
        log.info("balance sync disabled (BALANCE_SYNC_ENABLED=0)")
        return
    if _task and not _task.done():
        return
    _stop = asyncio.Event()
    _task = asyncio.create_task(_cron_loop(), name="balance_sync")
    log.info(
        "balance sync started (every %ss, batch %s, stale %sh)",
        BALANCE_SYNC_INTERVAL_SEC,
        BALANCE_SYNC_BATCH,
        BALANCE_SYNC_STALE_HOURS,
    )


async def stop_balance_sync() -> None:
    global _task, _stop
    if _stop:
        _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    log.info("balance sync stopped")
