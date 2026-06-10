"""Resume upload parsing helpers.

The project intentionally keeps dependencies minimal. TXT parsing is exact.
PDF/DOCX parsing is best-effort plain-text extraction from uploaded bytes.
"""

from __future__ import annotations

import base64
import re
import zipfile
from io import BytesIO


SUPPORTED_RESUME_TYPES = {".pdf", ".docx", ".txt"}


def file_extension(file_name: str) -> str:
    lowered = file_name.lower().strip()
    for extension in SUPPORTED_RESUME_TYPES:
        if lowered.endswith(extension):
            return extension
    raise ValueError("Supported resume files: PDF, DOCX, TXT")


def parse_resume_upload(file_name: str, content_text: str = "", content_base64: str = "") -> dict[str, str]:
    extension = file_extension(file_name)
    if content_text:
        raw = content_text.encode("utf-8", errors="ignore")
    elif content_base64:
        raw = base64.b64decode(content_base64)
    else:
        raise ValueError("Resume upload requires content_text or content_base64")

    if extension == ".txt":
        text = raw.decode("utf-8", errors="ignore")
    elif extension == ".docx":
        text = _parse_docx(raw)
    else:
        text = _parse_pdf_best_effort(raw)

    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("Unable to parse resume text from uploaded file")
    if extension == ".pdf" and _looks_like_raw_office_or_pdf(text):
        text = "PDF preview available. Text extraction was not available; paste resume text manually for ATS analysis."
    elif _looks_like_raw_office_or_pdf(text):
        raise ValueError("Unable to render readable resume preview from uploaded file")
    return {
        "file_type": extension.removeprefix(".").upper(),
        "resume_text": text,
        "preview_type": "pdf" if extension == ".pdf" else "text",
    }


def _parse_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        if raw.startswith(b"PK"):
            raise ValueError("Unable to parse DOCX document text")
        return raw.decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"\s+", " ", text)


def _parse_pdf_best_effort(raw: bytes) -> str:
    # This is intentionally simple and transparent; users can paste text manually if needed.
    text = raw.decode("latin-1", errors="ignore")
    chunks = re.findall(r"\(([^()]{2,})\)", text)
    if chunks:
        return "\n".join(chunks)
    return re.sub(r"[^A-Za-z0-9@.,;:/$%#&+()\-_\s]", " ", text)


def _looks_like_raw_office_or_pdf(text: str) -> bool:
    indicators = ["[Content_Types].xml", "word/document.xml", "_rels/.rels", "PK\x03", "%PDF-"]
    return any(indicator in text for indicator in indicators)
