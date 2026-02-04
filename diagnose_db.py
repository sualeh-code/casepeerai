from database import engine, SessionLocal
from sqlalchemy import inspect, text
import models

def diagnose():
    print("--- Database Diagnostic Tool ---")
    
    # 1. Connection Check
    print("\n1. Testing Connection...")
    try:
        with engine.connect() as conn:
            print("   ✓ Connection successful")
            # Try a simple query
            result = conn.execute(text("SELECT 1")).scalar()
            print(f"   ✓ SELECT 1 returned: {result}")
    except Exception as e:
        print(f"   ✗ Connection FAILED: {e}")
        return

    # 2. Schema Check
    print("\n2. Checking Schema...")
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"   Tables found: {tables}")
    
    expected_tables = ["app_settings", "case_metrics", "cases", "negotiations", "classifications", "reminders", "token_usage", "app_sessions"]
    missing = [t for t in expected_tables if t not in tables]
    
    if missing:
        print(f"   ✗ Missing tables: {missing}")
        print("   Attempting to create missing tables...")
        models.Base.metadata.create_all(bind=engine)
        print("   ✓ create_all() execution complete.")
        
        # Check again
        inspector = inspect(engine)
        tables_after = inspector.get_table_names()
        missing_after = [t for t in expected_tables if t not in tables_after]
        if missing_after:
             print(f"   ✗ Still missing tables after creation: {missing_after}")
        else:
             print("   ✓ All tables created successfully!")
    else:
        print("   ✓ All expected tables present.")

    # 3. Data Check (AppSettings)
    print("\n3. Checking App Settings...")
    try:
        with SessionLocal() as db:
            settings = db.query(models.AppSetting).all()
            print(f"   Found {len(settings)} settings:")
            for s in settings:
                masked_val = s.value
                if "password" in s.key or "key" in s.key:
                    masked_val = "***"
                print(f"     - {s.key}: {masked_val}")
    except Exception as e:
        print(f"   ✗ Failed to query settings: {e}")

if __name__ == "__main__":
    diagnose()
