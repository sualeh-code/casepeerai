
from database import engine, Base
from models import Document

def update_schema():
    print("Updating database schema...")
    Base.metadata.create_all(bind=engine)
    print("Schema updated successfully.")

if __name__ == "__main__":
    update_schema()
