"""
Direct Turso HTTP Client - Replaces broken SQLAlchemy libsql driver.
Uses Turso's HTTP API (Hrana protocol) for reliable database operations.
"""
import re
import requests
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# HARDCODED Turso Database Credentials
DATABASE_URL = "https://casepeerai-salehai.aws-us-east-2.turso.io"
AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzAyNTAwMzksImlkIjoiY2M5ZTE4NjctMGMwNi00MzcxLWIzZjMtMmM2MTRhOTllMTFlIiwicmlkIjoiYzgxOWZmNjYtNzViNi00NmQzLWJiZjQtMTRmNzMwNWMxOWFiIn0.lgyzL-ITZMts0H_eXBdC1d-UJ4xWDus5qQFTmND_1zZ1oOS2vEjfvUzao2jlYRVATH95hBW664nFS2h2AGkdBw"


class TursoClient:
    """Direct HTTP client for Turso database operations."""
    
    def __init__(self, db_url: str = DATABASE_URL, auth_token: str = AUTH_TOKEN):
        self.db_url = db_url
        self.auth_token = auth_token
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        # Persistent session for TCP connection reuse (avoids new TLS handshake per query)
        self._session = requests.Session()
        self._session.headers.update(self.headers)
    
    def execute(self, sql: str, params: Optional[List] = None) -> Dict[str, Any]:
        """Execute a single SQL statement."""
        stmt = {"sql": sql}
        if params:
            stmt["args"] = self._convert_params(params)
            
        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"}
            ]
        }
        
        try:
            response = self._session.post(
                f"{self.db_url}/v2/pipeline",
                json=payload,
                timeout=30
            )
            if response.status_code != 200:
                logger.error(f"Turso API Error ({response.status_code}): {response.text}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Turso execute error: {e}")
            raise
    
    def initialize_schema(self):
        """Create all necessary tables if they don't exist."""
        statements = [
            # App Settings
            {"sql": "CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT, description TEXT)"},
            # App Sessions
            {"sql": "CREATE TABLE IF NOT EXISTS app_sessions (name TEXT PRIMARY KEY, session_data TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"},
            # Cases
            {"sql": "CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, patient_name TEXT, status TEXT, fees_taken REAL DEFAULT 0, savings REAL DEFAULT 0, revenue REAL DEFAULT 0, emails_received INTEGER DEFAULT 0, emails_sent INTEGER DEFAULT 0)"},
            # (negotiations table removed — all data lives in conversation_history)
            # Classifications
            {"sql": "CREATE TABLE IF NOT EXISTS classifications (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, ocr_performed INTEGER DEFAULT 0, number_of_documents INTEGER, confidence REAL)"},
            # Reminders
            {"sql": "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, reminder_number INTEGER, reminder_date TEXT, reminder_email_body TEXT)"},
            # Token Usage
            {"sql": "CREATE TABLE IF NOT EXISTS token_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, date DATETIME DEFAULT CURRENT_TIMESTAMP, tokens_used INTEGER, cost REAL, model_name TEXT)"},
            # Case Metrics
            {"sql": "CREATE TABLE IF NOT EXISTS case_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, case_name TEXT, status TEXT, emails_received INTEGER DEFAULT 0, emails_sent INTEGER DEFAULT 0, savings REAL DEFAULT 0, revenue REAL DEFAULT 0, start_date DATETIME, end_date DATETIME, completion_time TEXT)"},
            # Conversation History — full AI chat per sender/thread for continuity
            {"sql": "CREATE TABLE IF NOT EXISTS conversation_history (id TEXT PRIMARY KEY, case_id TEXT, sender_email TEXT, thread_subject TEXT, messages_json TEXT, tools_used TEXT, last_intent TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"},
            # Workflow Runs — tracks every automated workflow execution
            {"sql": "CREATE TABLE IF NOT EXISTS workflow_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_name TEXT NOT NULL, case_id TEXT, status TEXT DEFAULT 'running', started_at DATETIME DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME, result_json TEXT, error TEXT, triggered_by TEXT DEFAULT 'scheduler')"},
            # Provider Calls — tracks Vapi phone calls to providers for email confirmation
            {"sql": """CREATE TABLE IF NOT EXISTS provider_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                provider_phone TEXT,
                existing_email TEXT,
                confirmed_email TEXT,
                vapi_call_id TEXT,
                call_type TEXT DEFAULT 'outbound_confirm',
                status TEXT DEFAULT 'queued',
                email_status TEXT DEFAULT 'pending',
                transcript TEXT,
                recording_url TEXT,
                summary TEXT,
                call_duration_seconds REAL,
                call_cost REAL,
                end_reason TEXT,
                scheduled_at TEXT,
                redirect_number TEXT,
                attempt_number INTEGER DEFAULT 1,
                metadata_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )"""},
        ]
        # Migration: add case_id column if table already exists without it
        migration_stmts = [
            {"sql": "ALTER TABLE conversation_history ADD COLUMN case_id TEXT"},
            {"sql": "DROP TABLE IF EXISTS negotiations"},
            # Indexes for provider_calls
            {"sql": "CREATE INDEX IF NOT EXISTS idx_provider_calls_case_id ON provider_calls(case_id)"},
            {"sql": "CREATE INDEX IF NOT EXISTS idx_provider_calls_vapi_call_id ON provider_calls(vapi_call_id)"},
            {"sql": "CREATE INDEX IF NOT EXISTS idx_provider_calls_status ON provider_calls(status)"},
            {"sql": "CREATE INDEX IF NOT EXISTS idx_provider_calls_scheduled ON provider_calls(scheduled_at)"},
            {"sql": "CREATE INDEX IF NOT EXISTS idx_provider_calls_phone ON provider_calls(provider_phone)"},
            # Merge known_cases into cases: add new columns to cases
            {"sql": "ALTER TABLE cases ADD COLUMN discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP"},
            {"sql": "ALTER TABLE cases ADD COLUMN classification_status TEXT DEFAULT 'pending'"},
            {"sql": "ALTER TABLE cases ADD COLUMN initial_negotiation_status TEXT DEFAULT 'pending'"},
            {"sql": "ALTER TABLE cases ADD COLUMN last_checked DATETIME"},
            {"sql": "ALTER TABLE cases ADD COLUMN casetype TEXT"},
            {"sql": "ALTER TABLE cases ADD COLUMN casestatus TEXT"},
            {"sql": "ALTER TABLE cases ADD COLUMN primary_contact TEXT"},
            {"sql": "ALTER TABLE cases ADD COLUMN doi TEXT"},
            # Migrate any existing known_cases data into cases
            {"sql": "INSERT OR IGNORE INTO cases (id, patient_name, status, discovered_at, classification_status, initial_negotiation_status, last_checked) SELECT case_id, patient_name, status, discovered_at, classification_status, initial_negotiation_status, last_checked FROM known_cases"},
            # Drop known_cases table
            {"sql": "DROP TABLE IF EXISTS known_cases"},
        ]
        try:
            self.execute_many(statements)
            # Run migrations (ignore errors for already-applied migrations)
            for m in migration_stmts:
                try:
                    self.execute(m["sql"])
                except Exception:
                    pass  # column already exists
            logger.info("[OK] Turso schema initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Turso schema: {e}")
            return False

    def execute_many(self, statements: List[Dict]) -> Dict[str, Any]:
        """Execute multiple SQL statements in a batch."""
        requests_list = []
        for stmt in statements:
            # We need to make sure we're handling the statement structure correctly
            # If stmt is just a dict with 'sql' and 'args', convert args
            sql_cmd = stmt.get("sql")
            args = stmt.get("args")
            
            s = {"sql": sql_cmd}
            if args:
                s["args"] = self._convert_params(args)
                
            requests_list.append({"type": "execute", "stmt": s})
        requests_list.append({"type": "close"})
        
        payload = {"requests": requests_list}
        
        try:
            response = self._session.post(
                f"{self.db_url}/v2/pipeline",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Turso execute_many error: {e}")
            raise
    
    def fetch_one(self, sql: str, params: Optional[List] = None) -> Optional[Dict]:
        """Fetch a single row."""
        result = self.execute(sql, params)
        rows = self._extract_rows(result)
        return rows[0] if rows else None
    
    def fetch_all(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        """Fetch all rows."""
        result = self.execute(sql, params)
        return self._extract_rows(result)
    
    def _extract_rows(self, result: Dict) -> List[Dict]:
        """Extract rows from Turso response format."""
        try:
            results = result.get("results", [])
            if not results:
                return []
            
            first_result = results[0]
            if first_result.get("type") != "ok":
                error = first_result.get("error", {})
                raise Exception(f"Query error: {error}")
            
            response = first_result.get("response", {})
            query_result = response.get("result", {})
            cols = query_result.get("cols", [])
            rows = query_result.get("rows", [])
            
            # Convert to list of dicts
            col_names = [c["name"] for c in cols]
            return [
                {col_names[i]: self._extract_value(cell) for i, cell in enumerate(row)}
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error extracting rows: {e}")
            return []
    
    def _extract_value(self, cell: Dict) -> Any:
        """Extract value from Turso cell format."""
        if cell is None:
            return None
        if isinstance(cell, dict):
            c_type = cell.get("type")
            value = cell.get("value")
            
            if c_type == "integer":
                return int(value) if value is not None else None
            elif c_type == "float":
                return float(value) if value is not None else None
            elif c_type == "blob":
                if cell.get("base64"):
                    import base64
                    return base64.b64decode(cell["base64"])
                return None
            return value
        return cell
        
    def _convert_params(self, params: List[Any]) -> List[Dict[str, Any]]:
        """Convert Python values to Turso typed arguments."""
        converted = []
        for p in params:
            if p is None:
                converted.append({"type": "null"})
            elif isinstance(p, bool):
                 # SQLite uses integers for boolean. Check bool BEFORE int because bool is a subclass of int.
                converted.append({"type": "integer", "value": "1" if p else "0"})
            elif isinstance(p, int):
                converted.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                converted.append({"type": "float", "value": p})
            elif isinstance(p, str):
                converted.append({"type": "text", "value": p})
            elif isinstance(p, bytes):
                import base64
                encoded = base64.b64encode(p).decode('utf-8')
                converted.append({"type": "blob", "base64": encoded})
            else:
                 converted.append({"type": "text", "value": str(p)})
        return converted
    
    def get_tables(self) -> List[str]:
        """Get list of table names."""
        rows = self.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [row["name"] for row in rows]
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            result = self.execute("SELECT 1")
            return True
        except:
            return False


# Global client instance
turso = TursoClient()


# App Settings helpers
def get_setting(key: str, default: str = None) -> Optional[str]:
    """Get a setting from app_settings table."""
    try:
        row = turso.fetch_one(
            "SELECT value FROM app_settings WHERE key = ?",
            [key]
        )
        return row["value"] if row else default
    except Exception as e:
        logger.warning(f"get_setting({key}) failed: {e}")
        return default


def set_setting(key: str, value: str, description: str = ""):
    """Set or update a setting in app_settings table."""
    try:
        # Check if exists
        existing = turso.fetch_one("SELECT key FROM app_settings WHERE key = ?", [key])
        if existing:
            turso.execute(
                "UPDATE app_settings SET value = ?, description = ? WHERE key = ?",
                [value, description, key]
            )
        else:
            turso.execute(
                "INSERT INTO app_settings (key, value, description) VALUES (?, ?, ?)",
                [key, value, description]
            )
        return True
    except Exception as e:
        logger.error(f"set_setting({key}) failed: {e}")
        return False


# Token Usage helpers
def get_token_usage(limit: int = 100) -> List[Dict]:
    """Get recent token usage."""
    try:
        return turso.fetch_all("SELECT * FROM token_usage ORDER BY date DESC LIMIT ?", [limit])
    except Exception as e:
        logger.error(f"get_token_usage failed: {e}")
        return []

def log_token_usage(tokens: int, cost: float, model: str):
    """Log AI token usage."""
    try:
        turso.execute(
            "INSERT INTO token_usage (tokens_used, cost, model_name) VALUES (?, ?, ?)",
            [tokens, cost, model]
        )
        return True
    except Exception as e:
        logger.error(f"log_token_usage failed: {e}")
        return False


# Session helpers
def get_session(name: str = "default") -> Optional[Dict]:
    """Get session data."""
    try:
        return turso.fetch_one(
            "SELECT * FROM app_sessions WHERE name = ?",
            [name]
        )
    except Exception as e:
        logger.warning(f"get_session failed: {e}")
        return None

def save_session(name: str, session_data: str):
    """Save or update session data (JSON string)."""
    try:
        existing = turso.fetch_one("SELECT name FROM app_sessions WHERE name = ?", [name])
        if existing:
            turso.execute(
                "UPDATE app_sessions SET session_data = ?, updated_at = datetime('now') WHERE name = ?",
                [session_data, name]
            )
        else:
            turso.execute(
                "INSERT INTO app_sessions (name, session_data) VALUES (?, ?)",
                [name, session_data]
            )
        return True
    except Exception as e:
        logger.error(f"save_session failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Phone number normalization
# ---------------------------------------------------------------------------
def normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format (+1XXXXXXXXXX for US)."""
    if not phone:
        return ""
    cleaned = re.sub(r'[^0-9+]', '', phone)
    if not cleaned.startswith('+'):
        if len(cleaned) == 10:
            cleaned = f'+1{cleaned}'
        elif len(cleaned) == 11 and cleaned.startswith('1'):
            cleaned = f'+{cleaned}'
    return cleaned


# ---------------------------------------------------------------------------
# Provider Calls helpers
# ---------------------------------------------------------------------------
def create_provider_call(case_id: str, provider_name: str, provider_phone: str,
                         existing_email: str = None, call_type: str = "outbound_confirm",
                         scheduled_at: str = None, attempt_number: int = 1,
                         metadata_json: str = None) -> Optional[int]:
    """Create a new provider_calls record. Returns the row id."""
    try:
        status = "scheduled" if scheduled_at else "queued"
        turso.execute(
            """INSERT INTO provider_calls
               (case_id, provider_name, provider_phone, existing_email, call_type,
                status, scheduled_at, attempt_number, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [case_id, provider_name, normalize_phone(provider_phone),
             existing_email, call_type, status, scheduled_at, attempt_number,
             metadata_json]
        )
        # Fetch the id of the row we just inserted
        row = turso.fetch_one("SELECT last_insert_rowid() as id")
        return row["id"] if row else None
    except Exception as e:
        logger.error(f"create_provider_call failed: {e}")
        return None


def update_provider_call(call_id: int, **fields) -> bool:
    """Update provider_calls by id with arbitrary fields."""
    if not fields:
        return False
    try:
        set_parts = []
        values = []
        for k, v in fields.items():
            set_parts.append(f"{k} = ?")
            values.append(v)
        set_parts.append("updated_at = datetime('now')")
        values.append(call_id)
        turso.execute(
            f"UPDATE provider_calls SET {', '.join(set_parts)} WHERE id = ?",
            values
        )
        return True
    except Exception as e:
        logger.error(f"update_provider_call({call_id}) failed: {e}")
        return False


def get_provider_call_by_vapi_id(vapi_call_id: str) -> Optional[Dict]:
    """Fetch a single provider_calls record by vapi_call_id."""
    if not vapi_call_id:
        return None
    try:
        rows = turso.fetch_all(
            "SELECT * FROM provider_calls WHERE vapi_call_id = ? LIMIT 1",
            [vapi_call_id]
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.error(f"get_provider_call_by_vapi_id({vapi_call_id}) failed: {e}")
        return None


def update_provider_call_by_vapi_id(vapi_call_id: str, **fields) -> bool:
    """Update provider_calls by vapi_call_id (for webhook handler)."""
    if not fields or not vapi_call_id:
        return False
    try:
        set_parts = []
        values = []
        for k, v in fields.items():
            set_parts.append(f"{k} = ?")
            values.append(v)
        set_parts.append("updated_at = datetime('now')")
        values.append(vapi_call_id)
        turso.execute(
            f"UPDATE provider_calls SET {', '.join(set_parts)} WHERE vapi_call_id = ?",
            values
        )
        return True
    except Exception as e:
        logger.error(f"update_provider_call_by_vapi_id({vapi_call_id}) failed: {e}")
        return False


def get_provider_calls(case_id: str = None, status: str = None,
                       email_status: str = None, limit: int = 100) -> List[Dict]:
    """Fetch provider_calls with optional filters."""
    try:
        conditions = []
        params = []
        if case_id:
            conditions.append("case_id = ?")
            params.append(case_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if email_status:
            conditions.append("email_status = ?")
            params.append(email_status)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        return turso.fetch_all(
            f"SELECT * FROM provider_calls{where} ORDER BY created_at DESC LIMIT ?",
            params
        )
    except Exception as e:
        logger.error(f"get_provider_calls failed: {e}")
        return []


def find_provider_by_phone(phone: str) -> Optional[Dict]:
    """Find the most relevant provider_calls record by phone number.
    Prefers active calls, then most recent pending call."""
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    try:
        # First try active calls (queued, ringing, in_progress)
        row = turso.fetch_one(
            """SELECT * FROM provider_calls
               WHERE (provider_phone = ? OR redirect_number = ?)
                 AND status IN ('queued', 'ringing', 'in_progress')
               ORDER BY created_at DESC LIMIT 1""",
            [normalized, normalized]
        )
        if row:
            return row
        # Fallback: most recent pending email status
        row = turso.fetch_one(
            """SELECT * FROM provider_calls
               WHERE (provider_phone = ? OR redirect_number = ?)
                 AND email_status = 'pending'
               ORDER BY created_at DESC LIMIT 1""",
            [normalized, normalized]
        )
        if row:
            return row
        # Last resort: any recent call from this number
        return turso.fetch_one(
            """SELECT * FROM provider_calls
               WHERE (provider_phone = ? OR redirect_number = ?)
               ORDER BY created_at DESC LIMIT 1""",
            [normalized, normalized]
        )
    except Exception as e:
        logger.error(f"find_provider_by_phone({phone}) failed: {e}")
        return None


def get_scheduled_calls_due() -> List[Dict]:
    """Get all calls where status='scheduled' AND scheduled_at <= now."""
    try:
        return turso.fetch_all(
            """SELECT * FROM provider_calls
               WHERE status = 'scheduled' AND scheduled_at <= datetime('now')
               ORDER BY scheduled_at ASC"""
        )
    except Exception as e:
        logger.error(f"get_scheduled_calls_due failed: {e}")
        return []
