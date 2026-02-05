from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# HARDCODED Turso Database Credentials
# All other settings (CasePeer, Gmail, etc.) are stored in the app_settings table
DATABASE_URL = "https://casepeerai-salehai.aws-us-east-2.turso.io"
AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzAyNTAwMzksImlkIjoiY2M5ZTE4NjctMGMwNi00MzcxLWIzZjMtMmM2MTRhOTllMTFlIiwicmlkIjoiYzgxOWZmNjYtNzViNi00NmQzLWJiZjQtMTRmNzMwNWMxOWFiIn0.lgyzL-ITZMts0H_eXBdC1d-UJ4xWDus5qQFTmND_1zZ1oOS2vEjfvUzao2jlYRVATH95hBW664nFS2h2AGkdBw"

# Build SQLAlchemy connection URL for Turso/libsql
SQLALCHEMY_DATABASE_URL = f"sqlite+libsql://?url={DATABASE_URL}&auth_token={AUTH_TOKEN}"

print(f"DEBUG: Connecting to Database: {DATABASE_URL}...")

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
