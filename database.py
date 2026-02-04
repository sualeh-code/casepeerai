from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os

# Database configuration
# For Turso: libsql://...
# For SQLite: sqlite:///./casepeer.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./casepeer.db")
AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

if DATABASE_URL.startswith("libsql://"):
    # Use https:// for the base URL to avoid WebSocket handshake issues on some systems
    clean_url = DATABASE_URL.replace("libsql://", "https://")
    if AUTH_TOKEN:
        SQLALCHEMY_DATABASE_URL = f"sqlite+libsql://{clean_url}?auth_token={AUTH_TOKEN}"
    else:
        SQLALCHEMY_DATABASE_URL = f"sqlite+libsql://{clean_url}"
else:
    SQLALCHEMY_DATABASE_URL = DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} if not SQLALCHEMY_DATABASE_URL.startswith("sqlite+libsql") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
