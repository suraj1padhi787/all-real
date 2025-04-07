import sqlite3
from config import DB_PATH, ADMIN_ID

# 🔧 Initialize DB (called from bot.py)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Sessions Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER,
            session_string TEXT,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Admins Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)

    # Proxies Table (initial columns)
    c.execute("""
        CREATE TABLE IF NOT EXISTS proxies (
            user_id INTEGER,
            proxy_type TEXT,
            ip TEXT,
            port INTEGER
        )
    """)

    # ✅ Safe add missing columns (username, password)
    try:
        c.execute("ALTER TABLE proxies ADD COLUMN username TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE proxies ADD COLUMN password TEXT")
    except:
        pass

    conn.commit()
    conn.close()

# 💾 Save new session
def save_session(user_id, session_string):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (user_id, session_string) VALUES (?, ?)", (user_id, session_string))
    conn.commit()
    conn.close()

# 📥 Get session by user_id
def get_session(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_string FROM sessions WHERE user_id = ? ORDER BY created DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# 📋 Get all sessions
def get_all_sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, session_string FROM sessions")
    rows = c.fetchall()
    conn.close()
    return rows

# ❌ Delete session by string
def delete_session_by_string(session_string):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE session_string = ?", (session_string,))
    conn.commit()
    conn.close()

def delete_session_by_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    rows_affected = c.rowcount
    conn.close()
    return rows_affected > 0

# 👑 Admins
def init_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

def add_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in get_all_admins()

# 🔐 Proxies (with username + password support)
def save_user_proxies_to_db(user_id, proxy_list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM proxies WHERE user_id = ?", (user_id,))
    c.executemany(
        "INSERT INTO proxies (user_id, proxy_type, ip, port, username, password) VALUES (?, ?, ?, ?, ?, ?)",
        [(user_id, p[0], p[1], p[2], p[3], p[4]) for p in proxy_list]
    )
    conn.commit()
    conn.close()

def get_user_proxies_from_db(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT proxy_type, ip, port, username, password FROM proxies WHERE user_id = ?", (user_id,))
    proxies = c.fetchall()
    conn.close()
    return proxies
# 🔁 Load all proxies for all users
def get_all_user_proxies():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, proxy_type, ip, port, username, password FROM proxies")
    rows = c.fetchall()
    conn.close()

    proxy_dict = {}
    for user_id, proxy_type, ip, port, username, password in rows:
        if user_id not in proxy_dict:
            proxy_dict[user_id] = []
        proxy_dict[user_id].append((proxy_type, ip, port, username, password))
    return proxy_dict

