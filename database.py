from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Database configuration
# For Turso: libsql://...
# For SQLite: sqlite:///./casepeer.db
# Database configuration
# Enforce Turso/LibSQL usage
DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL environment variable is not set. You must configure a Turso/LibSQL database.")

if "sqlite:///" in DATABASE_URL and "libsql" not in DATABASE_URL:
     print("WARNING: You are configured to use a local SQLite file. This is NOT recommended for production/Render as data will be lost.")
     SQLALCHEMY_DATABASE_URL = DATABASE_URL
elif DATABASE_URL.startswith("libsql://") or DATABASE_URL.startswith("https://"):
    # Clear the prefix to get the base URL
    base_url = DATABASE_URL
    if base_url.startswith("libsql://"):
        base_url = base_url.replace("libsql://", "https://")
    
    if not AUTH_TOKEN:
         raise ValueError("CRITICAL: Turso URL provided but TURSO_AUTH_TOKEN is missing. Please set this environment variable.")

    # Using the 'url' parameter is often more reliable for Hrana redirects
    SQLALCHEMY_DATABASE_URL = f"sqlite+libsql://?url={base_url}&auth_token={AUTH_TOKEN}"
else:
    # Fallback for other postgres strings etc if user changes mind later
    SQLALCHEMY_DATABASE_URL = DATABASE_URL

print(f"DEBUG: Connecting to Database: {SQLALCHEMY_DATABASE_URL.split('&auth_token')[0]}...")

from sqlalchemy.pool import NullPool

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    # The libsql dialect handles its own threading, but we keep this safe
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {},
    poolclass=NullPool
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
