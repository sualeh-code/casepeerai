from typing import List, Optional, Dict, Any
import schemas
from turso_client import turso

# APP SETTINGS CRUD
def get_setting(db, key: str):
    """Get a setting using TursoClient."""
    row = turso.fetch_one("SELECT key, value, description FROM app_settings WHERE key = ?", [key])
    if not row:
        return None
    # Return an object-like structure for compatibility with existing code
    class Setting:
        def __init__(self, key, value, description):
            self.key = key
            self.value = value
            self.description = description
    return Setting(row["key"], row["value"], row["description"])

def set_setting(db, setting: schemas.AppSettingCreate):
    """Set or update a setting using TursoClient."""
    existing = turso.fetch_one("SELECT key FROM app_settings WHERE key = ?", [setting.key])
    if existing:
        turso.execute(
            "UPDATE app_settings SET value = ?, description = ? WHERE key = ?",
            [setting.value, setting.description or "", setting.key]
        )
    else:
        turso.execute(
            "INSERT INTO app_settings (key, value, description) VALUES (?, ?, ?)",
            [setting.key, setting.value, setting.description or ""]
        )
    return get_setting(db, setting.key)

# CASE CRUD (models.Case)
def get_all_cases(db, skip: int = 0, limit: int = 100) -> List[Dict]:
    """Get all cases."""
    return turso.fetch_all("SELECT * FROM cases LIMIT ? OFFSET ?", [limit, skip])

def get_case_by_id(db, case_id: str) -> Optional[Dict]:
    """Get a case by ID."""
    return turso.fetch_one("SELECT * FROM cases WHERE id = ?", [case_id])

def create_new_case(db, case: schemas.CaseCreate):
    """Create or update a case."""
    existing = get_case_by_id(db, case.id)
    case_dict = case.dict()
    
    # Generate SQL for dynamic columns
    cols = ", ".join(case_dict.keys())
    placeholders = ", ".join(["?" for _ in case_dict])
    vals = list(case_dict.values())
    
    if existing:
        # Update
        updates = ", ".join([f"{k} = ?" for k in case_dict.keys()])
        turso.execute(f"UPDATE cases SET {updates} WHERE id = ?", vals + [case.id])
    else:
        # Insert
        turso.execute(f"INSERT INTO cases ({cols}) VALUES ({placeholders})", vals)
    
    return get_case_by_id(db, case.id)

# CASE METRIC CRUD (Legacy/Migration compatibility)
def get_case_metric(db, case_id: int):
    return turso.fetch_one("SELECT * FROM case_metrics WHERE id = ?", [case_id])

def create_case_metric(db, case: schemas.CaseMetricCreate):
    case_dict = case.dict()
    cols = ", ".join(case_dict.keys())
    placeholders = ", ".join(["?" for _ in case_dict])
    vals = list(case_dict.values())
    turso.execute(f"INSERT INTO case_metrics ({cols}) VALUES ({placeholders})", vals)
    # Get last inserted id (Turso pipeline doesn't return it easily, so we query)
    return turso.fetch_one("SELECT * FROM case_metrics ORDER BY id DESC LIMIT 1")

# NEGOTIATION CRUD
def create_negotiation(db, negotiation: schemas.NegotiationCreate):
    neg_dict = negotiation.dict()
    cols = ", ".join(neg_dict.keys())
    placeholders = ", ".join(["?" for _ in neg_dict])
    vals = list(neg_dict.values())
    turso.execute(f"INSERT INTO negotiations ({cols}) VALUES ({placeholders})", vals)
    return turso.fetch_one("SELECT * FROM negotiations WHERE case_id = ? ORDER BY id DESC LIMIT 1", [negotiation.case_id])

def get_negotiations_by_case(db, case_id: str):
    return turso.fetch_all("SELECT * FROM negotiations WHERE case_id = ?", [case_id])

# CLASSIFICATION CRUD
def create_classification(db, classification: schemas.ClassificationCreate):
    cls_dict = classification.dict()
    cols = ", ".join(cls_dict.keys())
    placeholders = ", ".join(["?" for _ in cls_dict])
    vals = list(cls_dict.values())
    turso.execute(f"INSERT INTO classifications ({cols}) VALUES ({placeholders})", vals)
    return turso.fetch_one("SELECT * FROM classifications WHERE case_id = ? ORDER BY id DESC LIMIT 1", [classification.case_id])

def get_classifications_by_case(db, case_id: str):
    return turso.fetch_all("SELECT * FROM classifications WHERE case_id = ?", [case_id])

# REMINDER CRUD
def create_reminder(db, reminder: schemas.ReminderCreate):
    rem_dict = reminder.dict()
    cols = ", ".join(rem_dict.keys())
    placeholders = ", ".join(["?" for _ in rem_dict])
    vals = list(rem_dict.values())
    turso.execute(f"INSERT INTO reminders ({cols}) VALUES ({placeholders})", vals)
    return turso.fetch_one("SELECT * FROM reminders WHERE case_id = ? ORDER BY id DESC LIMIT 1", [reminder.case_id])

def get_reminders_by_case(db, case_id: str):
    return turso.fetch_all("SELECT * FROM reminders WHERE case_id = ?", [case_id])

# TOKEN USAGE CRUD
def create_token_usage(db, usage: schemas.TokenUsageCreate):
    usage_dict = usage.dict()
    cols = ", ".join(usage_dict.keys())
    placeholders = ", ".join(["?" for _ in usage_dict])
    vals = list(usage_dict.values())
    turso.execute(f"INSERT INTO token_usage ({cols}) VALUES ({placeholders})", vals)
    return turso.fetch_one("SELECT * FROM token_usage ORDER BY id DESC LIMIT 1")

# SESSION CRUD
def save_session(db, session_data: str):
    existing = turso.fetch_one("SELECT * FROM app_sessions WHERE name = 'default'")
    if existing:
        turso.execute(
            "UPDATE app_sessions SET session_data = ?, updated_at = datetime('now') WHERE name = 'default'",
            [session_data]
        )
    else:
        turso.execute(
            "INSERT INTO app_sessions (name, session_data) VALUES ('default', ?)",
            [session_data]
        )
    return turso.fetch_one("SELECT * FROM app_sessions WHERE name = 'default'")

def get_latest_session(db):
    return turso.fetch_one("SELECT * FROM app_sessions ORDER BY updated_at DESC LIMIT 1")

