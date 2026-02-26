import os
import sqlite3
import requests
import time
import logging
from datetime import datetime

# Configuration
DB_PATH = 'weknora_bridge.db'
API_BASE_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')
BATCH_SIZE = 50
POLL_INTERVAL = 0.2  # Sleep 200ms between requests to avoid overwhelming the API

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("polling_task.log"),
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

def check_knowledge_status(knowledge_id: str) -> dict:
    """Query RAG system for knowledge status."""
    url = f"{API_BASE_URL}/api/v1/knowledge/{knowledge_id}"
    try:
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success', True): # Some APIs might just return data directly or wrap in success
                # Adapt based on API response structure. Assuming structure from doc:
                # { "success": true, "data": { "parse_status": "..." } }
                return result.get('data')
            else:
                logging.warning(f"API returned success=false for {knowledge_id}: {result.get('message')}")
                return None
        elif response.status_code == 404:
            logging.warning(f"Knowledge ID {knowledge_id} not found (404).")
            return {'parse_status': 'not_found'}
        else:
            logging.error(f"API request failed for {knowledge_id} with status {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Exception checking status for {knowledge_id}: {e}")
        return None

def main():
    start_time = time.time()
    processed_count = 0
    status_changed_count = 0
    
    logging.info("Starting polling task...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Fetch tasks that are pending or processing
        cursor.execute('''
            SELECT id, filename, knowledge_id, file_status 
            FROM document_status_table 
            WHERE file_status IN ('pending', 'processing') 
              AND knowledge_id IS NOT NULL 
            LIMIT ?
        ''', (BATCH_SIZE,))
        tasks = cursor.fetchall()
        
        if not tasks:
            logging.info("No active tasks to poll.")
            conn.close()
            return
            
        logging.info(f"Polling {len(tasks)} tasks...")
        
        for task in tasks:
            task_id = task['id']
            knowledge_id = task['knowledge_id']
            current_status = task['file_status']
            
            # Rate limiting
            time.sleep(POLL_INTERVAL)
            
            api_data = check_knowledge_status(knowledge_id)
            
            if api_data:
                remote_status = api_data.get('parse_status')
                
                # Handle 404/Not Found
                if remote_status == 'not_found':
                    logging.info(f"Knowledge {knowledge_id} missing, marking as failed.")
                    cursor.execute('''
                        UPDATE document_status_table 
                        SET file_status = 'failed', finish_at = ?, failed_msg = 'Knowledge ID not found in RAG system'
                        WHERE id = ?
                    ''', (datetime.now(), task_id))
                    status_changed_count += 1
                    continue

                if not remote_status:
                    continue
                
                # Normalize status if needed (e.g., lowercase)
                remote_status = remote_status.lower()
                
                if remote_status != current_status:
                    logging.info(f"Status changed for {task['filename']}: {current_status} -> {remote_status}")
                    
                    if remote_status == 'completed':
                        cursor.execute('''
                            UPDATE document_status_table 
                            SET file_status = 'completed', finish_at = ?, failed_msg = NULL
                            WHERE id = ?
                        ''', (datetime.now(), task_id))
                    elif remote_status == 'failed':
                        error_msg = api_data.get('error_message', 'Unknown error')
                        cursor.execute('''
                            UPDATE document_status_table 
                            SET file_status = 'failed', finish_at = ?, failed_msg = ?
                            WHERE id = ?
                        ''', (datetime.now(), error_msg, task_id))
                    else:
                        # Update intermediate status (e.g. pending -> processing)
                        cursor.execute('''
                            UPDATE document_status_table 
                            SET file_status = ?
                            WHERE id = ?
                        ''', (remote_status, task_id))
                    
                    status_changed_count += 1
            
            processed_count += 1
            # Commit periodically
            conn.commit()
            
        conn.close()
        
    except Exception as e:
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Polling process completed in {duration:.2f}s. Checked: {processed_count}, Changed: {status_changed_count}")
        
        # Record stats
        try:
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO script_process_record (script_name, process_duration, process_count, insert_count, update_count, delete_count, process_timestamp, status, failed_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('polling_task.py', duration, processed_count, 0, status_changed_count, 0, datetime.now(), 'success', ''))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Failed to record script stats: {e}")

if __name__ == '__main__':
    main()
