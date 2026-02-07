"""
Direct Turso HTTP Client - Replaces broken SQLAlchemy libsql driver.
Uses Turso's HTTP API (Hrana protocol) for reliable database operations.
"""
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
            response = requests.post(
                f"{self.db_url}/v2/pipeline",
                headers=self.headers,
                json=payload,
                timeout=30
            )
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
            # Negotiations
            {"sql": "CREATE TABLE IF NOT EXISTS negotiations (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, negotiation_type TEXT, \"to\" TEXT, email_body TEXT, date TEXT, actual_bill REAL, offered_bill REAL, sent_by_us INTEGER DEFAULT 1, result TEXT)"},
            # Classifications
            {"sql": "CREATE TABLE IF NOT EXISTS classifications (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, ocr_performed INTEGER DEFAULT 0, number_of_documents INTEGER, confidence REAL)"},
            # Reminders
            {"sql": "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, reminder_number INTEGER, reminder_date TEXT, reminder_email_body TEXT)"},
            # Token Usage
            {"sql": "CREATE TABLE IF NOT EXISTS token_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, date DATETIME DEFAULT CURRENT_TIMESTAMP, tokens_used INTEGER, cost REAL, model_name TEXT)"},
            # Case Metrics
            {"sql": "CREATE TABLE IF NOT EXISTS case_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, case_name TEXT, status TEXT, emails_received INTEGER DEFAULT 0, emails_sent INTEGER DEFAULT 0, savings REAL DEFAULT 0, revenue REAL DEFAULT 0, start_date DATETIME, end_date DATETIME, completion_time TEXT)"}
        ]
        try:
            self.execute_many(statements)
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
            response = requests.post(
                f"{self.db_url}/v2/pipeline",
                headers=self.headers,
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
            elif isinstance(p, bool):
                 # SQLite uses integers for boolean
                converted.append({"type": "integer", "value": "1" if p else "0"})
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
