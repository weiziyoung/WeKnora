import logging
import re
import time
import zipfile
import io
import os
import uuid
from typing import Dict, Optional
from io import BytesIO

import markdownify
import requests

try:
    import alibabacloud_oss_v2 as oss
except ImportError:
    oss = None

from docreader.config import CONFIG
from docreader.models.document import Document
from docreader.parser.base_parser import BaseParser
from docreader.parser.chain_parser import PipelineParser
from docreader.parser.markdown_parser import MarkdownImageUtil, MarkdownTableFormatter
from docreader.utils import endecode

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class StdMinerUParser(BaseParser):
    """
    Standard MinerU Parser for document parsing.

    This parser uses MinerU API to parse documents (especially PDFs) into markdown format,
    with support for tables, formulas, and images extraction.
    """

    def __init__(
            self,
            enable_markdownify: bool = True,
            mineru_endpoint: Optional[str] = None,  # Added: 支持传入自定义 endpoint
            **kwargs,
    ):
        """
        Initialize MinerU parser.

        Args:
            enable_markdownify: Whether to convert HTML tables to markdown format
            mineru_endpoint: MinerU API endpoint URL
            **kwargs: Additional arguments passed to BaseParser
        """
        super().__init__(**kwargs)
        # Get MinerU endpoint from environment variable or parameter
        # Modified: 优先使用传入的参数，否则使用 Config
        base_url = mineru_endpoint if mineru_endpoint else CONFIG.mineru_endpoint
        self.minerU = base_url.rstrip("/") if base_url else ""

        self.enable_markdownify = enable_markdownify
        # Helper for processing markdown images
        self.image_helper = MarkdownImageUtil()
        # Pattern to match base64 encoded images
        self.base64_pattern = re.compile(r"data:image/(\w+);base64,(.*)")
        # Check if MinerU API is available
        self.enable = self.ping()

    def ping(self, timeout: int = 5) -> bool:
        """
        Check if MinerU API is available.

        Args:
            timeout: Request timeout in seconds

        Returns:
            True if API is available, False otherwise
        """
        try:
            response = requests.get(
                self.minerU + "/docs", timeout=timeout, allow_redirects=True
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def parse_into_text(self, content: bytes) -> Document:
        """
        Parse document content into text using MinerU API.

        Args:
            content: Raw document content in bytes

        Returns:
            Document object containing parsed text and images
        """
        if not self.enable:
            logger.debug("MinerU API is not enabled")
            return Document()

        logger.info(f"Parsing scanned PDF via MinerU API (size: {len(content)} bytes)")
        md_content: str = ""
        images_b64: Dict[str, str] = {}
        try:
            # Call MinerU API to parse document
            response = requests.post(
                url=self.minerU + "/file_parse",
                data={
                    "return_md": True,  # Return markdown content
                    "return_images": True,  # Return extracted images
                    "lang_list": ["ch", "en"],  # Support Chinese and English
                    "table_enable": True,  # Enable table parsing
                    "formula_enable": True,  # Enable formula parsing
                    "parse_method": "auto",  # Auto detect parsing method
                    "start_page_id": 0,  # Start from first page
                    "end_page_id": 99999,  # Parse all pages
                    "backend": "pipeline",  # Use pipeline backend
                    "response_format_zip": False,  # Return JSON instead of ZIP
                    "return_middle_json": False,  # Don't return intermediate JSON
                    "return_model_output": False,  # Don't return model output
                    "return_content_list": False,  # Don't return content list
                },
                files={"files": content},
                timeout=1000,
            )
            response.raise_for_status()
            result = response.json()["results"]["files"]
            md_content = result["md_content"]
            images_b64 = result.get("images", {})
        except Exception as e:
            logger.error(f"MinerU parsing failed: {e}", exc_info=True)
            return Document()

        # Convert HTML tables in markdown to markdown table format
        if self.enable_markdownify:
            logger.debug("Converting HTML to Markdown")
            md_content = markdownify.markdownify(md_content)

        images = {}
        image_replace = {}
        # Filter images that are actually used in markdown content
        # Some images in images_b64 may not be referenced in md_content
        # (e.g., images embedded in tables), so we need to filter them
        for ipath, b64_str in images_b64.items():
            # Skip images that are not referenced in markdown content
            if f"images/{ipath}" not in md_content:
                logger.debug(f"Image {ipath} not used in markdown")
                continue
            # Parse base64 image data
            match = self.base64_pattern.match(b64_str)
            if match:
                # Extract image format (e.g., png, jpg)
                file_ext = match.group(1)
                # Extract base64 encoded data
                b64_str = match.group(2)

                # Decode base64 string to bytes
                image_bytes = endecode.encode_image(b64_str, errors="ignore")
                if not image_bytes:
                    logger.error("Failed to decode base64 image skip it")
                    continue

                # Upload image to storage and get URL
                image_url = self.storage.upload_bytes(
                    image_bytes, file_ext=f".{file_ext}"
                )

                # Store image mapping for later use
                images[image_url] = b64_str
                # Prepare replacement mapping for markdown content
                image_replace[f"images/{ipath}"] = image_url

        logger.info(f"Replaced {len(image_replace)} images in markdown")
        # Replace image paths in markdown with uploaded URLs
        text = self.image_helper.replace_path(md_content, image_replace)

        logger.info(
            f"Successfully parsed PDF, text: {len(text)}, images: {len(images)}"
        )
        return Document(content=text, images=images)


# Added: 新增 MinerUCloudParser 类，支持异步任务提交
class MinerUCloudParser(StdMinerUParser):
    """
    MinerU Parser for REMOTE/CLOUD API (Asynchronous).
    Uses the /submit -> /status -> /result workflow.
    """

    SUBMIT_TIMEOUT = 30
    POLL_INTERVAL = 2
    MAX_WAIT_TIME = 600

    def parse_into_text(self, content: bytes) -> Document:
        """
        Parse document content using Cloud MinerU API (Async/Polling).
        """
        if not self.enable:
            return Document()

        logger.info(f"Parsing PDF via Cloud MinerU API (size: {len(content)} bytes)")

        try:
            # --- Step 1: Submit Task ---
            submit_url = f"{self.minerU}/submit"
            logger.info(f"Submitting task to {submit_url}")

            response = requests.post(
                url=submit_url,
                files={"files": content},
                data={
                    "enable_formula": "true",
                    "enable_table": "true",
                    "layout_model": "doclayout_yolo",
                    "backend": "pipeline",
                },
                timeout=self.SUBMIT_TIMEOUT,
            )
            response.raise_for_status()

            # Robust task_id extraction
            resp_data = response.json()
            task_id = resp_data.get("task_id") or resp_data.get("data", {}).get("task_id")

            if not task_id:
                raise ValueError(f"No task_id in response: {resp_data}")

            logger.info(f"Task submitted, ID: {task_id}, waiting for completion...")

            # --- Step 2: Poll Status ---
            start_time = time.time()

            while True:
                if time.time() - start_time > self.MAX_WAIT_TIME:
                    raise TimeoutError(f"Task {task_id} timed out after {self.MAX_WAIT_TIME}s")

                try:
                    status_resp = requests.get(
                        f"{self.minerU}/status/{task_id}",
                        timeout=10
                    )
                    status_resp.raise_for_status()
                    status_data = status_resp.json()
                except requests.RequestException as e:
                    logger.warning(f"Status check failed for {task_id}: {e}. Retrying...")
                    time.sleep(self.POLL_INTERVAL)
                    continue

                state = status_data.get("status") or status_data.get("state")

                if state in ["done", "success"]:
                    break
                elif state == "failed":
                    error_msg = status_data.get("error") or "Unknown error"
                    raise RuntimeError(f"Task {task_id} failed: {error_msg}")
                else:
                    time.sleep(self.POLL_INTERVAL)

            # --- Step 3: Get Result ---
            result_resp = requests.get(
                f"{self.minerU}/result/{task_id}",
                timeout=30
            )
            result_resp.raise_for_status()
            result_json = result_resp.json()

            # Normalize result data
            result_data = result_json.get("result", result_json)

            md_content = result_data.get("md_content", "")
            images_b64 = result_data.get("images", {})

            # 使用父类的方法处理图片和Markdown转换 (复用现有逻辑)

            # Convert HTML tables
            if self.enable_markdownify:
                md_content = markdownify.markdownify(md_content)

            images = {}
            image_replace = {}

            for ipath, b64_str in images_b64.items():
                if f"images/{ipath}" not in md_content:
                    continue
                match = self.base64_pattern.match(b64_str)
                if match:
                    file_ext = match.group(1)
                    b64_str_clean = match.group(2)
                    image_bytes = endecode.encode_image(b64_str_clean, errors="ignore")
                    if not image_bytes: continue

                    if self.storage:
                        image_url = self.storage.upload_bytes(image_bytes, file_ext=f".{file_ext}")
                        images[image_url] = b64_str_clean
                        image_replace[f"images/{ipath}"] = image_url

            if image_replace:
                md_content = self.image_helper.replace_path(md_content, image_replace)

            return Document(content=md_content, images=images)

        except Exception as e:
            logger.error(f"Cloud MinerU parsing failed: {e}", exc_info=True)
            return Document()


class AliyunOSSHelper:
    """
    Helper class for temporary file upload to Aliyun OSS.
    Used by MinerUAPIParser to expose local files to the public internet for API processing.
    """

    def __init__(self):
        if not oss:
            raise ImportError("alibabacloud-oss-v2 is not installed")
            
        # Setup credentials
        self.credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=CONFIG.oss_access_key,
            access_key_secret=CONFIG.oss_secret_key
        )
        # Setup config
        self.cfg = oss.config.load_default()
        self.cfg.credentials_provider = self.credentials_provider
        self.cfg.region = CONFIG.oss_region
        if CONFIG.oss_endpoint:
            self.cfg.endpoint = CONFIG.oss_endpoint
        
        self.client = oss.Client(self.cfg)
        self.bucket = CONFIG.oss_bucket

    def upload_bytes(self, content: bytes, file_ext: str = ".pdf") -> Optional[str]:
        """Uploads bytes to OSS and returns public URL"""
        if not self.bucket or not self.cfg.region:
            logger.warning("OSS configuration missing (bucket or region)")
            return None

        filename = f"mineru_temp/{uuid.uuid4()}{file_ext}"
        logger.info(f"Uploading temporary file to OSS: {filename}...")
        
        try:
            request = oss.PutObjectRequest(
                bucket=self.bucket,
                key=filename,
                body=BytesIO(content)
            )
            result = self.client.put_object(request)
            
            if result.status_code != 200:
                logger.error(f"OSS Upload failed with status {result.status_code}")
                return None
                
            # Construct public URL
            # Default to HTTPS
            endpoint = self.cfg.endpoint if self.cfg.endpoint else f"oss-{self.cfg.region}.aliyuncs.com"
            # Remove protocol if present to ensure clean construction, then add https
            endpoint = endpoint.replace("http://", "").replace("https://", "")
            
            url = f"https://{self.bucket}.{endpoint}/{filename}"
            return url
            
        except Exception as e:
            logger.error(f"OSS Upload Error: {e}", exc_info=True)
            return None


class MinerUAPIParser(StdMinerUParser):
    """
    MinerU Parser for Official API (mineru.net).
    Uses the official API workflow: Submit -> Poll -> Download ZIP -> Extract.
    """

    SUBMIT_TIMEOUT = 30
    POLL_INTERVAL = 2
    MAX_WAIT_TIME = 600

    def __init__(
            self,
            mineru_api_token: Optional[str] = None,
            **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_token = mineru_api_token if mineru_api_token else CONFIG.mineru_api_token
        # Base URL for official API
        self.mineru_base_url = "https://mineru.net/api/v4"
        # Force enable since we don't rely on ping() for API
        self.enable = True

    def parse_into_text(self, content: bytes) -> Document:
        """
        Parse document content using Official MinerU API.
        """

        if not self.api_token:
            logger.warning("MinerU API token is missing")
            return Document()

        try:
            # --- Step 1: Upload file to storage to get URL ---
            # We assume the content is PDF by default as per typical usage,
            # or we could try to detect from content if needed.
            # But upload_bytes requires an extension.
            
            # Try to use OSS Helper first if configured, to ensure public access
            file_url = None
            if CONFIG.oss_access_key and CONFIG.oss_bucket:
                try:
                    oss_helper = AliyunOSSHelper()
                    file_url = oss_helper.upload_bytes(content, file_ext=".pdf")
                except Exception as e:
                    logger.warning(f"Failed to initialize or use OSS Helper: {e}")
            
            # Fallback to default storage if OSS failed or not configured
            if not file_url:
                file_url = self.storage.upload_bytes(content, file_ext=".pdf")
            
            if not file_url:
                logger.error("Failed to upload file to storage for MinerU API")
                return Document()

            logger.info(f"File uploaded to storage: {file_url}")

            # Check for local URL which cannot be accessed by external API
            if any(x in file_url for x in ["localhost", "127.0.0.1", "minio", "host.docker.internal"]):
                logger.warning(
                    f"The file URL '{file_url}' appears to be a local address. "
                    "The official MinerU API (cloud service) cannot access local files. "
                    "Please use a public storage service (COS/OSS/S3) or expose your local MinIO to the internet."
                )

            # --- Step 2: Submit Task ---
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_token}"
            }
            submit_url = f"{self.mineru_base_url}/extract/task"

            response = requests.post(
                submit_url,
                headers=headers,
                json={"url": file_url, "model_version": "vlm"},
                timeout=self.SUBMIT_TIMEOUT
            )
            response.raise_for_status()
            resp_json = response.json()
            logger.info(f"MinerU API response: {resp_json}")

            # Extract task_id
            # The API response structure might vary, handle both direct ID or dict with ID
            task_data = resp_json.get("data")
            task_id = None
            if isinstance(task_data, str):
                task_id = task_data
            elif isinstance(task_data, dict):
                task_id = task_data.get("id") or task_data.get("task_id")

            if not task_id:
                raise ValueError(f"No task_id in response: {resp_json}")

            logger.info(f"Task submitted, ID: {task_id}, waiting for completion...")

            # --- Step 3: Poll Status ---
            start_time = time.time()
            result_data = None

            while True:
                if time.time() - start_time > self.MAX_WAIT_TIME:
                    raise TimeoutError(f"Task {task_id} timed out after {self.MAX_WAIT_TIME}s")

                try:
                    status_url = f"{self.mineru_base_url}/extract/task/{task_id}"
                    status_resp = requests.get(status_url, headers=headers, timeout=10)
                    status_resp.raise_for_status()
                    status_json = status_resp.json()
                    
                    data = status_json.get("data", {})
                    # Status field might be 'state' or 'status'
                    state = data.get("state") or data.get("status")
                    
                    # Fallback check at root level if data is empty or structure differs
                    if not state:
                        state = status_json.get("state") or status_json.get("status")

                    if state in ["done", "success", "completed", "succeeded"]:
                        result_data = data
                        break
                    elif state in ["failed", "error"]:
                        error_msg = data.get("error") or "Unknown error"
                        raise RuntimeError(f"Task {task_id} failed: {error_msg}")
                    else:
                        time.sleep(self.POLL_INTERVAL)
                except requests.RequestException as e:
                    logger.warning(f"Status check failed for {task_id}: {e}. Retrying...")
                    time.sleep(self.POLL_INTERVAL)
                    continue

            # --- Step 4: Get Result (ZIP) ---
            # The result data should contain the zip url
            zip_url = result_data.get("full_zip_url")
            if not zip_url:
                # Try finding it in keys ending with _zip_url or similar if exact key differs
                for k, v in result_data.items():
                    if isinstance(k, str) and k.endswith("zip_url") and v:
                        zip_url = v
                        break
            
            if not zip_url:
                raise ValueError(f"No zip url found in result: {result_data}")

            logger.info(f"Downloading result ZIP from {zip_url}")
            zip_resp = requests.get(zip_url, timeout=60)
            zip_resp.raise_for_status()

            # --- Step 5: Extract and Process ZIP ---
            with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
                # Find markdown file (e.g., full.md, output.md)
                md_filename = None
                # Prefer 'full.md' as requested, otherwise take any .md
                for name in z.namelist():
                    if name.endswith("full.md") and not name.startswith("__MACOSX"):
                        md_filename = name
                        break
                
                if not md_filename:
                    # Fallback to any .md file
                    for name in z.namelist():
                        if name.endswith(".md") and not name.startswith("__MACOSX"):
                            md_filename = name
                            break
                
                if not md_filename:
                    logger.warning("No markdown file found in ZIP result")
                    return Document()

                logger.info(f"Found markdown file: {md_filename}")
                md_content = z.read(md_filename).decode("utf-8")
                md_dir = os.path.dirname(md_filename)

                # Process Images
                images = {}
                image_replace = {}

                # Iterate through all files in ZIP to find images
                for name in z.namelist():
                    if name.startswith("__MACOSX"):
                        continue
                    
                    lower_name = name.lower()
                    if lower_name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                        try:
                            # Read image content
                            img_bytes = z.read(name)
                            if not img_bytes:
                                continue
                                
                            # Upload to storage
                            file_ext = os.path.splitext(name)[1]
                            img_url = self.storage.upload_bytes(img_bytes, file_ext=file_ext)
                            
                            # Store in images dict (using empty string for base64 as we don't have it easily/needed)
                            images[img_url] = "" 
                            
                            # Calculate relative path from markdown file to image file
                            # This is crucial for replacing the links correctly
                            # If md is "output/full.md" and img is "output/images/1.jpg"
                            # The link in md is likely "images/1.jpg"
                            # Relpath from "output" to "output/images/1.jpg" is "images/1.jpg"
                            
                            # However, we must handle paths carefully. 
                            # If md is at root "", dirname is "".
                            rel_path = os.path.relpath(name, md_dir)
                            
                            # Add to replacement map
                            # We replace strict relative path match
                            image_replace[rel_path] = img_url
                            
                            # Also try with './' prefix just in case
                            image_replace[f"./{rel_path}"] = img_url
                            
                        except Exception as img_err:
                            logger.warning(f"Failed to process image {name}: {img_err}")

                # Replace image paths in markdown
                if image_replace:
                    logger.info(f"Replacing {len(image_replace)} images in markdown")
                    md_content = self.image_helper.replace_path(md_content, image_replace)

                return Document(content=md_content, images=images)

        except Exception as e:
            logger.error(f"MinerU API parsing failed: {e}", exc_info=True)
            return Document()


class MinerUParser(PipelineParser):
    """
    MinerU Parser with pipeline processing.

    This parser combines StdMinerUParser (or MinerUAPIParser) for document parsing and
    MarkdownTableFormatter for table formatting in a pipeline.
    """

    _parser_cls = (StdMinerUParser, MarkdownTableFormatter)

    def __init__(self, *args, **kwargs):
        """
        Initialize MinerUParser.
        
        It automatically selects between StdMinerUParser and MinerUAPIParser based on configuration.
        """
        mineru_endpoint = kwargs.get("mineru_endpoint") or CONFIG.mineru_endpoint
        mineru_api_token = kwargs.get("mineru_api_token") or CONFIG.mineru_api_token
        
        logger.info(f"MinerUParser Init - Endpoint: '{mineru_endpoint}', Token: '{mineru_api_token}'")

        # Priority logic:
        # 1. If mineru_endpoint is provided (not empty), use self-hosted StdMinerUParser
        # 2. If mineru_api_token is provided (not empty), use official MinerUAPIParser
        # 3. Default to StdMinerUParser (which will likely fail if no endpoint, but maintains backward compat)
        
        if mineru_endpoint:
            logger.info(f"MinerUParser: Using StdMinerUParser (Endpoint: {mineru_endpoint})")
            # If backend is pipeline, we might want to use MinerUCloudParser?
            # For now, stick to StdMinerUParser which is synchronous
            self._parser_cls = (StdMinerUParser, MarkdownTableFormatter)
        elif mineru_api_token:
            logger.info("MinerUParser: Using MinerUAPIParser (Official API)")
            self._parser_cls = (MinerUAPIParser, MarkdownTableFormatter)
        else:
            logger.info("MinerUParser: Defaulting to StdMinerUParser (No specific config found)")
            self._parser_cls = (StdMinerUParser, MarkdownTableFormatter)
            
        super().__init__(*args, **kwargs)


if __name__ == "__main__":
    import os

    # Example usage for testing
    logging.basicConfig(level=logging.DEBUG)

    # Configure your file path and MinerU endpoint
    your_file = "/path/to/your/file.pdf"

    # Added: 修改为 Localhost 方便测试
    test_endpoint = "http://localhost:9987"
    os.environ["MINERU_ENDPOINT"] = test_endpoint

    # Create parser instance
    # Modified: 传入 endpoint
    parser = MinerUParser(mineru_endpoint=test_endpoint)

    # Parse PDF file
    if os.path.exists(your_file):
        with open(your_file, "rb") as f:
            content = f.read()
            document = parser.parse_into_text(content)
            logger.error(document.content)
    else:
        print(f"File not found: {your_file}")