import os
import csv
import re
import logging
from sqlalchemy.orm import Session
from database import get_session, DocumentStatus, init_db

# Configuration
# Default to D:\dump_data as per instructions, but allow override for testing
DUMP_DATA_DIR = os.getenv('DUMP_DATA_DIR', r'D:\dump_data')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("link_filename_path.log"),
        logging.StreamHandler()
    ]
)

def parse_content(content):
    """
    Parse HTML content to extract file information.
    Logic based on playground/extract_filename_zb_link.py
    """
    file_list = []
    
    # Regex to find <a> tags
    # <a (attributes)>(inner_text)</a>
    a_tag_pattern = re.compile(r'<a\s+([^>]+)>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    
    matches = a_tag_pattern.findall(content)
    
    for attrs_str, inner_text in matches:
        # Extract href
        href_match = re.search(r'href="([^"]+)"', attrs_str, re.IGNORECASE)
        if not href_match:
            continue
        href = href_match.group(1)
        
        # Pattern 1: /SYSA/edit/upimages/
        if '/SYSA/edit/upimages/' in href:
            filename = inner_text.strip()
            # Remove any HTML tags from filename if present
            filename = re.sub(r'<[^>]+>', '', filename)
            if filename:
                file_list.append({
                    "filepath": href, # This is the relative path from the link
                    "filename": filename # This is the display name (e.g., "Contract.pdf")
                })
            
        # Pattern 2: /WebSource.ashx?pf=
        elif '/WebSource.ashx?pf=' in href:
            # Extract title attribute
            title_match = re.search(r'title="([^"]+)"', attrs_str, re.IGNORECASE)
            if title_match:
                filename = title_match.group(1)
                file_list.append({
                    "zbpath": href,
                    "filename": filename
                })
                
    return file_list

def process_database_folder(session: Session, db_folder_path: str):
    """
    Process contract.csv in a specific database dump folder.
    """
    contract_file = os.path.join(db_folder_path, 'contract.csv')
    if not os.path.exists(contract_file):
        logging.warning(f"No contract.csv found in {db_folder_path}")
        return

    logging.info(f"Processing {contract_file}")
    
    # Attempt to read with likely encodings
    # SQL Server dumps often use local codepage (e.g. GBK/CP936) or UTF-16
    encodings = ['utf-8', 'gbk', 'utf-16', 'cp936']
    lines = []
    
    for enc in encodings:
        try:
            with open(contract_file, 'r', encoding=enc) as f:
                # Read all lines to avoid keeping file handle open too long
                lines = f.readlines()
            logging.info(f"Successfully read {contract_file} using {enc} encoding.")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logging.error(f"Error reading {contract_file}: {e}")
            return
            
    if not lines:
        logging.error(f"Failed to decode {contract_file} with supported encodings.")
        return

    update_count = 0
    skip_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Assuming tab-separated values based on bcp output
        parts = line.split('\t')
        
        # We expect at least 3 columns: ord, title, intro (content)
        if len(parts) < 3:
            continue
        
        try:
            ord_val_str = parts[0].strip()
            try:
                ord_val = int(ord_val_str)
            except ValueError:
                logging.warning(f"Invalid contract_ord value: {ord_val_str}, skipping line.")
                continue

            title = parts[1].strip()
            # Content is everything after the second tab
            content = "\t".join(parts[2:]).strip()
            
            extracted_files = parse_content(content)
            
            for file_info in extracted_files:
                # 3. Skip files with zbpath
                if 'zbpath' in file_info:
                    continue 
                
                # We only process files with 'filepath' (Pattern 1)
                if 'filepath' in file_info:
                    if update_db_record(session, file_info, title, ord_val):
                        update_count += 1
                    else:
                        skip_count += 1
                        
        except Exception as e:
            logging.error(f"Error processing line in {contract_file}: {e}")
            
    logging.info(f"Finished {contract_file}. Updated: {update_count}, Skipped/NoChange: {skip_count}")

def update_db_record(session: Session, file_info: dict, title: str, ord_val: int) -> bool:
    """
    Update the database record if a matching file is found.
    Returns True if updated, False otherwise.
    """
    rel_path = file_info['filepath'] # e.g., /SYSA/edit/upimages/202033194410445.pdf
    real_name = file_info['filename'] # e.g., 合同.pdf
    
    # Extract the physical filename from the relative path (e.g., 202033194410445.pdf)
    # This is likely unique or at least highly specific.
    physical_filename = os.path.basename(rel_path)
    
    if not physical_filename:
        return False
        
    # Search for the record in the database
    # The filepath in DB is absolute (e.g. D:\Zbintel\...\SYSA\Edit\upimages\202033194410445.pdf)
    # We search for records where the filepath ends with the physical filename.
    # Using 'like' for partial match. 
    # Note: On some systems path separators might differ, but basename match is a good start.
    
    candidates = session.query(DocumentStatus).filter(
        DocumentStatus.filepath.like(f"%{physical_filename}")
    ).all()
    
    for doc in candidates:
        # Verify the path structure matches (e.g. ensure it ends with /SYSA/edit/upimages/filename)
        # Normalize slashes for comparison
        norm_doc_path = doc.filepath.replace('\\', '/').lower()
        norm_rel_path = rel_path.replace('\\', '/').lower()
        
        # Check if the relative path (from link) is a suffix of the absolute path (in DB)
        # We strip leading slash from rel_path if present for endswith check
        suffix_check = norm_rel_path.lstrip('/')
        
        if norm_doc_path.endswith(suffix_check):
            # 4. If filepath matches and filename matches, skip
            if doc.filename == real_name:
                return False
            
            # 5. If filepath matches but filename differs, update
            logging.info(f"Updating File: {doc.filepath}")
            logging.info(f"  Old Filename: {doc.filename}")
            logging.info(f"  New Filename: {real_name}")
            logging.info(f"  Title: {title}, Ord: {ord_val}")
            
            doc.filename = real_name
            doc.contract_title = title
            doc.contract_ord = ord_val
            
            # Also could update zb_link if we wanted to store the source URL
            # doc.zb_link = rel_path 
            
            return True
            
    return False

def main():
    if not os.path.exists(DUMP_DATA_DIR):
        logging.error(f"Dump directory not found: {DUMP_DATA_DIR}")
        logging.info("Please ensure dump_contract.ps1 has been executed and DUMP_DATA_DIR is set correctly.")
        return

    logging.info(f"Starting database update from {DUMP_DATA_DIR}")
    
    # Initialize DB (ensure tables exist)
    init_db()
    session = get_session()
    
    try:
        # Iterate over subdirectories in DUMP_DATA_DIR
        # Each subdirectory corresponds to a database
        for entry in os.scandir(DUMP_DATA_DIR):
            if entry.is_dir():
                logging.info(f"Scanning database folder: {entry.name}")
                process_database_folder(session, entry.path)
        
        session.commit()
        logging.info("Database update committed successfully.")
        
    except Exception as e:
        session.rollback()
        logging.error(f"Fatal error during execution: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
