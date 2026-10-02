import sqlite3
from datetime import datetime, timedelta
from database_functions.client_db import get_user_id_by_username, get_username_by_user_id       

conn = sqlite3.connect('database/data.db')
cursor = conn.cursor()


def get_users_count():
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    return count

def get_all_user_ids():
    cursor.execute('SELECT user_id FROM users')
    user_ids = [row[0] for row in cursor.fetchall()]
    return user_ids


def get_all_users_data():
    cursor.execute('SELECT * FROM users')
    users_data = cursor.fetchall()
    users_columns = [description[0] for description in cursor.description]
    return users_data, users_columns


def get_all_links_data():
    # Отримуємо дані без поля link_count (статистика)
    cursor.execute('SELECT id, link_name, link_url FROM links')
    links_data = cursor.fetchall()
    links_columns = [description[0] for description in cursor.description]
    return links_data, links_columns


def get_new_users_count(days: int):
    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= ?", (date_threshold,))
    count = cursor.fetchone()[0]
    return count


def get_active_users_count(days: int):
    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_activity >= ?", (date_threshold,))
    count = cursor.fetchone()[0]
    return count


def get_users_with_phone():
    cursor.execute("SELECT COUNT(*) FROM users WHERE user_phone IS NOT NULL AND user_phone != ''")
    count = cursor.fetchone()[0]
    return count


def get_users_by_language():
    cursor.execute("SELECT language, COUNT(*) FROM users GROUP BY language ORDER BY COUNT(*) DESC")
    return cursor.fetchall()


def get_total_links_count():
    cursor.execute("SELECT COUNT(*) FROM links")
    count = cursor.fetchone()[0]
    return count


def get_total_link_clicks():
    cursor.execute("SELECT COALESCE(SUM(link_count), 0) FROM links")
    count = cursor.fetchone()[0]
    return count


def get_top_links(limit: int = 5):
    cursor.execute("SELECT link_name, link_count FROM links ORDER BY link_count DESC LIMIT ?", (limit,))
    return cursor.fetchall()


def get_users_with_ref_link():
    cursor.execute("SELECT COUNT(*) FROM users WHERE ref_link IS NOT NULL")
    count = cursor.fetchone()[0]
    return count


def get_statistics_summary():
    total_users = get_users_count()
    new_today = get_new_users_count(1)
    new_week = get_new_users_count(7)
    new_month = get_new_users_count(30)
    
    active_today = get_active_users_count(1)
    active_week = get_active_users_count(7)
    active_month = get_active_users_count(30)
    
    users_with_phone = get_users_with_phone()
    languages = get_users_by_language()
    
    total_links = get_total_links_count()
    total_clicks = get_total_link_clicks()
    top_links = get_top_links(5)
    users_from_links = get_users_with_ref_link()
    
    return {
        'total_users': total_users,
        'new_today': new_today,
        'new_week': new_week,
        'new_month': new_month,
        'active_today': active_today,
        'active_week': active_week,
        'active_month': active_month,
        'users_with_phone': users_with_phone,
        'languages': languages,
        'total_links': total_links,
        'total_clicks': total_clicks,
        'top_links': top_links,
        'users_from_links': users_from_links
    }


def create_admins_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE,
            username TEXT,
            added_by INTEGER,
            added_date TEXT,
            is_superadmin INTEGER DEFAULT 0
        )
    ''')
    conn.commit()


def add_admin(user_id, username, added_by):
    try:
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Спочатку знаходимо user_id якщо передано username
        if not user_id and username:
            found_user_id = get_user_id_by_username(username)
            if found_user_id:
                user_id = found_user_id
            else:
                return "not_found"  # Користувач не знайдений в базі
        
        # Перевіряємо чи користувач існує в базі даних
        if user_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                return "not_found"  # Користувач не знайдений в базі
        else:
            return "not_found"
        
        # Перевіряємо чи вже є адміністратором
        existing_admin = None
        if user_id:
            existing_admin = get_admin_by_id(user_id)
        if not existing_admin and username:
            existing_admin = get_admin_by_id(get_user_id_by_username(username))

        if existing_admin:
            return "already_admin"  # Вже є адміністратором

        if not username and user_id:
            cursor.execute("SELECT user_name FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            if result:
                username = result[0]
        
        cursor.execute(
            "INSERT INTO admins (user_id, username, added_by, added_date) VALUES (?, ?, ?, ?)",
            (user_id, username, added_by, current_date)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_admin(user_id):
    try:
        cursor.execute("SELECT is_superadmin FROM admins WHERE user_id = ?", (user_id,))
        admin_data = cursor.fetchone()
        
        if admin_data and admin_data[0] == 1:
            return False
            
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        if cursor.rowcount > 0:
            conn.commit()
            return True
        return False
    except Exception:
        return False


def get_admin_by_id(user_id):
    if not user_id:
        return None
    cursor.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone()


def get_all_admins():
    cursor.execute("""
        SELECT a.user_id, a.username, a.added_date, a.is_superadmin, 
               u.user_name as added_by_username,
               u2.user_name as admin_user_name
        FROM admins a
        LEFT JOIN users u ON a.added_by = u.user_id
        LEFT JOIN users u2 ON a.user_id = u2.user_id
        ORDER BY a.is_superadmin DESC, a.added_date DESC
    """)
    return cursor.fetchall()


def get_admin_info_by_id(admin_id):
    cursor.execute("""
        SELECT a.user_id, a.username, a.added_date, a.is_superadmin, a.added_by,
               u.user_name as current_username
        FROM admins a
        LEFT JOIN users u ON a.user_id = u.user_id
        WHERE a.user_id = ?
    """, (admin_id,))
    return cursor.fetchone()

def is_superadmin(user_id):
    cursor.execute("SELECT is_superadmin FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1


def get_superadmin_user_id():
    cursor.execute("SELECT user_id FROM admins WHERE is_superadmin = 1 LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row else None


def transfer_superadmin(new_superadmin_id: int, acting_user_id: int) -> bool:
    if not is_superadmin(acting_user_id):
        return False
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (new_superadmin_id,))
    if not cursor.fetchone():
        return False
    try:
        cursor.execute("UPDATE admins SET is_superadmin = 0")
        cursor.execute(
            "UPDATE admins SET is_superadmin = 1 WHERE user_id = ?",
            (new_superadmin_id,),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False


def init_superadmin(superadmin_id):
    try:
        cursor.execute("SELECT user_id FROM admins WHERE is_superadmin = 1")
        if cursor.fetchone():
            return False
        
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        username = get_username_by_user_id(superadmin_id)
        
        cursor.execute(
            "INSERT OR IGNORE INTO admins (user_id, username, added_by, added_date, is_superadmin) VALUES (?, ?, ?, ?, 1)",
            (superadmin_id, username, superadmin_id, current_date)
        )
        conn.commit()
        return True
    except Exception:
        return False


def get_all_admin_ids():
    cursor.execute("SELECT user_id FROM admins")
    return [row[0] for row in cursor.fetchall()]


def get_all_administrators():
    return get_all_admin_ids()


