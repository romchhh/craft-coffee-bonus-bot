"""Daily SQLite backup and delivery to admin Telegram chats."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from aiogram.types import FSInputFile

from config import DB_PATH, PROJECT_ROOT
from utils.kyiv_time import KYIV_TZ, now_kyiv

log = logging.getLogger(__name__)

_cron_task: asyncio.Task | None = None
_cron_stop: asyncio.Event | None = None

BACKUP_DIR = PROJECT_ROOT / "database" / "backups"


def _backup_settings() -> tuple[bool, int, int, int]:
    from config import (
        BACKUP_ENABLED,
        BACKUP_HOUR_KYIV,
        BACKUP_KEEP_DAYS,
        BACKUP_MINUTE_KYIV,
    )

    return BACKUP_ENABLED, BACKUP_HOUR_KYIV, BACKUP_MINUTE_KYIV, BACKUP_KEEP_DAYS


def create_sqlite_backup() -> Path:
    """Online-safe copy via sqlite3 backup API → database/backups/."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_kyiv().strftime("%Y-%m-%d_%H-%M")
    dest = BACKUP_DIR / f"craft_loyalty_{stamp}.db"

    src = sqlite3.connect(str(DB_PATH))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()

    # Also copy -wal/-shm if present is unnecessary after backup API.
    return dest


def prune_old_backups(keep_days: int) -> int:
    if keep_days <= 0 or not BACKUP_DIR.exists():
        return 0
    cutoff = now_kyiv() - timedelta(days=keep_days)
    removed = 0
    for path in BACKUP_DIR.glob("craft_loyalty_*.db"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=KYIV_TZ)
            if mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError as exc:
            log.warning("backup prune %s: %s", path, exc)
    return removed


def admin_recipient_ids() -> list[int]:
    ids: set[int] = set()
    try:
        from config import administrators

        for x in administrators or []:
            ids.add(int(x))
    except Exception:
        pass
    try:
        from database_functions.admin_db import get_all_admin_ids

        for x in get_all_admin_ids() or []:
            ids.add(int(x))
    except Exception:
        pass
    return sorted(ids)


async def send_backup_to_admins(bot, *, reason: str = "щоденний") -> dict:
    """Create backup file and send to every admin DM. Returns status dict."""
    report: dict = {"ok": False, "path": None, "sent": [], "errors": []}
    try:
        path = await asyncio.to_thread(create_sqlite_backup)
        report["path"] = str(path)
    except Exception as exc:
        log.exception("backup create failed")
        report["errors"].append(f"create: {exc}")
        return report

    _, _, _, keep_days = _backup_settings()
    try:
        pruned = await asyncio.to_thread(prune_old_backups, keep_days)
        report["pruned"] = pruned
    except Exception as exc:
        log.warning("backup prune: %s", exc)

    size_mb = path.stat().st_size / (1024 * 1024)
    caption = (
        f"💾 <b>Бекап бази лояльності</b> ({reason})\n"
        f"Файл: <code>{path.name}</code>\n"
        f"Розмір: {size_mb:.2f} МБ\n"
        f"Час (Київ): {now_kyiv().strftime('%d.%m.%Y %H:%M')}\n\n"
        "Зберігай файл поза сервером. Відновлення — замінити data.db і перезапустити бота."
    )

    recipients = admin_recipient_ids()
    if not recipients:
        report["errors"].append("немає admin id")
        return report

    for uid in recipients:
        try:
            await bot.send_document(
                uid,
                FSInputFile(str(path), filename=path.name),
                caption=caption,
                parse_mode="HTML",
            )
            report["sent"].append(uid)
        except Exception as exc:
            log.warning("backup send to %s failed: %s", uid, exc)
            report["errors"].append(f"{uid}: {exc}")

    report["ok"] = bool(report["sent"])
    return report


def _seconds_until_next_run(hour: int, minute: int) -> float:
    now = now_kyiv()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(30.0, (target - now).total_seconds())


async def _backup_loop(bot) -> None:
    assert _cron_stop is not None
    enabled, hour, minute, _keep = _backup_settings()
    while not _cron_stop.is_set():
        enabled, hour, minute, _keep = _backup_settings()
        if not enabled:
            try:
                await asyncio.wait_for(_cron_stop.wait(), timeout=3600)
            except asyncio.TimeoutError:
                continue
            break
        wait_s = _seconds_until_next_run(hour, minute)
        log.info("db backup: next run in %.0fs (Kyiv %02d:%02d)", wait_s, hour, minute)
        try:
            await asyncio.wait_for(_cron_stop.wait(), timeout=wait_s)
            break
        except asyncio.TimeoutError:
            pass
        if _cron_stop.is_set():
            break
        try:
            report = await send_backup_to_admins(bot, reason="щоденний автобекап")
            log.info(
                "db backup done ok=%s sent=%s errors=%s path=%s",
                report.get("ok"),
                report.get("sent"),
                report.get("errors"),
                report.get("path"),
            )
        except Exception:
            log.exception("db backup loop error")
        # Avoid double-fire within the same minute
        try:
            await asyncio.wait_for(_cron_stop.wait(), timeout=90)
        except asyncio.TimeoutError:
            continue


def start_backup_cron(bot) -> None:
    global _cron_task, _cron_stop
    enabled, hour, minute, keep = _backup_settings()
    if not enabled:
        log.info("db backup cron disabled (BACKUP_ENABLED=0)")
        return
    if _cron_task and not _cron_task.done():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _cron_stop = asyncio.Event()
    _cron_task = asyncio.create_task(_backup_loop(bot), name="db_backup_cron")
    log.info(
        "db backup cron started (Kyiv %02d:%02d, keep %sd)",
        hour,
        minute,
        keep,
    )


async def stop_backup_cron() -> None:
    global _cron_task, _cron_stop
    if _cron_stop:
        _cron_stop.set()
    if _cron_task:
        _cron_task.cancel()
        try:
            await _cron_task
        except asyncio.CancelledError:
            pass
        _cron_task = None
    _cron_stop = None
