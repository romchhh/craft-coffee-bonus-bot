from datetime import datetime

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from database_functions.admin_db import get_all_users_data, get_all_links_data, get_statistics_summary
from database_functions.loyalty_stats_db import (
    fetch_local_bonus_balances,
    fetch_poster_bonus_balances,
    get_loyalty_statistics_summary,
)
from utils.kyiv_time import format_date_ua, format_dt_ua, now_kyiv
import pandas as pd


def style_excel_sheet(
    ws,
    *,
    header_color: str = "35221A",
    zebra: bool = True,
    freeze: bool = True,
    autofilter: bool = True,
    column_group_colors: dict[tuple[int, int], str] | None = None,
) -> None:
    """Readable wide tables: header, zebra rows, freeze, filters, light borders.

    column_group_colors: optional {(start_col_1based, end_col_1based): "RRGGBB"}
    for tinted header groups (easier horizontal tracking).
    """
    if ws.max_row < 1 or ws.max_column < 1:
        return

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_align = Alignment(vertical="center", wrap_text=False)
    thin = Border(
        left=Side(style="thin", color="D9D0C7"),
        right=Side(style="thin", color="D9D0C7"),
        top=Side(style="thin", color="D9D0C7"),
        bottom=Side(style="thin", color="D9D0C7"),
    )
    default_header = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
    zebra_fill = PatternFill(start_color="F3EDE6", end_color="F3EDE6", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    group_fills: dict[int, PatternFill] = {}
    if column_group_colors:
        for (start, end), color in column_group_colors.items():
            fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
            for col in range(int(start), int(end) + 1):
                group_fills[col] = fill

    ws.row_dimensions[1].height = 32
    for cell in ws[1]:
        cell.fill = group_fills.get(cell.column, default_header)
        cell.font = header_font
        cell.alignment = header_align
        cell.border = thin

    max_row = ws.max_row
    max_col = ws.max_column
    for row_idx in range(2, max_row + 1):
        row_fill = zebra_fill if (zebra and row_idx % 2 == 0) else white_fill
        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = row_fill
            cell.border = thin
            cell.alignment = body_align

    if freeze:
        ws.freeze_panes = "A2"
    if autofilter and max_row >= 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"
    ws.sheet_view.showGridLines = False


def format_message_text(message) -> str:
    """
    Return message text (text or caption) formatted via format_entities.
    Use for all admin content editing and broadcasts.
    Keeps formatting tags and premium custom_emoji.
    """
    if message.text is not None:
        text = message.text
        entities = message.entities or []
    elif getattr(message, 'caption', None) is not None:
        text = message.caption
        entities = getattr(message, 'caption_entities', None) or []
    else:
        return ""
    if not text:
        return ""
    if entities:
        return format_entities(text, list(entities))
    return text


def format_entities(text: str, entities: list = None) -> str:
    if not text or not entities:
        return text

    utf16_to_utf8_map = create_utf16_to_utf8_mapping(text)
    
    adjusted_entities = []
    for entity in entities:
        utf8_offset = utf16_to_utf8_map.get(entity.offset, None)
        utf8_end = utf16_to_utf8_map.get(entity.offset + entity.length, None)
        
        if utf8_offset is None or utf8_end is None:
            continue
            
        new_entity = entity.__class__(**entity.__dict__) 
        new_entity.offset = utf8_offset
        new_entity.length = utf8_end - utf8_offset
        
        if new_entity.offset < 0 or new_entity.offset >= len(text):
            continue
        if new_entity.length <= 0:
            continue
        if new_entity.offset + new_entity.length > len(text):
            continue
            
        adjusted_entities.append(new_entity)
    
    if not adjusted_entities:
        return text
    
    entities_sorted = sorted(adjusted_entities, key=lambda e: (e.offset, get_entity_priority(e.type), -e.length))
    
    result = []
    current_pos = 0
    open_tags = []
    processed_entities = set()  
    
    for entity in entities_sorted:
        if id(entity) in processed_entities:
            continue
            
        entity_type = entity.type
        offset = entity.offset
        length = entity.length
        
        try:
            if offset > current_pos:
                result.append(text[current_pos:offset])
            
            while open_tags and open_tags[-1]['end'] <= offset:
                tag_info = open_tags.pop()
                result.append(tag_info['close_tag'])
            
            entity_text = text[offset:offset + length]
            
            # For custom_emoji, entity_text may contain an invisible placeholder
            if not entity_text.strip() and entity_type != "custom_emoji":
                continue
            
            open_tag, close_tag = get_entity_tags(entity, entity_text)
            
            if not open_tag:
                continue
            
            nested_entities = []
            for other_entity in entities_sorted:
                if (other_entity != entity and 
                    other_entity.type != entity_type and
                    other_entity.offset >= offset and 
                    other_entity.offset + other_entity.length <= offset + length and
                    other_entity.length > 0 and
                    not (other_entity.offset == offset and other_entity.length == length)):
                    nested_entities.append(other_entity)
            
            if nested_entities:
                result.append(open_tag)
                open_tags.append({
                    'end': offset + length,
                    'close_tag': close_tag
                })
                processed_entities.add(id(entity))
                current_pos = offset
            else:
                same_range_entities = [
                    e for e in entities_sorted 
                    if e != entity and e.offset == offset and e.length == length and id(e) not in processed_entities
                ]
                if same_range_entities:
                    all_entities = [entity] + same_range_entities
                    all_entities.sort(key=lambda e: get_entity_priority(e.type))
                    for e in all_entities:
                        e_open_tag, e_close_tag = get_entity_tags(e, text[offset:offset + length])
                        result.append(e_open_tag)
                        open_tags.append({
                            'end': offset + length,
                            'close_tag': e_close_tag
                        })
                        processed_entities.add(id(e))
                    result.append(entity_text)
                    current_pos = offset + length
                else:
                    result.append(open_tag)
                    result.append(entity_text)
                    result.append(close_tag)
                    processed_entities.add(id(entity))
                    current_pos = offset + length
            
        except (AttributeError, IndexError) as e:
            continue
        except Exception as e:
            continue
    
    while open_tags:
        tag_info = open_tags.pop()
        result.append(tag_info['close_tag'])
    
    if current_pos < len(text):
        result.append(text[current_pos:])
    
    return ''.join(result)



def create_utf16_to_utf8_mapping(text: str) -> dict:
    utf16_to_utf8 = {}
    utf16_pos = 0
    
    for utf8_pos, char in enumerate(text):
        utf16_to_utf8[utf16_pos] = utf8_pos
        utf16_length = len(char.encode('utf-16-le')) // 2
        utf16_pos += utf16_length
    
    utf16_to_utf8[utf16_pos] = len(text)
    
    return utf16_to_utf8

def get_entity_tags(entity, entity_text: str) -> tuple:
    entity_type = entity.type
    open_tag = ""
    close_tag = ""
    
    if entity_type == "bold":
        open_tag = "<b>"
        close_tag = "</b>"
    elif entity_type == "italic":
        open_tag = "<i>"
        close_tag = "</i>"
    elif entity_type == "underline":
        open_tag = "<u>"
        close_tag = "</u>"
    elif entity_type == "strikethrough":
        open_tag = "<s>"
        close_tag = "</s>"
    elif entity_type == "spoiler":
        open_tag = "<tg-spoiler>"
        close_tag = "</tg-spoiler>"
    elif entity_type == "code":
        open_tag = "<code>"
        close_tag = "</code>"
    elif entity_type == "pre":
        language = getattr(entity, 'language', None)
        if language:
            open_tag = f'<pre><code class="language-{language}">'
            close_tag = "</code></pre>"
        else:
            open_tag = "<pre>"
            close_tag = "</pre>"
    elif entity_type == "blockquote":
        open_tag = "<blockquote>"
        close_tag = "</blockquote>"
    elif entity_type == "text_link":
        url = getattr(entity, 'url', '')
        url = safe_html_escape(url)
        if not url:
            return "", ""
        open_tag = f'<a href="{url}">'
        close_tag = "</a>"
    elif entity_type == "url":
        if not entity_text:
            return "", ""
        open_tag = f'<a href="{entity_text}">'
        close_tag = "</a>"
    elif entity_type == "mention":
        if not entity_text.startswith('@'):
            return "", ""
        open_tag = f'<a href="https://t.me/{entity_text[1:]}">'
        close_tag = "</a>"
    elif entity_type == "hashtag":
        if not entity_text.startswith('#'):
            return "", ""
        open_tag = f'<a href="https://t.me/hashtag/{entity_text[1:]}">'
        close_tag = "</a>"
    elif entity_type == "custom_emoji":
        # Keep custom_emoji_id to send premium emoji from the bot
        custom_emoji_id = getattr(entity, 'custom_emoji_id', None)
        if not custom_emoji_id:
            return "", ""
        open_tag = f'<tg-emoji emoji-id="{custom_emoji_id}">'
        close_tag = "</tg-emoji>"
    
    return open_tag, close_tag

def safe_html_escape(text: str) -> str:
    if not text:
        return text
    
    escape_dict = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;'
    }
    
    for char, escaped in escape_dict.items():
        text = text.replace(char, escaped)
    
    return text

def get_entity_priority(entity_type: str) -> int:
    priority_map = {
        'text_link': 1,
        'url': 1,
        'mention': 1,
        'hashtag': 1,
        'bold': 2,
        'italic': 2,
        'underline': 2,
        'strikethrough': 2,
        'code': 3,
        'pre': 3,
        'spoiler': 3,
        'custom_emoji': 3,
        'blockquote': 4
    }
    return priority_map.get(entity_type, 5)


def parse_url_buttons(text):
    buttons = []
    lines = text.split('\n')
    for line in lines:
        if ' | ' in line:
            parts = line.split(' | ')
            row = []
            for part in parts:
                button_parts = part.split(' - ')
                if len(button_parts) == 2:
                    button_text = button_parts[0].strip()
                    button_url = button_parts[1].strip()
                    row.append((button_text, button_url))
            buttons.append(row)
        else:
            button_parts = line.split(' - ')
            if len(button_parts) == 2:
                button_text = button_parts[0].strip()
                button_url = button_parts[1].strip()
                buttons.append([(button_text, button_url)])
    return buttons


def parse_track_buttons(text: str) -> list[list[dict]]:
    """Parse poll/track buttons for mailing engagement.

    Formats:
      Лате | Американо | Капучино   → one row
      Лате                          → one button per line
      Лате - latte                  → label + custom key

    Returns rows of {key, label}.
    """
    import re

    def _slug(label: str, idx: int) -> str:
        raw = re.sub(r"[^a-zA-Zа-яА-ЯіїєґІЇЄҐ0-9]+", "_", (label or "").strip().lower())
        raw = raw.strip("_")[:24] or f"b{idx}"
        return raw

    rows: list[list[dict]] = []
    idx = 0
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        row: list[dict] = []
        for part in parts:
            if " - " in part:
                label, key = part.split(" - ", 1)
                label, key = label.strip(), key.strip()
            else:
                label, key = part, ""
            if not label:
                continue
            key = key or _slug(label, idx)
            key = re.sub(r"[^a-zA-Z0-9_]", "", key)[:32] or f"b{idx}"
            row.append({"key": key, "label": label[:64]})
            idx += 1
        if row:
            rows.append(row)
    return rows


def generate_database_export():
    users_data, users_columns = get_all_users_data()
    links_data, links_columns = get_all_links_data()
    
    users_df = pd.DataFrame(users_data, columns=users_columns)
    links_df = pd.DataFrame(links_data, columns=links_columns)
    
    current_date = datetime.now().strftime('%d.%m.%Y_%H-%M')
    filename = f'database_export_{current_date}.xlsx'
    
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        users_df.to_excel(writer, sheet_name="Користувачі", index=False)
        links_df.to_excel(writer, sheet_name="Посилання", index=False)

        worksheet_users = writer.sheets["Користувачі"]
        column_widths = {
            "A": 12,
            "B": 15,
            "C": 20,
            "D": 20,
            "E": 20,
            "F": 15,
            "G": 10,
            "H": 20,
            "I": 20,
            "J": 15,
        }
        for col, width in column_widths.items():
            worksheet_users.column_dimensions[col].width = width
        style_excel_sheet(worksheet_users, header_color="35221A")

        if not links_df.empty:
            worksheet_links = writer.sheets["Посилання"]
            for col, width in {"A": 12, "B": 30, "C": 50}.items():
                worksheet_links.column_dimensions[col].width = width
            style_excel_sheet(worksheet_links, header_color="35221A")

    return filename, len(users_df), len(links_df)


def _uah(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def format_statistics_message(*, refresh_poster: bool = False) -> str:
    """Build admin stats. Uses local DB only by default (fast).

    refresh_poster=True — slow live sweep of every Poster card (use rarely).
    """
    stats = get_statistics_summary()
    loyalty = get_loyalty_statistics_summary()
    if refresh_poster:
        bal = fetch_poster_bonus_balances(force=True)
        bal_line = (
            f"• На балансах у <b>Poster</b> (живе): <b>{_uah(bal['outstanding_bonus_uah'])} грн</b> "
            f"({bal['clients_with_bonus_balance']} з балансом"
            + (f", помилок {bal['poster_errors']}" if bal.get("poster_errors") else "")
            + f") · {_esc_plain(bal.get('as_of'))}"
        )
    else:
        bal = fetch_local_bonus_balances()
        unknown = int(bal.get("clients_unknown_balance") or 0)
        bal_line = (
            f"• Орієнтовно на балансах: <b>{_uah(bal['outstanding_bonus_uah'])} грн</b> "
            f"({bal['clients_with_bonus_balance']} клієнтів з відомим балансом"
            + (f", без даних: {unknown}" if unknown else "")
            + ")\n"
            f"   <i>З останніх відомих у боті. Фоновний sync оновлює Poster сам; "
            f"кнопка нижче — повне оновлення вручну (теж у фоні).</i>"
        )

    language_emoji = {
        "uk": "🇺🇦",
        "ru": "🇷🇺",
        "en": "🇬🇧",
        "pl": "🇵🇱",
        "de": "🇩🇪",
        "fr": "🇫🇷",
        "es": "🇪🇸",
        "it": "🇮🇹",
    }

    languages_text = ""
    for lang, count in stats["languages"]:
        emoji = language_emoji.get(lang, "🌐")
        percentage = (count / stats["total_users"] * 100) if stats["total_users"] > 0 else 0
        languages_text += f"   {emoji} {lang or 'Невідомо'}: {count} ({percentage:.1f}%)"

    top_links_text = ""
    if stats["top_links"]:
        for i, (link_name, clicks) in enumerate(stats["top_links"], 1):
            top_links_text += f"   {i}. {link_name}: {clicks} переходів"
    else:
        top_links_text = "   Немає даних\n"

    phone_percentage = (
        (stats["users_with_phone"] / stats["total_users"] * 100) if stats["total_users"] > 0 else 0
    )
    links_percentage = (
        (stats["users_from_links"] / stats["total_users"] * 100) if stats["total_users"] > 0 else 0
    )

    reg = loyalty["registered_clients"]
    reg_pct = (reg / stats["total_users"] * 100) if stats["total_users"] > 0 else 0

    from database_functions.client_db import count_bonuses_blocked

    blocked_n = count_bonuses_blocked()
    updated = now_kyiv().strftime("%d.%m.%Y %H:%M")

    message = f"""<b>📊 ДЕТАЛЬНА СТАТИСТИКА БОТА</b>

<b>👥 ЗАГАЛЬНА ІНФОРМАЦІЯ</b>
• Всього користувачів: <b>{stats['total_users']}</b>
• З номером телефону: <b>{stats['users_with_phone']}</b> ({phone_percentage:.1f}%)

<b>☕ КЛІЄНТИ ТА ЛОЯЛЬНІСТЬ</b>
• У програмі лояльності: <b>{reg}</b> ({reg_pct:.1f}% від усіх у боті)
• Купували (чеки через бот): <b>{loyalty['buyers_unique']}</b>
• Повертаються (≥2 покупки): <b>{loyalty['returning_clients']}</b> — <b>{loyalty['return_rate_percent']:.1f}%</b> від покупців
• Чеків загалом: <b>{loyalty['purchases_total']}</b> на <b>{_uah(loyalty['payed_total_uah'])} грн</b>
• З блокуванням Крафтиків: <b>{blocked_n}</b> · картки — меню <b>👤 Клієнти</b>

<b>🎁 КРАФТИКИ НА БАЛАНСІ</b>
• Нараховано кешбеку (бот): <b>{_uah(loyalty['cashback_accrued_uah'])} грн</b>
• Списано в чеках: <b>{_uah(loyalty['bonus_spent_uah'])} грн</b>
• Вітальні: <b>{loyalty['welcome_count']}</b> видач (~<b>{_uah(loyalty['welcome_total_est_uah'])} грн</b> за поточним тарифом)
{bal_line}

<b>🛒 ПОКУПКИ (клієнти бота, з 00:00 Києва)</b>
• Сьогодні: <b>{loyalty['purchases_today']}</b> чеків, <b>{loyalty['buyers_today']}</b> клієнтів, <b>{_uah(loyalty['payed_today_uah'])} грн</b>
• За 7 днів: <b>{loyalty['purchases_week']}</b> чеків, <b>{loyalty['buyers_week']}</b> клієнтів, <b>{_uah(loyalty['payed_week_uah'])} грн</b>
• За 30 днів: <b>{loyalty['purchases_month']}</b> чеків, <b>{loyalty['buyers_month']}</b> клієнтів, <b>{_uah(loyalty['payed_month_uah'])} грн</b>
<i>Чеки за датою закриття в Poster (не коли бот їх підхопив).</i>

<b>📈 НОВІ (з 00:00 Києва)</b>
• У боті (/start) сьогодні: <b>{stats['new_today']}</b>
• Картки лояльності сьогодні: <b>{loyalty.get('new_registered_today', 0)}</b>
• У боті за тиждень / місяць: <b>{stats['new_week']}</b> / <b>{stats['new_month']}</b>

<b>⚡️ АКТИВНІ (з 00:00 Києва)</b>
• За сьогодні: <b>{stats['active_today']}</b>
• За тиждень: <b>{stats['active_week']}</b>
• За місяць: <b>{stats['active_month']}</b>

<b>🌍 СТАТИСТИКА ПО МОВАХ</b>
{languages_text}

<b>🔗 СТАТИСТИКА ПО ПОСИЛАННЯХ</b>
• Всього посилань: <b>{stats['total_links']}</b>
• Всього переходів: <b>{stats['total_clicks']}</b>
• Користувачів з посилань: <b>{stats['users_from_links']}</b> ({links_percentage:.1f}%)

<b>🏆 ТОП-5 ПОСИЛАНЬ:</b>
{top_links_text}

<i>📅 Оновлено: {updated} (Київ) · періоди — календарний день</i>"""

    return message


def _esc_plain(s: object) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_clients_export() -> tuple[str, int]:
    """Excel of all registered clients with spend / Крафтики / referrals / venues.

    Uses last_known_bonus (local) — no live Poster N× sweep.
    Returns (filename, clients_count). Caller should delete the file after send.
    """
    from database_functions.clients_admin_db import iter_clients_stats_for_export

    rows = iter_clients_stats_for_export()
    export_rows = []
    for r in rows:
        referrer_label = (
            r.get("referrer_name")
            or r.get("referrer_first_name")
            or (f"@{r['referrer_username']}" if r.get("referrer_username") else "")
            or ""
        )
        balance = None
        if r.get("last_known_bonus") is not None:
            try:
                balance = float(r["last_known_bonus"])
            except (TypeError, ValueError):
                balance = None

        export_rows.append(
            {
                "Telegram ID": r.get("user_id"),
                "Username": (f"@{r['user_name']}" if r.get("user_name") else ""),
                "Імʼя": r.get("display_name")
                or " ".join(
                    x for x in [r.get("user_first_name"), r.get("user_last_name")] if x
                )
                or "",
                "Телефон": r.get("user_phone") or "",
                "Картка": r.get("card_number") or "",
                "Poster client_id": r.get("poster_client_id") or "",
                "Дата народження": (
                    format_date_ua(r.get("birthday"), empty="") if r.get("birthday") else ""
                ),
                "Вік": r.get("age") if r.get("age") is not None else "",
                "Реєстрація": format_dt_ua(r.get("join_date"), empty=""),
                "Остання активність": format_dt_ua(r.get("last_activity"), empty=""),
                "Крафтики заблоковано": "так" if int(r.get("bonuses_blocked") or 0) else "ні",
                "Вітальний бонус": "так" if int(r.get("welcome_bonus_given") or 0) else "ні",
                "Бонус ДН": "так" if int(r.get("birthday_bonus_given") or 0) else "ні",
                "Розсилка": (
                    "відписаний" if int(r.get("mailing_opt_out") or 0) else "підписаний"
                ),
                "Дата відписки": format_dt_ua(r.get("mailing_opt_out_at"), empty=""),
                "Причина відписки": (
                    {
                        "user_opt_out": "Відписка від розсилки",
                        "broadcast_button": "Кнопка в розсилці",
                        "admin": "Адмін",
                        "bot_blocked": "Заблокував бота",
                        "card_deleted": "Видалив картку",
                    }.get(
                        (r.get("mailing_opt_out_reason") or "").strip(),
                        r.get("mailing_opt_out_reason") or "",
                    )
                    if int(r.get("mailing_opt_out") or 0)
                    else ""
                ),
                "Картку видалено": format_dt_ua(r.get("card_deleted_at"), empty=""),
                "Покупок (чеків)": int(r.get("purchases_count") or 0),
                "Витрачено грн": round(float(r.get("spent_uah") or 0), 2),
                "Нараховано Крафтиків": round(float(r.get("bonus_earned_uah") or 0), 2),
                "Списано Крафтиків": round(float(r.get("bonus_spent_uah") or 0), 2),
                "Крафтики на балансі": (
                    round(float(balance), 2) if balance is not None else ""
                ),
                "Баланс оновлено": format_dt_ua(r.get("last_known_bonus_at"), empty=""),
                "Улюблена кавʼярня": r.get("top_spot") or "",
                "Кавʼярні (усі)": r.get("spots_visited") or "",
                "Адмін-посилання": r.get("admin_link_name") or "",
                "Привів (Telegram ID)": r.get("referred_by_user_id") or "",
                "Привів (імʼя)": referrer_label,
                "Привів (телефон)": r.get("referrer_phone") or "",
                "Запросив друзів": int(r.get("invited_friends") or 0),
                "З них виплачено": int(r.get("invited_paid") or 0),
            }
        )

    df = pd.DataFrame(export_rows)
    current_date = datetime.now().strftime("%d.%m.%Y_%H-%M")
    filename = f"clients_export_{current_date}.xlsx"

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Клієнти", index=False)
        ws = writer.sheets["Клієнти"]

        widths = {
            "A": 14,   # Telegram ID
            "B": 16,   # Username
            "C": 22,   # Імʼя
            "D": 16,   # Телефон
            "E": 14,   # Картка
            "F": 14,   # Poster client_id
            "G": 14,   # Дата народження
            "H": 8,    # Вік
            "I": 18,   # Реєстрація
            "J": 18,   # Остання активність
            "K": 14,   # Крафтики заблоковано
            "L": 12,   # Вітальний бонус
            "M": 10,   # Бонус ДН
            "N": 14,   # Розсилка
            "O": 18,   # Дата відписки
            "P": 20,   # Причина відписки
            "Q": 16,   # Картку видалено
            "R": 12,   # Покупок
            "S": 14,   # Витрачено
            "T": 16,   # Нараховано
            "U": 14,   # Списано
            "V": 16,   # Крафтики на балансі
            "W": 18,   # Баланс оновлено
            "X": 20,   # Улюблена кавʼярня
            "Y": 28,   # Кавʼярні (усі)
            "Z": 18,   # Адмін-посилання
            "AA": 16,  # Привів (Telegram ID)
            "AB": 20,  # Привів (імʼя)
            "AC": 16,  # Привів (телефон)
            "AD": 12,  # Запросив друзів
            "AE": 12,  # З них виплачено
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width

        # Групи колонок різними відтінками шапки (легше орієнтуватись по ширині)
        style_excel_sheet(
            ws,
            header_color="35221A",
            column_group_colors={
                (1, 6): "35221A",   # профіль / ID
                (7, 10): "5C4033",  # дати
                (11, 13): "6B5344",  # прапорці
                (14, 17): "8B4513",  # розсилка / відписка
                (18, 23): "3D5A40",  # гроші / Крафтики
                (24, 25): "4A6741",  # кавʼярні
                (26, 26): "6B3A5A",  # адмін-посилання (Замок, Крафт5…)
                (27, 31): "3D5A80",  # реферали (хто привів / кого запросив)
            },
        )

    return filename, len(export_rows)

