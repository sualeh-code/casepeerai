"""
Test Turso database connection via HTTP API (no driver needed).
"""
import requests
import json

# Credentials from user
DB_URL = "https://casepeerai-salehai.aws-us-east-2.turso.io"
AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzAyNTAwMzksImlkIjoiY2M5ZTE4NjctMGMwNi00MzcxLWIzZjMtMmM2MTRhOTllMTFlIiwicmlkIjoiYzgxOWZmNjYtNzViNi00NmQzLWJiZjQtMTRmNzMwNWMxOWFiIn0.lgyzL-ITZMts0H_eXBdC1d-UJ4xWDus5qQFTmND_1zZ1oOS2vEjfvUzao2jlYRVATH95hBW664nFS2h2AGkdBw"

def query_turso(sql):
    """Execute SQL via Turso HTTP API."""
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql}},
            {"type": "close"}
        ]
    }
    
    response = requests.post(f"{DB_URL}/v2/pipeline", headers=headers, json=payload)
    return response.json()

print(f"Connecting to: {DB_URL}")
print("-" * 50)

# Test 1: List all tables
print("\n📋 Listing tables...")
result = query_turso("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print(json.dumps(result, indent=2))

# Test 2: Check app_settings specifically
print("\n🔍 Checking app_settings table...")
try:
    result2 = query_turso("SELECT * FROM app_settings LIMIT 5")
    print(json.dumps(result2, indent=2))
except Exception as e:
    print(f"Error: {e}")
