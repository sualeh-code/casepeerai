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
            stmt["args"] = params
            
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
    
    def execute_many(self, statements: List[Dict]) -> Dict[str, Any]:
        """Execute multiple SQL statements in a batch."""
        requests_list = []
        for stmt in statements:
            requests_list.append({"type": "execute", "stmt": stmt})
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
            return cell.get("value")
        return cell
    
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


def get_all_settings() -> List[Dict]:
    """Get all settings."""
    try:
        return turso.fetch_all("SELECT key, value, description FROM app_settings")
    except Exception as e:
        logger.error(f"get_all_settings failed: {e}")
        return []


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


def save_session(name: str, access_token: str, refresh_token: str = None, csrf_token: str = None):
    """Save or update session."""
    try:
        existing = turso.fetch_one("SELECT name FROM app_sessions WHERE name = ?", [name])
        if existing:
            turso.execute(
                "UPDATE app_sessions SET access_token = ?, refresh_token = ?, csrf_token = ?, updated_at = datetime('now') WHERE name = ?",
                [access_token, refresh_token, csrf_token, name]
            )
        else:
            turso.execute(
                "INSERT INTO app_sessions (name, access_token, refresh_token, csrf_token) VALUES (?, ?, ?, ?)",
                [name, access_token, refresh_token, csrf_token]
            )
        return True
    except Exception as e:
        logger.error(f"save_session failed: {e}")
        return False
