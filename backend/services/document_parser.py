"""
Document parsing service with Redis caching.

Extracts text from PDF, DOCX, TXT, and RTF files with caching to avoid
repeated expensive parsing operations.
"""

import os
import hashlib
from typing import Optional
import logging

from services.redis_service import redis_service
from config import settings

logger = logging.getLogger(__name__)

# Cache key prefix for document content
CACHE_PREFIX = "doc_content:"


def _get_cache_key(doc_id: int, file_path: str) -> str:
    """
    Generate cache key based on document ID and file modification time.

    This ensures cache is invalidated when the file changes.
    """
    try:
        mtime = os.path.getmtime(file_path)
        return f"{CACHE_PREFIX}{doc_id}:{int(mtime)}"
    except OSError:
        return f"{CACHE_PREFIX}{doc_id}"


def _extract_text_from_file(file_path: str, filename: str) -> str:
    """
    Extract text content from a document file.

    Supports PDF, DOCX, TXT, and RTF formats.
    """
    file_ext = os.path.splitext(filename)[1].lower()
    content = ""

    if file_ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

    elif file_ext == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                content = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        except ImportError:
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    content = '\n'.join(page.extract_text() or '' for page in reader.pages)
            except ImportError:
                raise RuntimeError("PDF parsing libraries not available")

    elif file_ext in ['.doc', '.docx']:
        try:
            import docx
            doc_file = docx.Document(file_path)
            content = '\n'.join(para.text for para in doc_file.paragraphs)
        except ImportError:
            raise RuntimeError("DOCX parsing library not available")

    elif file_ext == '.rtf':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

    return content


def get_document_content(doc_id: int, file_path: str, filename: str) -> Optional[str]:
    """
    Get document content with Redis caching.

    First checks cache, then extracts and caches if not found.

    Args:
        doc_id: Database document ID
        file_path: Path to the document file
        filename: Original filename (for extension detection)

    Returns:
        Extracted text content or None on error
    """
    if not os.path.exists(file_path):
        return None

    cache_key = _get_cache_key(doc_id, file_path)

    # Try cache first
    try:
        cached = redis_service.cache_get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for document {doc_id}")
            return cached
    except Exception as e:
        logger.warning(f"Redis cache read failed: {e}")

    # Extract content
    try:
        content = _extract_text_from_file(file_path, filename)
    except Exception as e:
        logger.error(f"Failed to extract text from document {doc_id}: {e}")
        raise

    # Cache the extracted content
    try:
        redis_service.cache_set(
            cache_key,
            content,
            ttl_seconds=settings.cache_ttl_documents
        )
        logger.debug(f"Cached content for document {doc_id}")
    except Exception as e:
        logger.warning(f"Redis cache write failed: {e}")

    return content


def invalidate_document_cache(doc_id: int) -> bool:
    """
    Invalidate all cached content for a document.

    Call this when a document is deleted or updated.

    Args:
        doc_id: Database document ID

    Returns:
        True if invalidation succeeded
    """
    try:
        pattern = f"{CACHE_PREFIX}{doc_id}:*"
        deleted = redis_service.cache_delete_pattern(pattern)
        logger.debug(f"Invalidated {deleted} cache entries for document {doc_id}")
        return True
    except Exception as e:
        logger.warning(f"Cache invalidation failed for document {doc_id}: {e}")
        return False
