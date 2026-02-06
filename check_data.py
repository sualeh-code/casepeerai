from turso_client import turso
import json

def diagnose_all():
    print("Listing all tables in Turso...")
    tables = turso.get_tables()
    print(f"Tables found: {tables}")
    
    for table in tables:
        count_row = turso.fetch_one(f"SELECT COUNT(*) as count FROM {table}")
        count = count_row['count'] if count_row else 0
        print(f"Table '{table}': {count} rows")
        
        if count > 0:
            sample = turso.fetch_all(f"SELECT * FROM {table} LIMIT 1")
            print(f"  Sample from '{table}': {json.dumps(sample[0], indent=2) if sample else 'None'}")

if __name__ == "__main__":
    diagnose_all()
