import os
import requests
import time
import logging
from datetime import datetime

# Import ORM models
from database import DocumentStatus, ScriptProcessRecord, get_session

# Configuration
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
    status = "success"
    failed_reason = ""
    
    logging.info("Starting polling task...")
    
    session = get_session()
    
    try:
        # 1. Fetch tasks that are pending or processing
        tasks = session.query(DocumentStatus).filter(
            DocumentStatus.file_status.in_(['pending', 'processing']),
            DocumentStatus.knowledge_id.isnot(None)
        ).limit(BATCH_SIZE).all()
        
        if not tasks:
            logging.info("No active tasks to poll.")
            session.close()
            return
            
        logging.info(f"Polling {len(tasks)} tasks...")
        
        for task in tasks:
            current_status = task.file_status
            
            # Rate limiting
            time.sleep(POLL_INTERVAL)
            
            api_data = check_knowledge_status(task.knowledge_id)
            
            if api_data:
                remote_status = api_data.get('parse_status')
                
                # Handle 404/Not Found
                if remote_status == 'not_found':
                    logging.info(f"Knowledge {task.knowledge_id} missing, marking as failed.")
                    task.file_status = 'failed'
                    task.finish_at = datetime.now()
                    task.failed_msg = 'Knowledge ID not found in RAG system'
                    status_changed_count += 1
                    session.commit()
                    continue

                if not remote_status:
                    continue
                
                # Normalize status if needed (e.g., lowercase)
                remote_status = remote_status.lower()
                
                if remote_status != current_status:
                    logging.info(f"Status changed for {task.filename}: {current_status} -> {remote_status}")
                    
                    if remote_status == 'completed':
                        task.file_status = 'completed'
                        task.finish_at = datetime.now()
                        task.failed_msg = None
                    elif remote_status == 'failed':
                        error_msg = api_data.get('error_message', 'Unknown error')
                        task.file_status = 'failed'
                        task.finish_at = datetime.now()
                        task.failed_msg = error_msg
                    else:
                        # Update intermediate status (e.g. pending -> processing)
                        task.file_status = remote_status
                    
                    status_changed_count += 1
            
            processed_count += 1
            # Commit periodically (or per task as here)
            session.commit()
            
    except Exception as e:
        session.rollback()
        status = "fail"
        failed_reason = str(e)
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Polling process completed in {duration:.2f}s. Checked: {processed_count}, Changed: {status_changed_count}")
        
        # Record stats
        try:
            stat_record = ScriptProcessRecord(
                script_name='polling_task.py',
                process_duration=duration,
                process_count=processed_count,
                insert_count=0,
                update_count=status_changed_count,
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
