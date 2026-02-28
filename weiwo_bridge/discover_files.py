import os
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Set

# Import ORM models
from database import DocumentStatus, ScriptProcessRecord, init_db, get_session

# Configuration
API_BASE_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')
API_KEY = 'sk-06OSFVXX3uEPKxgxx4YhGbx-VCjujpAAC8MpxMxJL-wv4CbQ'

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

def delete_knowledge_api(knowledge_id: str) -> bool:
    """Call API to delete knowledge from RAG system."""
    if not knowledge_id:
        return True
    
    url = f"{API_BASE_URL}/api/v1/knowledge/{knowledge_id}"
    try:
        response = requests.delete(url, headers={'X-API-Key': API_KEY})
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
    
    session = get_session()
    
    try:
        init_db()
        
        # 1. Get existing DB files (excluding already deleted ones)
        logging.info("Fetching existing records from database...")
        existing_docs = session.query(DocumentStatus).filter(DocumentStatus.file_status != 'deleted').all()
        db_files = {doc.filepath: doc for doc in existing_docs}
        
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
            new_doc = DocumentStatus(
                filename=info['filename'],
                filepath=fp,
                file_status='discover',
                created_at=datetime.now(),
                last_modified_time=info['mtime'],
                file_size=info['size']
            )
            session.add(new_doc)
            insert_count += 1
            
        # 3.2 Updates (Files in both, check for changes)
        potential_updates = current_filepaths & db_filepaths
        logging.info(f"Checking {len(potential_updates)} existing files for updates...")
        
        for fp in potential_updates:
            curr_info = current_files[fp]
            db_doc = db_files[fp]
            
            # Skip if file is currently being processed to avoid race conditions
            if db_doc.file_status == 'processing':
                continue
                
            # Check metadata first (mtime or size)
            if curr_info['mtime'] > db_doc.last_modified_time or curr_info['size'] != db_doc.file_size:
                # Metadata changed, assume content updated
                logging.info(f"File updated: {fp}")
                # Confirmed update
                # Delete old knowledge if exists
                if db_doc.knowledge_id:
                    delete_knowledge_api(db_doc.knowledge_id)
                
                db_doc.file_status = 'discover'
                db_doc.created_at = datetime.now()
                db_doc.last_modified_time = curr_info['mtime']
                db_doc.file_size = curr_info['size']
                db_doc.file_hash = None
                db_doc.knowledge_id = None
                
                update_count += 1

        # 3.3 Deletions (Files in DB but not on disk)
        deleted_filepaths = db_filepaths - current_filepaths
        logging.info(f"Found {len(deleted_filepaths)} deleted files.")
        
        for fp in deleted_filepaths:
            db_doc = db_files[fp]
            
            logging.info(f"Marking as deleted: {fp}")
            if db_doc.knowledge_id:
                 delete_knowledge_api(db_doc.knowledge_id)
            
            db_doc.file_status = 'deleted'
            db_doc.finish_at = datetime.now()
            
            delete_count += 1
            
        session.commit()
        
    except Exception as e:
        session.rollback()
        status = "fail"
        failed_reason = str(e)
        logging.exception("Script execution failed")
    finally:
        duration = time.time() - start_time
        logging.info(f"Process completed in {duration:.2f}s. Insert: {insert_count}, Update: {update_count}, Delete: {delete_count}, Status: {status}")
        
        # Record execution stats
        try:
            stat_record = ScriptProcessRecord(
                script_name='discover_files.py',
                process_duration=duration,
                process_count=insert_count + update_count + delete_count,
                insert_count=insert_count,
                update_count=update_count,
                delete_count=delete_count,
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
