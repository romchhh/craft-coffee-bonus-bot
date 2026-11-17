"""Safe Craftyki mutations: ledger + Poster + optional expiring lots."""
from __future__ import annotations

import logging
from typing import Any

from database_functions import bonus_ledger_db as ldb
from database_functions.client_db import get_user, set_last_known_bonus
from services import poster
from services.poster_client_cache import invalidate_client

log = logging.getLogger(__name__)


def _round2(x: float) -> float:
    return round(float(x or 0), 2)


def _read_balance(poster_client_id: int) -> float | None:
    try:
        return _round2(poster.get_client_bonus_uah(poster_client_id))
    except Exception as exc:
        log.warning("bonus_ops balance read client=%s: %s", poster_client_id, exc)
        return None


def _remember_balance(user_id: int | None, balance: float | None) -> None:
    if user_id is None or balance is None:
        return
    try:
        set_last_known_bonus(int(user_id), float(balance))
    except Exception:
        pass


def apply_bonus_delta(
    *,
    op_key: str,
    amount_uah: float,
    reason: str,
    user_id: int | None,
    poster_client_id: int | None,
    title: str | None = None,
    admin_user_id: int | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    meta: dict | None = None,
    expires_at: str | None = None,
    create_lot: bool = False,
) -> dict[str, Any]:
    """
    Idempotent credit/debit via Poster.
    Returns {status, ledger_id, amount_uah, balance_after?, error?}.
    """
    amount = _round2(amount_uah)
    if abs(amount) < 0.005:
        return {"status": "skip", "reason": "zero_amount"}
    if not poster_client_id:
        return {"status": "error", "reason": "no_poster_client"}

    row = ldb.create_pending(
        op_key=op_key,
        user_id=user_id,
        poster_client_id=int(poster_client_id),
        amount_uah=amount,
        reason=reason,
        title=title,
        admin_user_id=admin_user_id,
        ref_type=ref_type,
        ref_id=ref_id,
        meta=meta,
    )
    ledger_id = int(row["id"])
    if row.get("status") == ldb.STATUS_POSTED:
        return {
            "status": "ok",
            "already_posted": True,
            "ledger_id": ledger_id,
            "amount_uah": float(row["amount_uah"]),
            "balance_after": row.get("balance_after"),
        }

    bal_before = _read_balance(int(poster_client_id))
    # Resume after crash: Poster may already have applied the delta
    if row.get("status") == ldb.STATUS_SUBMITTED and bal_before is not None:
        expected = _round2(float(row.get("balance_before") or 0) + amount)
        if abs(bal_before - expected) <= 0.02 or (
            amount > 0 and bal_before + 1e-9 >= expected - 0.02
        ):
            ldb.mark_posted(ledger_id, balance_after=bal_before)
            _remember_balance(user_id, bal_before)
            if create_lot and amount > 0 and user_id and not _lot_exists(ledger_id):
                ldb.create_lot(
                    ledger_id=ledger_id,
                    user_id=int(user_id),
                    source=reason,
                    amount_uah=amount,
                    expires_at=expires_at,
                )
            return {
                "status": "ok",
                "recovered": True,
                "ledger_id": ledger_id,
                "amount_uah": amount,
                "balance_after": bal_before,
            }

    ldb.mark_submitted(ledger_id, balance_before=bal_before)
    try:
        poster.change_client_bonus(int(poster_client_id), amount)
        invalidate_client(int(poster_client_id))
    except Exception as exc:
        log.exception("bonus_ops Poster failed op=%s", op_key)
        ldb.mark_failed(ledger_id, str(exc))
        return {
            "status": "error",
            "ledger_id": ledger_id,
            "amount_uah": amount,
            "error": str(exc),
        }

    bal_after = _read_balance(int(poster_client_id))
    ldb.mark_posted(ledger_id, balance_after=bal_after)
    _remember_balance(user_id, bal_after if bal_after is not None else (
        _round2(bal_before + amount) if bal_before is not None else None
    ))

    if create_lot and amount > 0 and user_id:
        if not _lot_exists(ledger_id):
            ldb.create_lot(
                ledger_id=ledger_id,
                user_id=int(user_id),
                source=reason,
                amount_uah=amount,
                expires_at=expires_at,
            )

    if amount < 0 and user_id:
        ldb.allocate_spend(int(user_id), abs(amount))

    return {
        "status": "ok",
        "ledger_id": ledger_id,
        "amount_uah": amount,
        "balance_after": bal_after,
    }


def _lot_exists(ledger_id: int) -> bool:
    from database_functions.db import get_connection

    row = get_connection().execute(
        "SELECT 1 FROM bonus_lots WHERE ledger_id = ? LIMIT 1",
        (int(ledger_id),),
    ).fetchone()
    return row is not None


def record_external_spend(
    *,
    op_key: str,
    user_id: int,
    poster_client_id: int | None,
    amount_uah: float,
    ref_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Record POS spend already applied in Poster (no second Poster call)."""
    amount = -abs(_round2(amount_uah))
    if abs(amount) < 0.005:
        return {"status": "skip"}
    row = ldb.create_pending(
        op_key=op_key,
        user_id=user_id,
        poster_client_id=poster_client_id,
        amount_uah=amount,
        reason=ldb.REASON_SPEND,
        title=title or ldb.REASON_TITLES_UK[ldb.REASON_SPEND],
        ref_type="transaction",
        ref_id=ref_id,
    )
    if row.get("status") == ldb.STATUS_POSTED:
        return {"status": "ok", "already_posted": True, "ledger_id": row["id"]}
    ldb.mark_posted(int(row["id"]))
    ldb.allocate_spend(int(user_id), abs(amount))
    return {"status": "ok", "ledger_id": row["id"], "amount_uah": amount}


def resume_incomplete_ops(*, limit: int = 50) -> dict[str, Any]:
    """Retry pending/submitted ledger rows after restart."""
    report = {"checked": 0, "posted": 0, "failed": 0, "errors": []}
    for row in ldb.list_incomplete(limit=limit):
        report["checked"] += 1
        meta = None
        try:
            expires_at = None
            create_lot = row.get("reason") == ldb.REASON_REFERRAL
            if row.get("meta_json"):
                import json

                meta = json.loads(row["meta_json"])
                expires_at = (meta or {}).get("expires_at")
                create_lot = bool((meta or {}).get("create_lot")) or create_lot
            result = apply_bonus_delta(
                op_key=row["op_key"],
                amount_uah=float(row["amount_uah"]),
                reason=row["reason"],
                user_id=row.get("user_id"),
                poster_client_id=row.get("poster_client_id"),
                title=row.get("title"),
                admin_user_id=row.get("admin_user_id"),
                ref_type=row.get("ref_type"),
                ref_id=row.get("ref_id"),
                meta=meta,
                expires_at=expires_at,
                create_lot=create_lot,
            )
            if result.get("status") == "ok":
                report["posted"] += 1
            else:
                report["failed"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["errors"].append(f"{row.get('op_key')}: {exc}")
            log.exception("resume incomplete %s", row.get("op_key"))
    return report


def set_absolute_bonus(
    *,
    op_key: str,
    user_id: int,
    poster_client_id: int,
    target_uah: float,
    reason: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Welcome-style set: compute delta from current balance, then apply_delta."""
    target = _round2(target_uah)
    current = _read_balance(int(poster_client_id))
    if current is None:
        # Fall back to Poster set_bonus once, then ledger as posted
        try:
            poster.set_bonus(int(poster_client_id), target)
            invalidate_client(int(poster_client_id))
        except Exception as exc:
            return {"status": "error", "error": str(exc)}
        row = ldb.create_pending(
            op_key=op_key,
            user_id=user_id,
            poster_client_id=poster_client_id,
            amount_uah=target,
            reason=reason,
            title=title,
        )
        ldb.mark_posted(int(row["id"]), balance_after=target)
        _remember_balance(user_id, target)
        return {"status": "ok", "ledger_id": row["id"], "amount_uah": target, "balance_after": target}
    delta = _round2(target - current)
    if abs(delta) < 0.005:
        row = ldb.create_pending(
            op_key=op_key,
            user_id=user_id,
            poster_client_id=poster_client_id,
            amount_uah=0,
            reason=reason,
            title=title,
        )
        ldb.mark_posted(int(row["id"]), balance_after=current)
        return {"status": "ok", "ledger_id": row["id"], "amount_uah": 0, "balance_after": current}
    return apply_bonus_delta(
        op_key=op_key,
        amount_uah=delta,
        reason=reason,
        user_id=user_id,
        poster_client_id=poster_client_id,
        title=title,
    )
