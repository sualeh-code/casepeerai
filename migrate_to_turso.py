import sqlite3
import libsql_client
import os
import json
from datetime import datetime

# Turso Config
# Using https:// to avoid WSServerHandshakeError 505 on regional URLs
TURSO_URL = os.getenv("DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

LOCAL_DB = "casepeer.db"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS case_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_name TEXT,
        status TEXT,
        emails_received INTEGER DEFAULT 0,
        emails_sent INTEGER DEFAULT 0,
        savings REAL DEFAULT 0.0,
        revenue REAL DEFAULT 0.0,
        start_date TEXT,
        end_date TEXT,
        completion_time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        description TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY,
        patient_name TEXT,
        status TEXT,
        fees_taken REAL DEFAULT 0.0,
        savings REAL DEFAULT 0.0
    )""",
    """CREATE TABLE IF NOT EXISTS negotiations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        negotiation_type TEXT,
        "to" TEXT,
        email_body TEXT,
        date TEXT,
        actual_bill REAL,
        offered_bill REAL,
        sent_by_us BOOLEAN DEFAULT 1,
        result TEXT,
        FOREIGN KEY(case_id) REFERENCES cases(id)
    )""",
    """CREATE TABLE IF NOT EXISTS classifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        ocr_performed BOOLEAN DEFAULT 0,
        number_of_documents INTEGER,
        confidence REAL,
        FOREIGN KEY(case_id) REFERENCES cases(id)
    )""",
    """CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT,
        reminder_number INTEGER,
        reminder_date TEXT,
        reminder_email_body TEXT,
        FOREIGN KEY(case_id) REFERENCES cases(id)
    )""",
    """CREATE TABLE IF NOT EXISTS token_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        tokens_used INTEGER,
        cost REAL,
        model_name TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS app_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_data TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
]

def migrate():
    print(f"Connecting to Turso: {TURSO_URL}")
    client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    
    # 1. Create Schema
    print("Creating schema on Turso...")
    for stmt in SCHEMA:
        client.execute(stmt)
    
    # 2. Migrate Data
    if not os.path.exists(LOCAL_DB):
        print(f"Local database {LOCAL_DB} not found. Schema initialized only.")
        return

    print(f"Migrating data from {LOCAL_DB}...")
    local_conn = sqlite3.connect(LOCAL_DB)
    local_cursor = local_conn.cursor()
    
    tables = [
        "case_metrics", "app_settings", "cases", "negotiations", 
        "classifications", "reminders", "token_usage", "app_sessions"
    ]
    
    for table in tables:
        print(f"Migrating table: {table}...")
        local_cursor.execute(f"SELECT * FROM {table}")
        rows = local_cursor.fetchall()
        
        if not rows:
            print(f"  Table {table} is empty. Skipping.")
            continue
            
        # Get column names
        local_cursor.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in local_cursor.fetchall()]
        col_str = ", ".join([f'"{c}"' for c in cols])
        placeholder_str = ", ".join(["?" for _ in cols])
        
        insert_sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholder_str})"
        
        for row in rows:
            client.execute(insert_sql, row)
            
        print(f"  Successfully migrated {len(rows)} rows to {table}.")
    
    local_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
