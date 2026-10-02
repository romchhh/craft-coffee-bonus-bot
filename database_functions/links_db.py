import sqlite3


conn = sqlite3.connect('database/data.db')
cursor = conn.cursor()


def create_table_links():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY,
            link_name TEXT,
            link_url TEXT,
            link_count INTEGER
        )
    ''')
    conn.commit()


def add_link(link_name: str, link_url: str = None):
    cursor.execute('INSERT INTO links (link_name, link_url, link_count) VALUES (?, ?, ?)', 
                  (link_name, None, 0))
    conn.commit()
    return cursor.lastrowid


def get_all_links():
    cursor.execute('SELECT * FROM links')
    return cursor.fetchall()


def increment_link_count(link_id: int):
    cursor.execute('UPDATE links SET link_count = link_count + 1 WHERE id = ?', (link_id,))
    conn.commit()


def get_link_stats():
    cursor.execute('SELECT link_name, link_count FROM links')
    return cursor.fetchall()


def get_link_detailed_stats():
    cursor.execute('SELECT id, link_name, link_count FROM links')
    return cursor.fetchall()


def get_link_by_id(link_id: int):
    cursor.execute('SELECT link_name, link_url FROM links WHERE id = ?', (link_id,))
    return cursor.fetchone()


def update_link_name(link_id: int, new_name: str):
    cursor.execute('UPDATE links SET link_name = ? WHERE id = ?', (new_name, link_id))
    conn.commit()


def delete_link(link_id: int):
    cursor.execute('DELETE FROM links WHERE id = ?', (link_id,))
    conn.commit()

def get_users_by_language():
    cursor.execute("SELECT language, COUNT(*) FROM users GROUP BY language")
    return cursor.fetchall()