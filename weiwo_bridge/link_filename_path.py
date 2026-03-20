import os
import csv
import re
import logging
import time
import base64
import hashlib
import subprocess
import sys
from urllib.parse import unquote, urlparse
from typing import Optional, Tuple
from datetime import datetime

import requests
from openai import OpenAI
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session
from database import get_session, DocumentStatus, init_db, ScriptProcessRecord

# Constants for WeiWoSession
LOGIN_URL = os.getenv("MOCK_LOGIN_URL", "http://192.168.1.70:1011/sysn/view/init/login.ashx")
LOGIN_USERNAME = os.getenv("MOCK_LOGIN_USERNAME", "young")
LOGIN_PASSWORD = os.getenv("MOCK_LOGIN_PASSWORD", "young1001")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-muvpkwaagsyaspqtiuvjlqpxlrfjaztwldlbxkbodkgbetqz")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen3-VL-32B-Instruct")
CAPTCHA_RETRY = int(os.getenv("MOCK_LOGIN_CAPTCHA_RETRY", "3"))
WAIT_SECONDS = int(os.getenv("MOCK_LOGIN_WAIT_SECONDS", "15"))
SERVER_INSTANCE = "WIN-K2TPMMTJLJM"

DOWNLOAD_CONNECT_TIMEOUT_SECONDS = int(os.getenv("DOWNLOAD_CONNECT_TIMEOUT_SECONDS", "10"))
DOWNLOAD_READ_TIMEOUT_SECONDS = int(os.getenv("DOWNLOAD_READ_TIMEOUT_SECONDS", "60"))
DOWNLOAD_MAX_SECONDS = int(os.getenv("DOWNLOAD_MAX_SECONDS", "300"))
DOWNLOAD_PROGRESS_LOG_INTERVAL_SECONDS = int(os.getenv("DOWNLOAD_PROGRESS_LOG_INTERVAL_SECONDS", "30"))
DOWNLOAD_RETRY_MAX = int(os.getenv("DOWNLOAD_RETRY_MAX", "3"))
DOWNLOAD_RETRY_BACKOFF_SECONDS = float(os.getenv("DOWNLOAD_RETRY_BACKOFF_SECONDS", "2"))

# Constants for WeKnora API
WEKNORA_API_URL = os.getenv('WEKNORA_API_URL', 'http://localhost:8000')
WEKNORA_API_KEY = 'sk-06OSFVXX3uEPKxgxx4YhGbx-VCjujpAAC8MpxMxJL-wv4CbQ'


SUPPORTED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.md', '.markdown', '.txt',
    '.xlsx', '.xls', '.csv',
    '.jpg', '.jpeg', '.png', '.gif'
}

class UnsupportedFileExtensionError(Exception):
    pass

class WeiWoSession:
    def __init__(self):
        self.driver = None
        self.session = None

    def _create_driver(self) -> webdriver.Chrome:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        return webdriver.Chrome(options=options)

    def _first_visible(self, selectors: list[str]) -> WebElement:
        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    return element
            except NoSuchElementException:
                continue
        raise NoSuchElementException(f"未找到可见元素: {selectors}")

    def _find_username_input(self) -> WebElement:
        selectors = [
            "#username",
            "#usernameid",
            "input[name*='user' i]",
            "input[id*='user' i]",
            "input[name*='login' i]",
            "input[id*='login' i]",
            "input[type='text']",
        ]
        return self._first_visible(selectors)

    def _find_password_input(self) -> WebElement:
        selectors = [
            "#password",
            "#userpassid",
            "input[type='password']",
            "input[name*='pass' i]",
            "input[id*='pass' i]",
        ]
        return self._first_visible(selectors)

    def _find_captcha_image(self) -> WebElement:
        selectors = [
            "#code_img",
            "img[id*='captcha' i]",
            "img[name*='captcha' i]",
            "img[class*='captcha' i]",
            "img[src*='captcha' i]",
            "img[id*='verify' i]",
            "img[class*='verify' i]",
            "img[src*='verify' i]",
            "img[src*='checkcode' i]",
            "img[src*='validate' i]",
            "img",
        ]
        return self._first_visible(selectors)

    def _find_captcha_input(self) -> WebElement:
        selectors = [
            "#xcode",
            "#xcodeYZM",
            "input[name*='captcha' i]",
            "input[id*='captcha' i]",
            "input[name*='verify' i]",
            "input[id*='verify' i]",
            "input[name*='code' i]",
            "input[id*='code' i]",
        ]
        return self._first_visible(selectors)

    def _find_submit_button(self) -> WebElement:
        selectors = [
            "#login input[type='button']",
            "#login button",
            "input#login",
            "button[type='submit']",
            "input[type='submit']",
            "button[id*='login' i]",
            "button[class*='login' i]",
            "input[id*='login' i]",
            "input[class*='login' i]",
            "button",
        ]
        return self._first_visible(selectors)

    def _normalize_captcha_text(self, text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", text or "")
        if cleaned:
            return cleaned
        return (text or "").strip().replace(" ", "")

    def _recognize_captcha(self, image_bytes: bytes) -> str:
        if not SILICONFLOW_API_KEY:
            raise ValueError("缺少 SILICONFLOW_API_KEY 环境变量")
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        client = OpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
        response = client.chat.completions.create(
            model=SILICONFLOW_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                        {
                            "type": "text",
                            "text": "请只返回验证码内容，不要返回其他解释、标点或空格。",
                        },
                    ],
                }
            ],
            temperature=0,
        )
        content = response.choices[0].message.content if response.choices else ""
        return self._normalize_captcha_text(content)

    def _is_login_success(self) -> bool:
        current_url = self.driver.current_url.lower()
        if "view/init/login.ashx" not in current_url and "view/init/relogin.ashx" not in current_url:
            return True
        try:
            if self.driver.find_elements(By.CSS_SELECTOR, "#username") or self.driver.find_elements(
                By.CSS_SELECTOR, "#password"
            ):
                return False
        except Exception:
            return False
        page = self.driver.page_source
        fail_signals = ["验证码错误", "用户名或密码错误", "登录失败"]
        if any(signal in page for signal in fail_signals):
            return False
        return False

    def _refresh_captcha_if_possible(self) -> None:
        try:
            captcha_image = self._find_captcha_image()
            captcha_image.click()
            time.sleep(0.8)
        except Exception:
            return


    def login(self, force_refresh: bool = False) -> requests.Session:
        if self.session and not force_refresh:
            return self.session
            
        self.driver = self._create_driver()
        try:
            self.driver.get(LOGIN_URL)
            wait = WebDriverWait(self.driver, WAIT_SECONDS)
            wait.until(EC.presence_of_element_located((By.ID, "username")))

            for _ in range(CAPTCHA_RETRY):
                username_input = self._find_username_input()
                password_input = self._find_password_input()
                captcha_image = self._find_captcha_image()
                captcha_input = self._find_captcha_input()
                submit_button = self._find_submit_button()

                username_input.clear()
                username_input.send_keys(LOGIN_USERNAME)
                password_input.clear()
                password_input.send_keys(LOGIN_PASSWORD)

                captcha_bytes = captcha_image.screenshot_as_png
                captcha_text = self._recognize_captcha(captcha_bytes)
                if not captcha_text:
                    self._refresh_captcha_if_possible()
                    continue

                captcha_input.clear()
                captcha_input.send_keys(captcha_text)
                submit_button.click()

                try:
                    wait.until(lambda d: self._is_login_success())
                except TimeoutException:
                    time.sleep(1.5)

                if self._is_login_success():
                    self.session = requests.Session()
                    user_agent = self.driver.execute_script("return navigator.userAgent;")
                    self.session.headers.update({"User-Agent": user_agent})
                    for cookie in self.driver.get_cookies():
                        self.session.cookies.set(
                            name=cookie.get("name"),
                            value=cookie.get("value"),
                            domain=cookie.get("domain"),
                            path=cookie.get("path", "/"),
                        )
                    return self.session
                self._refresh_captcha_if_possible()

            raise RuntimeError("登录失败：验证码多次识别后仍未通过")
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

    def _extract_filename_from_response(self, response: requests.Response, url: str) -> str:
        content_disposition = response.headers.get("Content-Disposition", "")
        filename_utf8 = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
        if filename_utf8:
            parsed = unquote(filename_utf8.group(1).strip().strip('"'))
            if parsed:
                return parsed
        filename_plain = re.search(r'filename\s*=\s*"([^"]+)"', content_disposition, re.IGNORECASE)
        if filename_plain:
            parsed = unquote(filename_plain.group(1).strip())
            if parsed:
                return parsed
        filename_plain = re.search(r"filename\s*=\s*([^;]+)", content_disposition, re.IGNORECASE)
        if filename_plain:
            parsed = unquote(filename_plain.group(1).strip().strip('"'))
            if parsed:
                return parsed
        basename = unquote(os.path.basename(urlparse(url).path))
        if basename and basename.lower() not in {"websource.ashx", "download", "file"}:
            return basename
        return "downloaded_file.bin"

    def download(self, url: str, retry_count: int = 0) -> Tuple[bytes, str, str]:
        """
        Download file content.
        Returns: (content_bytes, filename, md5_hash)
        """
        if not self.session:
            self.login()
        
        # Ensure full URL if relative
        if not url.startswith('http'):
            # Construct base URL from LOGIN_URL
            parsed_login = urlparse(LOGIN_URL)
            base_url = f"{parsed_login.scheme}://{parsed_login.netloc}"
            if not url.startswith('/'):
                url = '/' + url
            url = base_url + url

        try:
            request_start_time = time.time()
            with self.session.get(
                url,
                timeout=(DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_READ_TIMEOUT_SECONDS),
                stream=True,
            ) as response:
                request_elapsed = time.time() - request_start_time
                content_length = response.headers.get("Content-Length", "unknown")
                logging.info(
                    f"Request headers received in {request_elapsed:.2f}s, status={response.status_code}, content_length={content_length}, url={url}"
                )

                response.raise_for_status()

                filename = self._extract_filename_from_response(response, url)
                ext = os.path.splitext(filename)[1].lower()
                # Skip extension check for fallback filename "downloaded_file.bin"
                # This usually means the server didn't provide a Content-Disposition header, often an error page
                if filename != "downloaded_file.bin" and ext not in SUPPORTED_EXTENSIONS:
                    logging.warning(f"Skipping unsupported file type: {filename} ({ext})")
                    raise UnsupportedFileExtensionError(f"Unsupported file extension: {ext}")

                chunks = []
                md5_hash = hashlib.md5()
                bytes_downloaded = 0
                download_start_time = time.time()
                last_progress_log_time = download_start_time

                # Use a larger chunk size (128KB) for better network throughput
                for chunk in response.iter_content(chunk_size=131072):
                    now = time.time()
                    if now - download_start_time > DOWNLOAD_MAX_SECONDS:
                        raise TimeoutError(
                            f"Download exceeded {DOWNLOAD_MAX_SECONDS}s: downloaded={bytes_downloaded} bytes, filename={filename}, url={url}"
                        )
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    bytes_downloaded += len(chunk)
                    md5_hash.update(chunk)
                    if now - last_progress_log_time >= DOWNLOAD_PROGRESS_LOG_INTERVAL_SECONDS:
                        elapsed_download = now - download_start_time
                        logging.info(
                            f"Downloading {filename}: {bytes_downloaded} bytes in {elapsed_download:.2f}s, url={url}"
                        )
                        last_progress_log_time = now
                
                content = b"".join(chunks)

                total_download_elapsed = time.time() - download_start_time
                logging.info(
                    f"Download completed: filename={filename}, size={bytes_downloaded} bytes, elapsed={total_download_elapsed:.2f}s, url={url}"
                )

                # Check if content is suspiciously small or if filename indicates a missing Content-Disposition (likely an error page)
                if len(content) < 5120 or filename == "downloaded_file.bin":
                    logging.warning(f"Downloaded content size is small ({len(content)} bytes) or filename is default ('{filename}') from {url}")
                    try:
                        text_content = content.decode('utf-8', errors='ignore')
                        logging.warning(f"Small content preview: {text_content[:500]}")
                    except Exception:
                        pass

                    if retry_count < DOWNLOAD_RETRY_MAX:
                        backoff_seconds = DOWNLOAD_RETRY_BACKOFF_SECONDS * (retry_count + 1)
                        logging.info("Suspecting session expired or download failed. Re-logging and retrying...")
                        time.sleep(backoff_seconds)
                        self.login(force_refresh=True)
                        return self.download(url, retry_count=retry_count + 1)
                    else:
                        raise RuntimeError(f"Download failed after retry: Content too small ({len(content)} bytes) or filename is '{filename}'")

                return content, filename, md5_hash.hexdigest()

        except Exception as e:
            if isinstance(e, UnsupportedFileExtensionError):
                raise e
            if retry_count < DOWNLOAD_RETRY_MAX:
                backoff_seconds = DOWNLOAD_RETRY_BACKOFF_SECONDS * (retry_count + 1)
                logging.warning(
                    f"Download error (attempt {retry_count + 1}/{DOWNLOAD_RETRY_MAX + 1}): {e}. Retrying after {backoff_seconds:.1f}s..."
                )
                time.sleep(backoff_seconds)
                if isinstance(e, requests.exceptions.HTTPError):
                    self.login(force_refresh=True)
                return self.download(url, retry_count=retry_count + 1)
            raise e

# Configuration
# Default to D:\dump_data as per instructions, but allow override for testing
DUMP_DATA_DIR = os.getenv('DUMP_DATA_DIR', r'D:\dump_data')

# Setup logging
# Ensure standard streams use UTF-8 on Windows to avoid UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("link_filename_path.log", encoding='utf-8'),
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

def get_last_checkpoint(session: Session) -> Optional[datetime]:
    """
    Get the process_timestamp of the last successful run of link_filename_path.py
    """
    # Using status='success' to ensure we don't skip data if the last run failed
    record = session.query(ScriptProcessRecord).filter(
        ScriptProcessRecord.script_name == "link_filename_path.py",
        ScriptProcessRecord.status == "success"
    ).order_by(ScriptProcessRecord.process_timestamp.desc()).first()
    
    if record:
        return record.process_timestamp
    return None

def export_contract_from_db(db_name: str, output_file: str, checkpoint: Optional[datetime] = None):
    """
    Export contract table from SQL Server using bcp.
    If checkpoint is provided, only export records with uptime > checkpoint.
    """
    logging.info(f"Exporting contract table from {db_name}...")
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as e:
            logging.error(f"Error creating directory {output_dir}: {e}")
            return

    query = f"SELECT ord, title, intro FROM {db_name}.dbo.contract"
    if checkpoint:
        # Format checkpoint for SQL Server
        # SQL Server datetime format: YYYY-MM-DD HH:MM:SS.mmm
        checkpoint_str = checkpoint.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        query += f" WHERE uptime > '{checkpoint_str}'"
        logging.info(f"Using checkpoint: {checkpoint_str}")
    else:
        logging.info("Performing full export (no checkpoint found).")
        
    cmd = [
        "bcp",
        query,
        "queryout",
        output_file,
        "-c",
        "-T",
        "-S",
        SERVER_INSTANCE
    ]
    
    try:
        logging.info(f"Executing command: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        logging.info(f"Successfully exported to {output_file}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error exporting database {db_name}: {e}")
    except FileNotFoundError:
        logging.error("Error: 'bcp' command not found. Please ensure SQL Server command line tools are installed and in your PATH.")

def rename_knowledge(knowledge_id: str, new_filename: Optional[str] = None, new_title: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Call WeKnora API to rename knowledge.
    PUT /api/v1/knowledge/{id}
    """
    if not knowledge_id:
        return False, "Missing knowledge_id"
        
    url = f"{WEKNORA_API_URL}/api/v1/knowledge/{knowledge_id}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": WEKNORA_API_KEY
    }
    
    payload = {}
    if new_filename:
        payload["file_name"] = new_filename
    if new_title:
        payload["title"] = new_title
        
    if not payload:
        return True, "No changes"

    try:
        response = requests.put(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("success"):
                logging.info(f"Successfully renamed knowledge {knowledge_id} to filename: {new_filename}, title: {new_title}")
                return True, None
            else:
                return False, res_json.get("message")
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)

def process_database_folder(session: Session, db_folder_path: str, session_manager: WeiWoSession = None):
    """
    Process contract.csv in a specific database dump folder.
    """
    
    # Logic to export contract.csv from database
    db_name = os.path.basename(db_folder_path)
    contract_file = os.path.join(db_folder_path, 'contract.csv')
    
    # Get the last checkpoint
    checkpoint = get_last_checkpoint(session)
    
    # Perform export

    export_contract_from_db(db_name, contract_file, checkpoint)

    if not os.path.exists(contract_file):
        msg = f"No contract.csv found in {db_folder_path} after export attempt."
        logging.warning(msg)
        raise FileNotFoundError(msg)

    logging.info(f"Processing {contract_file}")
    
    # Attempt to read with likely encodings
    # SQL Server dumps often use local codepage (e.g. GBK/CP936) or UTF-16
    encodings = ['GB2312', 'utf-8']
    lines = None
    
    for enc in encodings:
        try:
            with open(contract_file, 'r', encoding=enc, errors="ignore") as f:
                # Read all lines to avoid keeping file handle open too long
                lines = f.readlines()
            logging.info(f"Successfully read {contract_file} using {enc} encoding.")
            break
        except UnicodeDecodeError:
            logging.info(f"failed to decode {contract_file} with {enc} encoding.")
            continue
        except Exception as e:
            msg = f"Error reading {contract_file}: {e}"
            logging.error(msg)
            raise RuntimeError(msg)
            
    if lines is None:
        msg = f"Failed to decode {contract_file} with supported encodings."
        logging.error(msg)
        raise ValueError(msg)

    if not lines:
        logging.info(f"File {contract_file} is empty (no records to process).")
        return 0, 0

    update_count = 0
    skip_count = 0
    last_commit_update_count = 0
    
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
            print(extracted_files)
            
            for file_info in extracted_files:
                # 3. Handle zbpath files
                if 'zbpath' in file_info and session_manager:
                    zb_path = file_info['zbpath']
                    filename = file_info['filename']
                    
                    # Check if this zbpath has already been processed
                    existing_zb = session.query(DocumentStatus).filter(DocumentStatus.zb_link == zb_path).first()
                    if existing_zb:
                        logging.info(f"Skipping zbpath {zb_path} (already processed).")
                        skip_count += 1
                        continue

                    try:
                        # Download and get MD5
                        full_zb_path = f"http://192.168.1.70:1011/{zb_path.lstrip('/')}"
                        logging.info(f"Downloading zbpath: {full_zb_path}")
                        content, real_filename, md5_val = session_manager.download(full_zb_path)
                        
                        # Search DB by MD5
                        doc = session.query(DocumentStatus).filter(DocumentStatus.file_hash == md5_val).first()
                        
                        if doc:
                            # Check if filename differs
                            if doc.filename != filename:
                                logging.info(f"Updating via MD5 match (zbpath): {doc.filepath}")
                                logging.info(f"  Old Filename: {doc.filename}")
                                logging.info(f"  New Filename: {filename}")
                                logging.info(f"  Title: {title}, Ord: {ord_val}")
                                
                                doc.filename = filename
                                doc.contract_title = title
                                doc.contract_ord = ord_val
                                doc.zb_link = zb_path # Update zb_link

                                if doc.knowledge_id:
                                    # new_title = title + "_" + filename(without extension)
                                    filename_no_ext = os.path.splitext(filename)[0]
                                    new_title_val = f"{title}_{filename_no_ext}"
                                    
                                    success, msg = rename_knowledge(doc.knowledge_id, new_filename=filename, new_title=new_title_val)
                                    if not success:
                                        logging.error(f"Failed to rename knowledge {doc.knowledge_id}: {msg}")

                                update_count += 1
                            else:
                                # Even if filename matches, we should update zb_link if it's missing
                                if not doc.zb_link:
                                    doc.zb_link = zb_path
                                    doc.contract_title = title
                                    doc.contract_ord = ord_val
                                    update_count += 1
                                    logging.info(f"Updated zb_link for {doc.filename}")
                                else:
                                    skip_count += 1
                        else:
                            logging.warning(f"No DB record found for MD5: {md5_val} (zbpath: {zb_path})")
                            skip_count += 1
                            
                    except Exception as e:
                        logging.error(f"Error processing zbpath {zb_path}: {e}")
                    
                    continue 
                
                # We only process files with 'filepath' (Pattern 1)
                if 'filepath' in file_info:
                    if update_db_record(session, file_info, title, ord_val):
                        update_count += 1
                    else:
                        skip_count += 1
        
            # Batch commit every 10 updates to save progress
            if update_count - last_commit_update_count >= 10:
                try:
                    session.commit()
                    logging.info(f"Committed {update_count} updates...")
                    last_commit_update_count = update_count
                except Exception as e:
                    logging.error(f"Error during batch commit: {e}")
                    session.rollback()

        except Exception as e:
            logging.error(f"Error processing line in {contract_file}: {e}")
            
    # Final commit for the file
    try:
        session.commit()
    except Exception as e:
        logging.error(f"Error during final commit for {contract_file}: {e}")
        session.rollback()

    logging.info(f"Finished {contract_file}. Updated: {update_count}, Skipped/NoChange: {skip_count}")
    return update_count, skip_count

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
            
            if doc.file_status == 'completed' and doc.knowledge_id:
                # new_title = title + "_" + filename(without extension)
                filename_no_ext = os.path.splitext(real_name)[0]
                new_title_val = f"{title}_{filename_no_ext}"

                success, msg = rename_knowledge(doc.knowledge_id, new_filename=real_name, new_title=new_title_val)
                if not success:
                    logging.error(f"Failed to rename knowledge {doc.knowledge_id}: {msg}")
            
            return True
            
    return False

def main():
    start_time = time.time()

    if not os.path.exists(DUMP_DATA_DIR):
        logging.error(f"Dump directory not found: {DUMP_DATA_DIR}")
        logging.info("Please ensure dump_contract.ps1 has been executed and DUMP_DATA_DIR is set correctly.")
        return

    logging.info(f"Starting database update from {DUMP_DATA_DIR}")
    
    # Initialize DB (ensure tables exist)
    init_db() 
    session = get_session()
    
    # Initialize WeiWoSession
    session_manager = None
    try:
        if 'WeiWoSession' in globals():
            session_manager = WeiWoSession()
            logging.info("WeiWoSession initialized successfully.")
        else:
            logging.warning("WeiWoSession not available, skipping zbpath processing.")
    except Exception as e:
        logging.error(f"Failed to initialize WeiWoSession: {e}")

    total_updated = 0
    total_skipped = 0

    try:
        # Iterate over subdirectories in DUMP_DATA_DIR
        # Each subdirectory corresponds to a database
        for entry in os.scandir(DUMP_DATA_DIR):
            if entry.is_dir() and "zbintel117_erp" == entry.name:
                logging.info(f"Scanning database folder: {entry.name}")
                updated, skipped = process_database_folder(session, entry.path, session_manager)
                total_updated += updated
                total_skipped += skipped
        
        # Create success record
        duration = time.time() - start_time
        record = ScriptProcessRecord(
            script_name="link_filename_path.py",
            process_duration=duration,
            process_count=total_updated + total_skipped,
            insert_count=0,
            update_count=total_updated,
            delete_count=0,
            process_timestamp=datetime.now(),
            status="success"
        )
        session.add(record)

        session.commit()
        logging.info("Database update committed successfully.")
        
    except Exception as e:
        session.rollback()
        # Create failure record
        try:
            duration = time.time() - start_time
            fail_record = ScriptProcessRecord(
                script_name="link_filename_path.py",
                process_duration=duration,
                process_count=total_updated + total_skipped,
                process_timestamp=datetime.now(),
                status="failed",
                failed_reason=str(e)
            )
            session.add(fail_record)
            session.commit()
        except Exception as record_error:
            logging.error(f"Failed to save failure record: {record_error}")
            
        logging.error(f"Fatal error during execution: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
