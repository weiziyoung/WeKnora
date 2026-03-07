import logging
from typing import List, Tuple
from docreader.proto.docreader_pb2 import Chunk

logger = logging.getLogger(__name__)

try:
    from langchain_text_splitters import MarkdownHeaderTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    logger.warning("langchain-text-splitters not installed, skipping langchain splitters")
    LANGCHAIN_AVAILABLE = False

def split_by_markdown_header(text: str) -> List[Chunk]:
    """
    Use Langchain's MarkdownHeaderTextSplitter to split text.
    """
    if not LANGCHAIN_AVAILABLE:
        return []
    
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
    ]
    
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    docs = splitter.split_text(text)
    
    chunks = []
    current_pos = 0
    
    for i, doc in enumerate(docs):
        # Reconstruct header context from metadata
        header_context = ""
        for header_len, header_name in headers_to_split_on:
            if header_name in doc.metadata:
                header_val = doc.metadata[header_name]
                # Reconstruct the header line
                header_context += f"{header_len} {header_val}\n"
        
        # Prepend headers to content
        content = header_context + doc.page_content
        
        # We need to estimate start/end because langchain doesn't give character positions easily
        # This is an approximation.
        start = current_pos
        end = start + len(content)
        current_pos = end
        
        chunk = Chunk(
            seq=i,
            content=content,
            start=start,
            end=end
        )
        chunks.append(chunk)
        
    return chunks
