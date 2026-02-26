import os
import sqlite3
import hashlib
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Set

# Configuration
DB_PATH = 'weknora_bridge.db'
API_BASE_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')

# Directory Configuration
SEARCH_PREFIX = r'D:\Zbintel'
SEARCH_SUFFIX = r'SYSA\Edit\upimages'
SEARCH_MIDFIXES = [
    'ZBIntel_jhxny_hf_8088',
    'ZBintel_lbjs_tc_9199',
    'ZBIntel_LBTC_XT1_1011',
    'ZBIntel_LBTC_XT2_2022',
    'ZBIntel_LBTC_XT3_3033',
    'ZBIntel_LBZN_TG_4044',
    'ZBIntel_weiyy_tg_9099',
    'ZBIntel_YYJ_SC_5055',
    'ZBIntel_yyjs1_6066',
    'ZBIntel_yyjs2_7077'
]

SUPPORTED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.md', '.markdown', '.txt',
    '.xlsx', '.xls', '.csv',
    '.jpg', '.jpeg', '.png', '.gif'
}

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("discover_files.log"),
        logging.StreamHandler()
    ]
)

def get_db_connection():
    """Create a database connection with WAL mode enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging for concurrency
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # document_status_table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS document_status_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL UNIQUE,
        file_status TEXT DEFAULT 'discover',
        created_at DATETIME,
        last_modified_time REAL,
        process_at DATETIME,
        finish_at DATETIME,
        failed_msg TEXT,
        file_size INTEGER,
        file_hash TEXT,
        file_store_path TEXT,
        knowledge_id TEXT
    )
    ''')
    
    # script_process_record
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS script_process_record (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        script_name TEXT,
        process_duration REAL,
        process_count INTEGER,
        insert_count INTEGER,
        update_count INTEGER,
        delete_count INTEGER,
        process_timestamp DATETIME,
        status TEXT,
        failed_reason TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def delete_knowledge_api(knowledge_id: str) -> bool:
    """Call API to delete knowledge from RAG system."""
    if not knowledge_id:
        return True
    
    url = f"{API_BASE_URL}/api/v1/knowledge/{knowledge_id}"
    try:
        response = requests.delete(url)
        if response.status_code == 200:
            logging.info(f"Successfully deleted knowledge {knowledge_id}")
            return True
        elif response.status_code == 404:
            logging.warning(f"Knowledge ID {knowledge_id} not found (404), considering deleted.")
            return True
        else:
            logging.error(f"Failed to delete knowledge {knowledge_id}: {response.text}")
            return False
    except Exception as e:
        logging.error(f"API request failed for delete knowledge {knowledge_id}: {e}")
        return False

def scan_files() -> Dict[str, dict]:
    """Scan directories and return map of filepath -> file_info."""
    found_files = {}
    
    for mid in SEARCH_MIDFIXES:
        # Construct path using os.path.join for correct separator handling
        # Note: SEARCH_PREFIX is D:\Zbintel, SEARCH_SUFFIX is \SYSA\Edit\upimages
        # We strip leading/trailing slashes to ensure join works correctly
        base_dir = os.path.join(SEARCH_PREFIX, mid, SEARCH_SUFFIX.strip('\\'))
        
        if not os.path.exists(base_dir):
            logging.warning(f"Directory not found: {base_dir}")
            continue
            
        logging.info(f"Scanning directory: {base_dir}")
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                
                filepath = os.path.join(root, file)
                try:
                    stats = os.stat(filepath)
                    if stats.st_size < 1024: # < 1KB
                        continue
                        
                    found_files[filepath] = {
                        'filename': file,
                        'filepath': filepath,
                        'size': stats.st_size,
                        'mtime': stats.st_mtime
                    }
                except OSError as e:
                    logging.error(f"Error accessing file {filepath}: {e}")
    
    return found_files

def main():
    start_time = time.time()
    insert_count = 0
    update_count = 0
    delete_count = 0
    status = "success"
    failed_reason = ""
    
    logging.info("Starting discovery process...")
    
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Get existing DB files (excluding already deleted ones)
        logging.info("Fetching existing records from database...")
        cursor.execute("SELECT filepath, file_size, last_modified_time, file_hash, file_status, knowledge_id FROM document_status_table WHERE file_status != 'deleted'")
        db_rows = cursor.fetchall()
        db_files = {row['filepath']: dict(row) for row in db_rows}
        
        # 2. Scan current files on disk
        logging.info("Scanning file system...")
        current_files = scan_files()
        
        # 3. Process differences
        current_filepaths = set(current_files.keys())
        db_filepaths = set(db_files.keys())
        
        # 3.1 Insertions (Files on disk but not in DB)
        new_filepaths = current_filepaths - db_filepaths
        logging.info(f"Found {len(new_filepaths)} new files.")
        
        for fp in new_filepaths:
            info = current_files[fp]
            
            cursor.execute('''
                INSERT INTO document_status_table (filename, filepath, file_status, created_at, last_modified_time, file_size, file_hash)
                VALUES (?, ?, 'discover', ?, ?, ?, NULL)
            ''', (info['filename'], fp, datetime.now(), info['mtime'], info['size']))
            insert_count += 1
            
        # 3.2 Updates (Files in both, check for changes)
        potential_updates = current_filepaths & db_filepaths
        logging.info(f"Checking {len(potential_updates)} existing files for updates...")
        
        for fp in potential_updates:
            curr_info = current_files[fp]
            db_info = db_files[fp]
            
            # Skip if file is currently being processed to avoid race conditions
            if db_info['file_status'] == 'processing':
                continue
                
            # Check metadata first (mtime or size)
            # Use a small epsilon for float comparison if needed, but direct inequality is usually fine for mtime
            if curr_info['mtime'] > db_info['last_modified_time'] or curr_info['size'] != db_info['file_size']:
                # Metadata changed, assume content updated
                logging.info(f"File updated: {fp}")
                # Confirmed update
                # Delete old knowledge if exists
                if db_info['knowledge_id']:
                    delete_knowledge_api(db_info['knowledge_id'])
                
                cursor.execute('''
                    UPDATE document_status_table 
                    SET file_status = 'discover', created_at = ?, last_modified_time = ?, file_size = ?, file_hash = NULL, knowledge_id = NULL
                    WHERE filepath = ?
                ''', (datetime.now(), curr_info['mtime'], curr_info['size'], fp))
                update_count += 1

        # 3.3 Deletions (Files in DB but not on disk)
        deleted_filepaths = db_filepaths - current_filepaths
        logging.info(f"Found {len(deleted_filepaths)} deleted files.")
        
        for fp in deleted_filepaths:
            db_info = db_files[fp]
            
            logging.info(f"Marking as deleted: {fp}")
            if db_info['knowledge_id']:
                 delete_knowledge_api(db_info['knowledge_id'])
            
            cursor.execute('''
                UPDATE document_status_table
                SET file_status = 'deleted', finish_at = ?
                WHERE filepath = ?
            ''', (datetime.now(), fp))
            delete_count += 1
            
        conn.commit()
        conn.close()
        
    except Exception as e:
        status = "fail"
        failed_reason = str(e)
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Process completed in {duration:.2f}s. Insert: {insert_count}, Update: {update_count}, Delete: {delete_count}, Status: {status}")
        
        # Record execution stats
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO script_process_record (script_name, process_duration, process_count, insert_count, update_count, delete_count, process_timestamp, status, failed_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('discover_files.py', duration, insert_count + update_count + delete_count, insert_count, update_count, delete_count, datetime.now(), status, failed_reason))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Failed to record script stats: {e}")

if __name__ == '__main__':
    main()
