import os
from sqlalchemy import create_engine, text

# Get credentials from user's provided info
DATABASE_URL = "libsql://casepeerai-salehai.aws-us-east-2.turso.io"
AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzAyMjQ2NjcsImlkIjoiY2M5ZTE4NjctMGMwNi00MzcxLWIzZjMtMmM2MTRhOTllMTFlIiwicmlkIjoiYzgxOWZmNjYtNzViNi00NmQzLWJiZjQtMTRmNzMwNWMxOWFiIn0.tMNHDPh8-nkZ-e_burheTxTtSmRF4DB1Xv-DqTwsh4-oimkbvAveDCysJ1NCPf-RhGIUCl0te2trot5mMtnaBQ"

test_urls = [
    # Option 1: Current (Host only)
    f"sqlite+libsql://casepeerai-salehai.aws-us-east-2.turso.io?auth_token={AUTH_TOKEN}",
    
    # Option 2: Trying https directly if possible (unlikely to work with parser)
    # f"sqlite+libsql://https://casepeerai-salehai.aws-us-east-2.turso.io?auth_token={AUTH_TOKEN}",
    
    # Option 3: Using the libsql:// prefix inside if driver allows
    # f"sqlite+libsql://libsql://casepeerai-salehai.aws-us-east-2.turso.io?auth_token={AUTH_TOKEN}",

    # Option 4: Query param 'url'?
    f"sqlite+libsql://?url=https://casepeerai-salehai.aws-us-east-2.turso.io&auth_token={AUTH_TOKEN}"
]

for url in test_urls:
    print(f"\nTesting URL: {url.split('?')[0]}...")
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1"))
            print(f"✅ Success! Result: {res.fetchone()}")
            break
    except Exception as e:
        print(f"❌ Failed: {e}")
