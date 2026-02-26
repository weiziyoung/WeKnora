import os
import sqlite3
import requests
import time
import logging
from datetime import datetime

# Configuration
DB_PATH = 'weknora_bridge.db'
API_BASE_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')
KNOWLEDGE_BASE_ID = os.getenv('KNOWLEDGE_BASE_ID')
BATCH_SIZE = 50

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("submit_task.log"),
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

def submit_file_to_rag(filepath: str, filename: str) -> dict:
    """Submit file to RAG system and return API response data."""
    url = f"{API_BASE_URL}/api/v1/knowledge-bases/{KNOWLEDGE_BASE_ID}/knowledge/file"
    
    try:
        with open(filepath, 'rb') as f:
            files = {
                'file': (filename, f)
            }
            # Optional parameters can be added here
            data = {
                'fileName': filename,
                'enable_multimodel': 'false' 
            }
            
            response = requests.post(url, files=files, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return result.get('data')
                else:
                    logging.error(f"API returned failure for {filename}: {result.get('message')}")
                    return None
            else:
                logging.error(f"API request failed for {filename} with status {response.status_code}: {response.text}")
                return None
                
    except Exception as e:
        logging.error(f"Exception submitting {filename}: {e}")
        return None

def main():
    if not KNOWLEDGE_BASE_ID:
        logging.error("KNOWLEDGE_BASE_ID environment variable is not set. Exiting.")
        return

    start_time = time.time()
    success_count = 0
    fail_count = 0
    
    logging.info("Starting submit task...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch 'discover' tasks
        cursor.execute("SELECT id, filename, filepath FROM document_status_table WHERE file_status = 'discover' LIMIT ?", (BATCH_SIZE,))
        tasks = cursor.fetchall()
        
        if not tasks:
            logging.info("No tasks to process.")
            conn.close()
            return
            
        logging.info(f"Processing {len(tasks)} tasks...")
        
        for task in tasks:
            task_id = task['id']
            filepath = task['filepath']
            filename = task['filename']
            
            logging.info(f"Submitting: {filename}")
            
            api_data = submit_file_to_rag(filepath, filename)
            
            if api_data:
                # Success
                knowledge_id = api_data.get('id')
                # Use the status returned by API (e.g., 'processing' or 'pending')
                new_status = api_data.get('parse_status', 'processing')
                file_hash = api_data.get('file_hash')
                
                cursor.execute('''
                    UPDATE document_status_table 
                    SET file_status = ?, knowledge_id = ?, file_hash = ?, process_at = ?, failed_msg = NULL
                    WHERE id = ?
                ''', (new_status, knowledge_id, file_hash, datetime.now(), task_id))
                success_count += 1
            else:
                # Failed
                cursor.execute('''
                    UPDATE document_status_table 
                    SET file_status = 'failed', failed_msg = 'API submission failed', process_at = ?
                    WHERE id = ?
                ''', (datetime.now(), task_id))
                fail_count += 1
                
            # Commit after each task or small batch to release locks quickly? 
            # Given WAL mode, batch commit is fine, but for safety against script crash, per-task commit is okay too.
            # Let's commit every loop to ensure progress is saved.
            conn.commit()
            
        conn.close()
        
    except Exception as e:
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Submit process completed in {duration:.2f}s. Success: {success_count}, Failed: {fail_count}")
        
        # Record stats
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO script_process_record (script_name, process_duration, process_count, insert_count, update_count, delete_count, process_timestamp, status, failed_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('submit_task.py', duration, success_count + fail_count, 0, success_count, 0, datetime.now(), 'success', ''))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Failed to record script stats: {e}")

if __name__ == '__main__':
    main()
