"""File Processor for Niv AI — handles uploaded files in chat.

Converts uploaded files into content that LLMs can understand:
- Images (jpg/png/gif/webp) → base64 data URL for vision models
- PDF → extracted text via pdfplumber
- Excel/CSV → parsed headers + sample rows as text
- Word (.docx) → extracted text
"""
import frappe
import os
import base64
import json
from typing import Optional


# Supported file types
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
PDF_EXTENSIONS = {".pdf"}
EXCEL_EXTENSIONS = {".xlsx", ".xls", ".csv"}
WORD_EXTENSIONS = {".docx", ".doc"}

# Limits
MAX_IMAGE_SIZE_MB = 10
MAX_TEXT_CHARS = 8000  # Max extracted text to send to LLM
MAX_EXCEL_ROWS = 20   # Sample rows to show


def process_attachments(attachments: list) -> dict:
    """Process a list of attachments and return content for LLM.
    
    Args:
        attachments: List of dicts with 'file_url' key
    
    Returns:
        dict with:
            - 'images': list of base64 data URLs (for vision)
            - 'text_context': string of extracted text (for text LLM)
            - 'file_names': list of processed file names
    """
    result = {
        "images": [],
        "text_context": "",
        "file_names": [],
    }
    
    if not attachments:
        return result
    
    text_parts = []
    
    for attachment in attachments:
        file_url = attachment.get("file_url", "")
        if not file_url:
            continue
        
        # Get file path on disk
        file_path = _get_file_path(file_url)
        if not file_path or not os.path.exists(file_path):
            continue
        
        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_name)[1].lower()
        result["file_names"].append(file_name)
        
        try:
            if ext in IMAGE_EXTENSIONS:
                # Image → base64 for vision model
                image_data = _process_image(file_path)
                if image_data:
                    result["images"].append(image_data)
            
            elif ext in PDF_EXTENSIONS:
                # PDF → extract text
                text = _process_pdf(file_path)
                if text:
                    text_parts.append(f"[Content from {file_name}]:\n{text}")
            
            elif ext in EXCEL_EXTENSIONS:
                # Excel/CSV → parse data
                text = _process_excel(file_path, ext)
                if text:
                    text_parts.append(f"[Data from {file_name}]:\n{text}")
            
            elif ext in WORD_EXTENSIONS:
                # Word → extract text
                text = _process_word(file_path)
                if text:
                    text_parts.append(f"[Content from {file_name}]:\n{text}")
            
            else:
                # Unknown file — just mention it
                text_parts.append(f"[File attached: {file_name} ({ext})]")
        
        except Exception as e:
            frappe.log_error(f"Niv AI: File processing error for {file_name}: {e}", "Niv File Processor")
            text_parts.append(f"[Failed to process {file_name}: {str(e)[:100]}]")
    
    if text_parts:
        result["text_context"] = "\n\n".join(text_parts)[:MAX_TEXT_CHARS]
    
    return result


def _get_file_path(file_url: str) -> Optional[str]:
    """Convert Frappe file URL to absolute file path."""
    if not file_url:
        return None
    
    # Handle /files/ URLs
    if file_url.startswith("/files/"):
        site_path = frappe.get_site_path()
        return os.path.join(site_path, "public", file_url.lstrip("/"))
    
    # Handle /private/files/ URLs
    if file_url.startswith("/private/files/"):
        site_path = frappe.get_site_path()
        return os.path.join(site_path, file_url.lstrip("/"))
    
    # Handle full paths
    if os.path.isabs(file_url):
        return file_url
    
    return None


def _process_image(file_path: str) -> Optional[str]:
    """Convert image to base64 data URL for vision models."""
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    if file_size > MAX_IMAGE_SIZE_MB:
        return None
    
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    
    return f"data:{mime_type};base64,{data}"


def _process_pdf(file_path: str) -> Optional[str]:
    """Extract text from PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return "[PDF processing unavailable — pdfplumber not installed]"
    
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages[:20]):  # Max 20 pages
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {i+1} ---\n{page_text}")
    
    full_text = "\n\n".join(text_parts)
    if len(full_text) > MAX_TEXT_CHARS:
        full_text = full_text[:MAX_TEXT_CHARS] + f"\n\n[... truncated, {len(full_text)} total chars]"
    
    return full_text or "[PDF has no extractable text — may be scanned/image-based]"


def _process_excel(file_path: str, ext: str) -> Optional[str]:
    """Parse Excel/CSV and return header + sample rows as text."""
    try:
        import pandas as pd
    except ImportError:
        return "[Excel processing unavailable — pandas not installed]"
    
    try:
        if ext == ".csv":
            df = pd.read_csv(file_path, nrows=MAX_EXCEL_ROWS + 1)
        else:
            df = pd.read_excel(file_path, nrows=MAX_EXCEL_ROWS + 1)
    except Exception as e:
        return f"[Failed to parse: {str(e)[:100]}]"
    
    total_rows = len(df)
    headers = list(df.columns)
    
    # Build text representation
    lines = [f"Columns ({len(headers)}): {', '.join(str(h) for h in headers)}"]
    lines.append(f"Total rows shown: {min(total_rows, MAX_EXCEL_ROWS)}")
    lines.append("")
    
    # Add sample rows as markdown table
    sample = df.head(MAX_EXCEL_ROWS)
    lines.append(sample.to_markdown(index=False))
    
    return "\n".join(lines)


def _process_word(file_path: str) -> Optional[str]:
    """Extract text from Word document."""
    try:
        from docx import Document
    except ImportError:
        return "[Word processing unavailable — python-docx not installed]"
    
    doc = Document(file_path)
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n".join(text_parts)
    
    if len(full_text) > MAX_TEXT_CHARS:
        full_text = full_text[:MAX_TEXT_CHARS] + f"\n\n[... truncated]"
    
    return full_text or "[Word document is empty]"
