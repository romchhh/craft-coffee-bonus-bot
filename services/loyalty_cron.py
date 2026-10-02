"""Періодична перевірка закритих чеків Poster для клієнтів бонусної програми."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import (
    LOYALTY_CRON_ENABLED,
    LOYALTY_CRON_INTERVAL_SEC,
    LOYALTY_CRON_LOOKBACK_DAYS,
)
from database_functions.client_db import registered_poster_client_ids
from database_functions.settings_db import is_transaction_processed
from services import poster
from services.loyalty import process_closed_transaction

log = logging.getLogger(__name__)

_cron_task: asyncio.Task | None = None
_cron_stop: asyncio.Event | None = None


def _tx_client_id(tx: dict) -> int:
    try:
        return int(tx.get("client_id") or 0)
    except (TypeError, ValueError):
        return 0


async def scan_closed_transactions(
    *,
    lookback_days: int | None = None,
    bot=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Знаходить закриті чеки з клієнтами з бота, які ще не в processed_transactions.
    dry_run=True — лише звіт, без нарахування.
    """
    days = lookback_days if lookback_days is not None else LOYALTY_CRON_LOOKBACK_DAYS
    bot_clients = registered_poster_client_ids()
    report: dict[str, Any] = {
        "lookback_days": days,
        "bot_clients": len(bot_clients),
        "poster_transactions": 0,
        "bot_client_receipts": 0,
        "pending": [],
        "processed": [],
        "skipped": [],
        "errors": [],
    }
    log.debug(
        "loyalty cron scan start: lookback=%sd bot_clients=%s ids=%s dry_run=%s",
        days,
        len(bot_clients),
        sorted(bot_clients),
        dry_run,
    )
    if not bot_clients:
        log.info("loyalty cron: немає зареєстрованих клієнтів — пропуск")
        return report

    try:
        txs = await asyncio.to_thread(poster.get_closed_transactions, days)
    except Exception as exc:
        log.exception("loyalty cron: get_closed_transactions")
        report["errors"].append(str(exc))
        return report

    report["poster_transactions"] = len(txs)
    report["other_client_receipts"] = []
    seen: set[str] = set()

    for tx in txs:
        cid = _tx_client_id(tx)
        tid = poster.transaction_id_from_row(tx)
        if not tid or tid in seen:
            continue
        seen.add(tid)

        if cid not in bot_clients:
            if cid:
                report["other_client_receipts"].append(
                    {
                        "transaction_id": tid,
                        "client_id": cid,
                        "status": tx.get("status"),
                        "payed_uah": poster.from_minor(tx.get("payed_sum")),
                        "bonus_spent_uah": poster.from_minor(tx.get("payed_bonus") or 0),
                        "closed_at": tx.get("date_close_date") or tx.get("date_close"),
                    }
                )
            continue

        report["bot_client_receipts"] += 1

        if is_transaction_processed(tid):
            report["skipped"].append(tid)
            continue

        report["pending"].append(tid)
        payed = poster.from_minor(tx.get("payed_sum"))
        log.info(
            "loyalty cron: новий чек клієнта бота tx=%s client_id=%s payed=%.2f грн",
            tid,
            cid,
            payed,
        )
        if dry_run:
            continue

        try:
            result = await process_closed_transaction(tid, bot=bot)
            report["processed"].append({"transaction_id": tid, "result": result})
            status = result.get("status")
            if status == "ok":
                log.info(
                    "loyalty cron OK tx=%s bonus=%.2f грн user=%s",
                    tid,
                    result.get("bonus_uah") or 0,
                    result.get("telegram_user_id"),
                )
            else:
                log.info("loyalty cron tx=%s result=%s", tid, result)
        except Exception as exc:
            log.exception("loyalty cron tx=%s", tid)
            report["errors"].append(f"{tid}: {exc}")

    ok_count = sum(
        1 for p in report["processed"] if (p.get("result") or {}).get("status") == "ok"
    )
    has_work = bool(report["pending"] or report["errors"] or ok_count)
    if has_work or report["bot_client_receipts"]:
        log.info(
            "loyalty cron scan done: poster_txs=%s bot_receipts=%s pending=%s credited=%s skipped=%s errors=%s",
            report["poster_transactions"],
            report["bot_client_receipts"],
            len(report["pending"]),
            ok_count,
            len(report["skipped"]),
            len(report["errors"]),
        )
    else:
        log.debug(
            "loyalty cron scan idle: poster_txs=%s bot_clients=%s",
            report["poster_transactions"],
            sorted(bot_clients),
        )
    if report["pending"] and dry_run:
        log.info("loyalty cron pending tx ids: %s", report["pending"])
    if report["other_client_receipts"] and not report["bot_client_receipts"]:
        log.info(
            "loyalty cron: чеки є, але client_id не з бота %s — скануй штрихкод на касі. %s",
            sorted(bot_clients),
            report["other_client_receipts"],
        )
    return report


async def _cron_loop(bot) -> None:
    assert _cron_stop is not None
    await asyncio.sleep(8)
    tick = 0
    while not _cron_stop.is_set():
        tick += 1
        log.info(
            "loyalty cron tick #%s (кожні %s с, lookback %s дн.)",
            tick,
            LOYALTY_CRON_INTERVAL_SEC,
            LOYALTY_CRON_LOOKBACK_DAYS,
        )
        try:
            await scan_closed_transactions(bot=bot, dry_run=False)
        except Exception:
            log.exception("loyalty cron tick #%s failed", tick)
        try:
            await asyncio.wait_for(_cron_stop.wait(), timeout=LOYALTY_CRON_INTERVAL_SEC)
            log.info("loyalty cron stopped after tick #%s", tick)
            break
        except asyncio.TimeoutError:
            continue


def start_loyalty_cron(bot) -> None:
    global _cron_task, _cron_stop
    if not LOYALTY_CRON_ENABLED:
        log.info("loyalty cron disabled (LOYALTY_CRON_ENABLED=0)")
        return
    if _cron_task and not _cron_task.done():
        return
    _cron_stop = asyncio.Event()
    _cron_task = asyncio.create_task(_cron_loop(bot), name="loyalty_cron")
    log.info(
        "loyalty cron started (every %ss, lookback %sd)",
        LOYALTY_CRON_INTERVAL_SEC,
        LOYALTY_CRON_LOOKBACK_DAYS,
    )


async def stop_loyalty_cron() -> None:
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


async def _main_cli() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Перевірка закритих чеків Poster для лояльності")
    parser.add_argument("--dry-run", action="store_true", help="Лише звіт, без нарахування")
    parser.add_argument("--days", type=int, default=LOYALTY_CRON_LOOKBACK_DAYS)
    parser.add_argument("--apply", action="store_true", help="Нарахувати бонуси (без --dry-run)")
    args = parser.parse_args()
    dry = args.dry_run or not args.apply
    report = await scan_closed_transactions(lookback_days=args.days, bot=None, dry_run=dry)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main_cli())
