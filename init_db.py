import models
from database import engine, Base
import os

def init_db():
    print(f"Initializing database at: {engine.url}")
    # This will create all tables defined in models.py
    models.Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")

if __name__ == "__main__":
    # You can set these env vars before running or let it default to local SQLite
    # export DATABASE_URL="libsql://your-db-url"
    # export TURSO_AUTH_TOKEN="your-token"
    init_db()
