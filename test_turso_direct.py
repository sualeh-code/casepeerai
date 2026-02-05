"""
Direct Turso connection test using the credentials provided.
This bypasses the .env file completely to verify the database.
"""
import os

# Set credentials directly (from user)
os.environ["DATABASE_URL"] = "libsql://casepeerai-salehai.aws-us-east-2.turso.io"
os.environ["TURSO_AUTH_TOKEN"] = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzAyNTAwMzksImlkIjoiY2M5ZTE4NjctMGMwNi00MzcxLWIzZjMtMmM2MTRhOTllMTFlIiwicmlkIjoiYzgxOWZmNjYtNzViNi00NmQzLWJiZjQtMTRmNzMwNWMxOWFiIn0.lgyzL-ITZMts0H_eXBdC1d-UJ4xWDus5qQFTmND_1zZ1oOS2vEjfvUzao2jlYRVATH95hBW664nFS2h2AGkdBw"

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

# Build connection URL
base_url = "https://casepeerai-salehai.aws-us-east-2.turso.io"
auth_token = os.environ["TURSO_AUTH_TOKEN"]
url = f"sqlite+libsql://?url={base_url}&auth_token={auth_token}"

print(f"Connecting to: {base_url}")

try:
    engine = create_engine(url, poolclass=NullPool)
    
    # Test connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        print(f"✓ Connection successful (SELECT 1 = {result})")
    
    # List tables
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n📋 Tables found: {tables}")
    
    if tables:
        for table in tables:
            cols = inspector.get_columns(table)
            print(f"  - {table}: {[c['name'] for c in cols]}")
    else:
        print("⚠ No tables found in database!")
        
except Exception as e:
    print(f"❌ Error: {e}")
