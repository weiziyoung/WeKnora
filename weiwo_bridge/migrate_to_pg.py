import os
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import urllib.parse
# Import models from database.py
from database import DocumentStatus, ScriptProcessRecord, Base

# SQLite setup
SQLITE_DB_PATH = 'weknora_bridge.db'
if not os.path.exists(SQLITE_DB_PATH):
    print(f"SQLite database not found at {SQLITE_DB_PATH}")
    # Try looking in the current directory if running from elsewhere
    if os.path.exists(os.path.join('weiwo_bridge', SQLITE_DB_PATH)):
        SQLITE_DB_PATH = os.path.join('weiwo_bridge', SQLITE_DB_PATH)
    else:
        print("Could not find sqlite database.")
        sys.exit(1)

SQLITE_URL = f"sqlite:///{SQLITE_DB_PATH}"

# Postgres setup from env vars
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "weknora")

# Construct Postgres connection string
# Note: Requires psycopg2 or psycopg2-binary installed
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)
POSTGRES_URL = f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def migrate():
    print(f"Source SQLite: {SQLITE_URL}")
    print(f"Target Postgres: {POSTGRES_URL}")
    
    # Connect to SQLite
    try:
        sqlite_engine = create_engine(SQLITE_URL)
        SqliteSession = sessionmaker(bind=sqlite_engine)
        sqlite_session = SqliteSession()
    except Exception as e:
        print(f"Failed to connect to SQLite: {e}")
        return

    # Connect to Postgres
    try:
        pg_engine = create_engine(POSTGRES_URL)
        PgSession = sessionmaker(bind=pg_engine)
        pg_session = PgSession()
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}")
        return

    # Create tables in Postgres if not exist
    print("Creating tables in Postgres...")
    try:
        Base.metadata.create_all(pg_engine)
    except Exception as e:
        print(f"Error creating tables: {e}")
        return

    # Migrate DocumentStatus
    print("Migrating DocumentStatus...")
    try:
        docs = sqlite_session.query(DocumentStatus).all()
        count = 0
        skipped = 0
        for doc in docs:
            # Check if exists by filepath (unique key)
            exists = pg_session.query(DocumentStatus).filter_by(filepath=doc.filepath).first()
            if not exists:
                # Create a new instance to avoid attaching the session state of the old one
                new_doc = DocumentStatus()
                # Copy attributes
                for column in DocumentStatus.__table__.columns:
                    if column.name == 'id':
                        continue # Skip ID to let Postgres autoincrement
                    setattr(new_doc, column.name, getattr(doc, column.name))
                
                pg_session.add(new_doc)
                count += 1
            else:
                skipped += 1
        
        pg_session.commit()
        print(f"Migrated {count} DocumentStatus records. Skipped {skipped} existing.")
    except Exception as e:
        print(f"Error migrating DocumentStatus: {e}")
        pg_session.rollback()

    # Migrate ScriptProcessRecord
    print("Migrating ScriptProcessRecord...")
    try:
        records = sqlite_session.query(ScriptProcessRecord).all()
        count = 0
        skipped = 0
        for record in records:
            # Check if exists by script_name and timestamp
            exists = pg_session.query(ScriptProcessRecord).filter_by(
                script_name=record.script_name, 
                process_timestamp=record.process_timestamp
            ).first()
            
            if not exists:
                new_record = ScriptProcessRecord()
                for column in ScriptProcessRecord.__table__.columns:
                    if column.name == 'id':
                        continue
                    setattr(new_record, column.name, getattr(record, column.name))
                
                pg_session.add(new_record)
                count += 1
            else:
                skipped += 1
                
        pg_session.commit()
        print(f"Migrated {count} ScriptProcessRecord records. Skipped {skipped} existing.")
    except Exception as e:
        print(f"Error migrating ScriptProcessRecord: {e}")
        pg_session.rollback()
    
    print("Migration completed.")

if __name__ == "__main__":
    migrate()
