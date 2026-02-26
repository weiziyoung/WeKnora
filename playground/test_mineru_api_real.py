
import os
import sys
import logging
import requests
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# --- MOCK DEPENDENCIES START ---
# We mock dependencies that might be missing or not needed for this specific test
for mod in ["qcloud_cos", "minio", "ollama", "openai", "numpy", "pandas", 
            "docx", "openpyxl", "pptx", "bs4", "lxml", "fitz", "paddle", 
            "paddleocr", "layoutparser", "playwright", 
            "trafilatura", "goose3", "markitdown", "textract", "cv2", 
            "pdfplumber", "PIL", "camelot"]:
    if mod not in sys.modules:
        try:
            __import__(mod)
        except ImportError:
            sys.modules[mod] = MagicMock()
            if mod == "docx":
                sys.modules["docx.image"] = MagicMock()
                sys.modules["docx.image.exceptions"] = MagicMock()
            elif mod == "PIL":
                sys.modules["PIL.Image"] = MagicMock()
            elif mod == "playwright":
                sys.modules["playwright.sync_api"] = MagicMock()
                sys.modules["playwright.async_api"] = MagicMock()

# Mock pydantic if missing
try:
    import pydantic
except ImportError:
    sys.modules["pydantic"] = MagicMock()
    class MockBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    sys.modules["pydantic"].BaseModel = MockBaseModel
    sys.modules["pydantic"].Field = MagicMock()
# --- MOCK DEPENDENCIES END ---

# Import real parser
try:
    from docreader.parser.mineru_parser import MinerUAPIParser
    from docreader.models.document import Document
    from docreader.config import CONFIG
except ImportError as e:
    print(f"Failed to import MinerUAPIParser: {e}")
    sys.exit(1)

# Local file path
LOCAL_FILE = "/app/playground/改造合同.pdf"

def main():
    # setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("docreader.parser.mineru_parser")
    logger.setLevel(logging.INFO)
    
    print(f"Reading local file: {LOCAL_FILE}")
    if not os.path.exists(LOCAL_FILE):
        print(f"Error: File not found: {LOCAL_FILE}")
        return

    with open(LOCAL_FILE, "rb") as f:
        pdf_content = f.read()
    
    print(f"Read {len(pdf_content)} bytes.")

    # Check Config
    print(f"Checking Config for OSS...")
    print(f"OSS_BUCKET: {CONFIG.oss_bucket}")
    print(f"OSS_REGION: {CONFIG.oss_region}")
    print(f"OSS_ACCESS_KEY: {'***' if CONFIG.oss_access_key else 'None'}")
    
    if not CONFIG.oss_bucket or not CONFIG.oss_access_key:
        print("Warning: OSS Config missing! MinerUAPIParser might fail to upload to OSS.")

    # Initialize Parser
    print("Initializing MinerUAPIParser...")
    # Token is loaded from CONFIG or env
    parser = MinerUAPIParser()
    
    # We DO NOT mock storage here, because we want to test the internal AliyunOSSHelper logic
    # parser.storage is still the default (mocked or real), but MinerUAPIParser should try OSS first.
    # To be safe, we can mock self.storage to ensure it falls back to it if OSS fails (or verify it DOESN'T use it if OSS succeeds)
    parser.storage = MagicMock()
    parser.storage.upload_bytes.return_value = "http://mock-storage/fallback.pdf"

    print("Starting parsing process...")
    try:
        doc = parser.parse_into_text(pdf_content)
        
        print("\n--- Parsing Result ---")
        if doc.content:
            print(f"Content length: {len(doc.content)}")
            print("Preview (first 500 chars):")
            print(doc.content[:500])
            print("\nImages found:", len(doc.images))
        else:
            print("No content extracted.")
            
    except Exception as e:
        print(f"Parsing failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
