import os
import requests
import time
import logging
from datetime import datetime

# Import ORM models
from database import DocumentStatus, ScriptProcessRecord, get_session

# Configuration
API_BASE_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')
API_KEY = 'sk-06OSFVXX3uEPKxgxx4YhGbx-VCjujpAAC8MpxMxJL-wv4CbQ'
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
            
            response = requests.post(url, files=files, data=data, timeout=60, headers={'X-API-Key': API_KEY})
            
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
    status = "success"
    failed_reason = ""
    
    logging.info("Starting submit task...")
    
    session = get_session()
    
    try:
        # 1. Fetch 'discover' tasks
        tasks = session.query(DocumentStatus).filter(DocumentStatus.file_status == 'discover').limit(BATCH_SIZE).all()
        
        if not tasks:
            logging.info("No tasks to process.")
            session.close()
            return
            
        logging.info(f"Processing {len(tasks)} tasks...")
        
        for task in tasks:
            logging.info(f"Submitting: {task.filename}")
            
            api_data = submit_file_to_rag(task.filepath, task.filename)
            
            if api_data:
                # Success
                task.knowledge_id = api_data.get('id')
                task.file_status = api_data.get('parse_status', 'processing')
                task.file_hash = api_data.get('file_hash')
                task.process_at = datetime.now()
                task.failed_msg = None
                success_count += 1
            else:
                # Failed
                task.file_status = 'failed'
                task.failed_msg = 'API submission failed'
                task.process_at = datetime.now()
                fail_count += 1
                
            session.commit()
            
    except Exception as e:
        session.rollback()
        status = "fail"
        failed_reason = str(e)
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Submit process completed in {duration:.2f}s. Success: {success_count}, Failed: {fail_count}")
        
        # Record stats
        try:
            stat_record = ScriptProcessRecord(
                script_name='submit_task.py',
                process_duration=duration,
                process_count=success_count + fail_count,
                insert_count=0,
                update_count=success_count, # Consistent with original behavior
                delete_count=0,
                process_timestamp=datetime.now(),
                status=status,
                failed_reason=failed_reason
            )
            session.add(stat_record)
            session.commit()
            session.close()
        except Exception as e:
            logging.error(f"Failed to record script stats: {e}")

if __name__ == '__main__':
    main()
