"""Central Craftyki ledger + expiring lots (factual history)."""
from __future__ import annotations

import json
from typing import Any

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

STATUS_PENDING = "pending"
STATUS_SUBMITTED = "submitted"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"
STATUS_VOID = "void"

# Reasons used across the app
REASON_CASHBACK = "cashback"
REASON_SPEND = "spend"
REASON_WELCOME = "welcome"
REASON_BIRTHDAY = "birthday"
REASON_ANNUAL_BIRTHDAY = "annual_birthday"
REASON_REFERRAL = "referral"
REASON_REFERRAL_EXPIRE = "referral_expire"
REASON_REFERRAL_REVERSE = "referral_reverse"
REASON_QUEST = "quest"
REASON_BURN_90D = "burn_90d"
REASON_ADMIN_GIFT = "admin_gift"
REASON_COMPENSATION = "compensation"
REASON_ADMIN_ADJUST = "admin_adjust"

PAGE_SIZE = 10

STATUS_LABELS_UK: dict[str, str] = {
    STATUS_PENDING: "очікує",
    STATUS_SUBMITTED: "в Poster",
    STATUS_POSTED: "проведено",
    STATUS_FAILED: "помилка",
    STATUS_VOID: "скасовано",
}


def create_bonus_ledger_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_ledger (
            id INTEGER PRIMARY KEY,
            op_key TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            poster_client_id INTEGER,
            amount_uah REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            balance_before REAL,
            balance_after REAL,
            admin_user_id INTEGER,
            ref_type TEXT,
            ref_id TEXT,
            title TEXT,
            meta_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            posted_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_ledger_user_created
        ON bonus_ledger(user_id, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_ledger_status
        ON bonus_ledger(status)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_lots (
            id INTEGER PRIMARY KEY,
            ledger_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            amount_uah REAL NOT NULL,
            remaining_uah REAL NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            closed_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_lots_user_exp
        ON bonus_lots(user_id, expires_at)
        """
    )
    conn.commit()


def _row(r) -> dict | None:
    return dict(r) if r else None


def get_by_op_key(op_key: str) -> dict | None:
    return _row(
        cursor.execute("SELECT * FROM bonus_ledger WHERE op_key = ?", (op_key,)).fetchone()
    )


def get_by_id(ledger_id: int) -> dict | None:
    return _row(
        cursor.execute("SELECT * FROM bonus_ledger WHERE id = ?", (int(ledger_id),)).fetchone()
    )


def create_pending(
    *,
    op_key: str,
    user_id: int | None,
    poster_client_id: int | None,
    amount_uah: float,
    reason: str,
    title: str | None = None,
    admin_user_id: int | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Insert pending op or return existing row for the same op_key."""
    existing = get_by_op_key(op_key)
    if existing:
        return existing
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO bonus_ledger (
            op_key, user_id, poster_client_id, amount_uah, reason, status,
            admin_user_id, ref_type, ref_id, title, meta_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            op_key,
            int(user_id) if user_id is not None else None,
            int(poster_client_id) if poster_client_id is not None else None,
            round(float(amount_uah), 2),
            reason,
            STATUS_PENDING,
            int(admin_user_id) if admin_user_id is not None else None,
            ref_type,
            str(ref_id) if ref_id is not None else None,
            title,
            json.dumps(meta, ensure_ascii=False) if meta else None,
            now,
            now,
        ),
    )
    conn.commit()
    return get_by_op_key(op_key) or {}


def mark_submitted(ledger_id: int, *, balance_before: float | None) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, balance_before = ?, updated_at = ?
        WHERE id = ? AND status IN (?, ?)
        """,
        (STATUS_SUBMITTED, balance_before, now, int(ledger_id), STATUS_PENDING, STATUS_SUBMITTED),
    )
    conn.commit()


def mark_posted(
    ledger_id: int,
    *,
    balance_after: float | None = None,
) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, balance_after = COALESCE(?, balance_after),
            posted_at = ?, updated_at = ?, error = NULL
        WHERE id = ?
        """,
        (STATUS_POSTED, balance_after, now, now, int(ledger_id)),
    )
    conn.commit()


def mark_failed(ledger_id: int, error: str) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, error = ?, updated_at = ?
        WHERE id = ?
        """,
        (STATUS_FAILED, (error or "")[:500], now, int(ledger_id)),
    )
    conn.commit()


def list_incomplete(*, limit: int = 100) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM bonus_ledger
        WHERE status IN (?, ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (STATUS_PENDING, STATUS_SUBMITTED, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def list_for_user(
    user_id: int,
    *,
    limit: int = 80,
    posted_only: bool = True,
    nonzero_only: bool = True,
) -> list[dict]:
    where = ["user_id = ?"]
    params: list[Any] = [int(user_id)]
    if posted_only:
        where.append("status = ?")
        params.append(STATUS_POSTED)
    if nonzero_only:
        where.append("amount_uah != 0")
    params.append(int(limit))
    rows = cursor.execute(
        f"""
        SELECT * FROM bonus_ledger
        WHERE {" AND ".join(where)}
        ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def list_admin(
    *,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    reason: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    admin_only: bool = False,
) -> tuple[list[dict], int]:
    """Paginated factual journal for admin. Returns (rows, total)."""
    where: list[str] = ["1=1"]
    params: list[Any] = []
    if reason:
        where.append("reason = ?")
        params.append(reason)
    if status:
        where.append("status = ?")
        params.append(status)
    if user_id is not None:
        where.append("user_id = ?")
        params.append(int(user_id))
    if admin_only:
        where.append("admin_user_id IS NOT NULL")
    where_sql = " AND ".join(where)
    total = int(
        cursor.execute(
            f"SELECT COUNT(*) FROM bonus_ledger WHERE {where_sql}", params
        ).fetchone()[0]
        or 0
    )
    rows = cursor.execute(
        f"""
        SELECT * FROM bonus_ledger
        WHERE {where_sql}
        ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, int(limit), max(0, int(offset))],
    ).fetchall()
    return [dict(r) for r in rows], total


def summary_admin() -> dict[str, Any]:
    """Aggregate counts / sums from factual ledger (no settings guesses)."""
    row = cursor.execute(
        """
        SELECT
            COUNT(*) AS total_ops,
            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS posted,
            SUM(CASE WHEN status IN (?, ?) THEN 1 ELSE 0 END) AS incomplete,
            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN status = ? AND amount_uah > 0 THEN amount_uah ELSE 0 END) AS credited,
            SUM(CASE WHEN status = ? AND amount_uah < 0 THEN amount_uah ELSE 0 END) AS debited,
            SUM(CASE WHEN status = ? AND admin_user_id IS NOT NULL THEN 1 ELSE 0 END) AS admin_ops
        FROM bonus_ledger
        """,
        (
            STATUS_POSTED,
            STATUS_PENDING,
            STATUS_SUBMITTED,
            STATUS_FAILED,
            STATUS_POSTED,
            STATUS_POSTED,
            STATUS_POSTED,
        ),
    ).fetchone()
    by_reason = cursor.execute(
        """
        SELECT reason, COUNT(*) AS n,
               SUM(CASE WHEN status = ? THEN amount_uah ELSE 0 END) AS sum_uah
        FROM bonus_ledger
        GROUP BY reason
        ORDER BY n DESC
        """,
        (STATUS_POSTED,),
    ).fetchall()
    return {
        "total_ops": int(row["total_ops"] or 0),
        "posted": int(row["posted"] or 0),
        "incomplete": int(row["incomplete"] or 0),
        "failed": int(row["failed"] or 0),
        "credited_uah": float(row["credited"] or 0),
        "debited_uah": float(row["debited"] or 0),
        "admin_ops": int(row["admin_ops"] or 0),
        "by_reason": [dict(r) for r in by_reason],
    }


def iter_for_export(
    *,
    reason: str | None = None,
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 20000,
) -> list[dict]:
    rows, _ = list_admin(
        offset=0,
        limit=limit,
        reason=reason,
        status=status,
        user_id=user_id,
    )
    return rows


def create_lot(
    *,
    ledger_id: int,
    user_id: int,
    source: str,
    amount_uah: float,
    expires_at: str | None,
) -> int:
    now = kyiv_now_str()
    amt = round(float(amount_uah), 2)
    cursor.execute(
        """
        INSERT INTO bonus_lots (
            ledger_id, user_id, source, amount_uah, remaining_uah, expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (int(ledger_id), int(user_id), source, amt, amt, expires_at, now),
    )
    conn.commit()
    return int(cursor.lastrowid)


def allocate_spend(user_id: int, spend_uah: float) -> float:
    """Reduce lot remainders (soonest expiry first). Returns unallocated spend."""
    left = round(float(spend_uah), 2)
    if left <= 0:
        return 0.0
    rows = cursor.execute(
        """
        SELECT id, remaining_uah FROM bonus_lots
        WHERE user_id = ? AND remaining_uah > 0 AND closed_at IS NULL
        ORDER BY
          CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
          expires_at ASC,
          id ASC
        """,
        (int(user_id),),
    ).fetchall()
    now = kyiv_now_str()
    for row in rows:
        if left <= 0:
            break
        rem = round(float(row["remaining_uah"] or 0), 2)
        take = min(rem, left)
        new_rem = round(rem - take, 2)
        if new_rem <= 0:
            cursor.execute(
                "UPDATE bonus_lots SET remaining_uah = 0, closed_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        else:
            cursor.execute(
                "UPDATE bonus_lots SET remaining_uah = ? WHERE id = ?",
                (new_rem, row["id"]),
            )
        left = round(left - take, 2)
    conn.commit()
    return left


def get_lot_remaining_for_ledger(ledger_id: int) -> float:
    row = cursor.execute(
        "SELECT remaining_uah FROM bonus_lots WHERE ledger_id = ?",
        (int(ledger_id),),
    ).fetchone()
    return round(float(row["remaining_uah"] or 0), 2) if row else 0.0


def close_lot_for_ledger(ledger_id: int) -> None:
    cursor.execute(
        """
        UPDATE bonus_lots
        SET remaining_uah = 0, closed_at = ?
        WHERE ledger_id = ? AND closed_at IS NULL
        """,
        (kyiv_now_str(), int(ledger_id)),
    )
    conn.commit()


def list_expired_lots(now_str: str) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM bonus_lots
        WHERE expires_at IS NOT NULL
          AND expires_at <= ?
          AND remaining_uah > 0
          AND closed_at IS NULL
        ORDER BY expires_at ASC
        """,
        (now_str,),
    ).fetchall()
    return [dict(r) for r in rows]


REASON_TITLES_UK: dict[str, str] = {
    REASON_CASHBACK: "Кешбек з покупки",
    REASON_SPEND: "Списання на касі",
    REASON_WELCOME: "Вітальні Крафтики за реєстрацію",
    REASON_BIRTHDAY: "Крафтики за день народження",
    REASON_ANNUAL_BIRTHDAY: "Вітальний бонус у день народження",
    REASON_REFERRAL: "Крафтики за друга",
    REASON_REFERRAL_EXPIRE: "Згоряння реферальної винагороди",
    REASON_REFERRAL_REVERSE: "Скасування реферальної винагороди",
    REASON_QUEST: "Винагорода за квест",
    REASON_BURN_90D: "Згоряння Крафтиків (90 днів)",
    REASON_ADMIN_GIFT: "Подарунок від Крафт Кава",
    REASON_COMPENSATION: "Компенсація",
    REASON_ADMIN_ADJUST: "Коригування адміном",
}

# Reasons shown in admin filter keyboard (order matters)
ADMIN_FILTER_REASONS: list[str] = [
    REASON_CASHBACK,
    REASON_SPEND,
    REASON_WELCOME,
    REASON_BIRTHDAY,
    REASON_ANNUAL_BIRTHDAY,
    REASON_REFERRAL,
    REASON_REFERRAL_EXPIRE,
    REASON_QUEST,
    REASON_BURN_90D,
    REASON_ADMIN_GIFT,
    REASON_COMPENSATION,
]


def history_title(row: dict) -> str:
    if row.get("title"):
        return str(row["title"])
    return REASON_TITLES_UK.get(str(row.get("reason") or ""), "Операція з Крафтиками")


def fetch_users_brief(user_ids: list[int]) -> dict[int, dict]:
    """user_id → {display_name, user_first_name, user_phone}."""
    ids = sorted({int(x) for x in user_ids if x is not None})
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = cursor.execute(
        f"""
        SELECT user_id, display_name, user_first_name, user_phone, user_name
        FROM users WHERE user_id IN ({ph})
        """,
        ids,
    ).fetchall()
    return {int(r["user_id"]): dict(r) for r in rows}


def fetch_purchases_by_tx_ids(tx_ids: list[str]) -> dict[str, dict]:
    """transaction_id → purchase row (products, spot, sum)."""
    ids = sorted({str(x) for x in tx_ids if x})
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = cursor.execute(
        f"""
        SELECT transaction_id, products_json, spot_name, payed_sum_uah, bonus_uah, bonus_spent_uah
        FROM processed_transactions
        WHERE transaction_id IN ({ph})
        """,
        ids,
    ).fetchall()
    return {str(r["transaction_id"]): dict(r) for r in rows}


def _insert_posted_legacy(
    *,
    op_key: str,
    user_id: int | None,
    poster_client_id: int | None,
    amount_uah: float,
    reason: str,
    title: str,
    ref_type: str | None,
    ref_id: str | None,
    when: str,
    meta: dict | None = None,
) -> bool:
    """Idempotent insert of an already-happened op (no Poster call)."""
    if get_by_op_key(op_key):
        return False
    amount = round(float(amount_uah or 0), 2)
    if abs(amount) < 0.005:
        return False
    cursor.execute(
        """
        INSERT INTO bonus_ledger (
            op_key, user_id, poster_client_id, amount_uah, reason, status,
            ref_type, ref_id, title, meta_json, created_at, updated_at, posted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            op_key,
            int(user_id) if user_id is not None else None,
            int(poster_client_id) if poster_client_id is not None else None,
            amount,
            reason,
            STATUS_POSTED,
            ref_type,
            str(ref_id) if ref_id is not None else None,
            title,
            json.dumps(meta, ensure_ascii=False) if meta else None,
            when,
            when,
            when,
        ),
    )
    return True


def backfill_user_ledger(user_id: int) -> dict[str, int]:
    """Pull legacy purchases (+ welcome/birthday flags) into bonus_ledger for one client.

    Safe / idempotent via op_key. Does not touch Poster.
    """
    uid = int(user_id)
    added = {"cashback": 0, "spend": 0, "welcome": 0, "birthday": 0}

    rows = cursor.execute(
        """
        SELECT transaction_id, poster_client_id, payed_sum_uah, bonus_uah, bonus_spent_uah,
               processed_at, date_close, spot_name
        FROM processed_transactions
        WHERE telegram_user_id = ?
        ORDER BY COALESCE(date_close, processed_at) ASC
        """,
        (uid,),
    ).fetchall()

    for r in rows:
        tid = str(r["transaction_id"] or "").strip()
        if not tid:
            continue
        when = (r["date_close"] or r["processed_at"] or kyiv_now_str())[:19]
        poster_id = r["poster_client_id"]
        bonus = float(r["bonus_uah"] or 0)
        spent = float(r["bonus_spent_uah"] or 0)
        meta = {
            "legacy_backfill": True,
            "payed_sum_uah": float(r["payed_sum_uah"] or 0),
            "spot_name": r["spot_name"],
        }
        if bonus > 0.004:
            if _insert_posted_legacy(
                op_key=f"cashback:tx:{tid}",
                user_id=uid,
                poster_client_id=poster_id,
                amount_uah=bonus,
                reason=REASON_CASHBACK,
                title=REASON_TITLES_UK[REASON_CASHBACK],
                ref_type="transaction",
                ref_id=tid,
                when=when,
                meta=meta,
            ):
                added["cashback"] += 1
        if spent > 0.004:
            if _insert_posted_legacy(
                op_key=f"spend:tx:{tid}",
                user_id=uid,
                poster_client_id=poster_id,
                amount_uah=-abs(spent),
                reason=REASON_SPEND,
                title=REASON_TITLES_UK[REASON_SPEND],
                ref_type="transaction",
                ref_id=tid,
                when=when,
                meta=meta,
            ):
                added["spend"] += 1

    user = cursor.execute(
        """
        SELECT poster_client_id, welcome_bonus_given, birthday_bonus_given,
               join_date, registered_at, last_activity
        FROM users WHERE user_id = ?
        """,
        (uid,),
    ).fetchone()
    if user:
        poster_id = user["poster_client_id"]
        join_at = (user["registered_at"] or user["join_date"] or kyiv_now_str())[:19]
        if int(user["welcome_bonus_given"] or 0):
            try:
                from database_functions.settings_db import get_welcome_bonus_uah

                amt = float(get_welcome_bonus_uah())
            except Exception:
                amt = 0.0
            if amt > 0 and _insert_posted_legacy(
                op_key=f"legacy:welcome:{uid}",
                user_id=uid,
                poster_client_id=poster_id,
                amount_uah=amt,
                reason=REASON_WELCOME,
                title=REASON_TITLES_UK[REASON_WELCOME],
                ref_type="legacy",
                ref_id=str(uid),
                when=join_at,
                meta={"legacy_backfill": True},
            ):
                added["welcome"] += 1
        if int(user["birthday_bonus_given"] or 0):
            try:
                from database_functions.settings_db import get_birthday_bonus_uah

                amt = float(get_birthday_bonus_uah())
            except Exception:
                amt = 0.0
            when = (user["last_activity"] or join_at)[:19]
            if amt > 0 and _insert_posted_legacy(
                op_key=f"legacy:birthday:{uid}",
                user_id=uid,
                poster_client_id=poster_id,
                amount_uah=amt,
                reason=REASON_BIRTHDAY,
                title=REASON_TITLES_UK[REASON_BIRTHDAY],
                ref_type="legacy",
                ref_id=str(uid),
                when=when,
                meta={"legacy_backfill": True},
            ):
                added["birthday"] += 1

    if any(added.values()):
        conn.commit()
    return added


def purchase_items_summary(products_json: object, *, max_items: int = 4) -> str:
    """Short human line from products_json, e.g. «Капучино, Круасан»."""
    import json

    try:
        items = json.loads(products_json or "[]")
    except Exception:
        return ""
    if not isinstance(items, list) or not items:
        return ""
    names: list[str] = []
    for it in items[:max_items]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "Товар").strip()
        try:
            qty = float(it.get("count") or 1)
        except (TypeError, ValueError):
            qty = 1
        if qty > 1:
            names.append(f"{qty:g}×{name}")
        else:
            names.append(name)
    more = len(items) - max_items
    s = ", ".join(names)
    if more > 0:
        s += f" +{more}"
    return s
