from datetime import datetime
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from database_functions.admin_db import get_all_users_data, get_all_links_data, get_statistics_summary
from database_functions.loyalty_stats_db import fetch_poster_bonus_balances, get_loyalty_statistics_summary
import pandas as pd


def format_message_text(message) -> str:
    """
    Повертає текст повідомлення (text або caption), відформатований через format_entities.
    Використовувати для всіх повідомлень адміна при редагуванні контенту та розсилках.
    Зберігає теги форматування та premium (custom_emoji).
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
    print(text)
    print(entities)
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
            
            # Для custom_emoji entity_text може містити невидимий placeholder
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
        # Зберігаємо custom_emoji_id для відправки преміум емодзі від бота
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


def generate_database_export():
    users_data, users_columns = get_all_users_data()
    links_data, links_columns = get_all_links_data()
    
    users_df = pd.DataFrame(users_data, columns=users_columns)
    links_df = pd.DataFrame(links_data, columns=links_columns)
    
    current_date = datetime.now().strftime('%d.%m.%Y_%H-%M')
    filename = f'database_export_{current_date}.xlsx'
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        users_df.to_excel(writer, sheet_name='Користувачі', index=False)
        links_df.to_excel(writer, sheet_name='Посилання', index=False)
        
        workbook = writer.book
        
        worksheet_users = writer.sheets['Користувачі']
        
        column_widths = {
            'A': 12,  # id
            'B': 15,  # user_id
            'C': 20,  # user_name
            'D': 20,  # user_first_name
            'E': 20,  # user_last_name
            'F': 15,  # user_phone
            'G': 10,  # language
            'H': 20,  # join_date
            'I': 20,  # last_activity
            'J': 15   # ref_link
        }
        
        for col, width in column_widths.items():
            worksheet_users.column_dimensions[col].width = width
        
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")
        
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for cell in worksheet_users[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border
        
        for row in worksheet_users.iter_rows(min_row=2, max_row=worksheet_users.max_row, 
                                             min_col=1, max_col=len(users_columns)):
            for cell in row:
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")
        
        if not links_df.empty:
            worksheet_links = writer.sheets['Посилання']
            
            link_column_widths = {
                'A': 12,  # id
                'B': 30,  # link_name
                'C': 50   # link_url
            }
            
            for col, width in link_column_widths.items():
                worksheet_links.column_dimensions[col].width = width
            
            for cell in worksheet_links[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = thin_border
            
            for row in worksheet_links.iter_rows(min_row=2, max_row=worksheet_links.max_row, 
                                                 min_col=1, max_col=len(links_columns)):
                for cell in row:
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")
    
    return filename, len(users_df), len(links_df)


def _uah(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def format_statistics_message():
    stats = get_statistics_summary()
    loyalty = get_loyalty_statistics_summary()
    poster_bal = fetch_poster_bonus_balances()
    
    language_emoji = {
        'uk': '🇺🇦',
        'ru': '🇷',
        'en': '🇬🇧',
        'pl': '🇵🇱',
        'de': '🇩🇪',
        'fr': '🇫🇷',
        'es': '🇪🇸',
        'it': '🇮🇹'
    }
    
    languages_text = ""
    for lang, count in stats['languages']:
        emoji = language_emoji.get(lang, '🌐')
        percentage = (count / stats['total_users'] * 100) if stats['total_users'] > 0 else 0
        languages_text += f"   {emoji} {lang or 'Невідомо'}: {count} ({percentage:.1f}%)"
    
    top_links_text = ""
    if stats['top_links']:
        for i, (link_name, clicks) in enumerate(stats['top_links'], 1):
            top_links_text += f"   {i}. {link_name}: {clicks} переходів"
    else:
        top_links_text = "   Немає даних\n"
    
    phone_percentage = (stats['users_with_phone'] / stats['total_users'] * 100) if stats['total_users'] > 0 else 0
    links_percentage = (stats['users_from_links'] / stats['total_users'] * 100) if stats['total_users'] > 0 else 0
    
    reg = loyalty["registered_clients"]
    reg_pct = (reg / stats["total_users"] * 100) if stats["total_users"] > 0 else 0
    poster_line = (
        f"• На балансах у Poster зараз: <b>{_uah(poster_bal['outstanding_bonus_uah'])} грн</b> "
        f"({poster_bal['clients_with_bonus_balance']} клієнтів з бонусами)"
    )
    if poster_bal["poster_errors"]:
        poster_line += f"\n   ⚠️ Не вдалося оновити {poster_bal['poster_errors']} карток"

    message = f"""<b>📊 ДЕТАЛЬНА СТАТИСТИКА БОТА</b>

<b>👥 ЗАГАЛЬНА ІНФОРМАЦІЯ</b>
• Всього користувачів: <b>{stats['total_users']}</b>
• З номером телефону: <b>{stats['users_with_phone']}</b> ({phone_percentage:.1f}%)

<b>☕ КЛІЄНТИ ТА ЛОЯЛЬНІСТЬ</b>
• У програмі лояльності: <b>{reg}</b> ({reg_pct:.1f}% від усіх у боті)
• Купували (чеки через бот): <b>{loyalty['buyers_unique']}</b>
• Повертаються (≥2 покупки): <b>{loyalty['returning_clients']}</b> — <b>{loyalty['return_rate_percent']:.1f}%</b> від покупців
• Чеків загалом: <b>{loyalty['purchases_total']}</b> на <b>{_uah(loyalty['payed_total_uah'])} грн</b>

<b>🎁 БОНУСИ</b>
• Нараховано кешбеку (бот): <b>{_uah(loyalty['cashback_accrued_uah'])} грн</b>
• Списано бонусів у чеках: <b>{_uah(loyalty['bonus_spent_uah'])} грн</b>
• Вітальні бонуси: <b>{loyalty['welcome_count']}</b> видач (~<b>{_uah(loyalty['welcome_total_est_uah'])} грн</b> за поточним тарифом)
{poster_line}

<b>🛒 ПОКУПКИ (клієнти бота)</b>
• Сьогодні: <b>{loyalty['purchases_today']}</b> чеків, <b>{loyalty['buyers_today']}</b> клієнтів, <b>{_uah(loyalty['payed_today_uah'])} грн</b>
• За 7 днів: <b>{loyalty['purchases_week']}</b> чеків, <b>{loyalty['buyers_week']}</b> клієнтів, <b>{_uah(loyalty['payed_week_uah'])} грн</b>
• За 30 днів: <b>{loyalty['purchases_month']}</b> чеків, <b>{loyalty['buyers_month']}</b> клієнтів, <b>{_uah(loyalty['payed_month_uah'])} грн</b>

<b>📈 НОВІ КОРИСТУВАЧІ</b>
• За сьогодні: <b>{stats['new_today']}</b>
• За тиждень: <b>{stats['new_week']}</b>
• За місяць: <b>{stats['new_month']}</b>

<b>⚡️ АКТИВНІ КОРИСТУВАЧІ</b>
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

<i>📅 Оновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"""
    
    return message



