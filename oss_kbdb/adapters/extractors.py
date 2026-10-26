from __future__ import annotations

from pathlib import PurePosixPath

from bs4 import BeautifulSoup
from pypdf import PdfReader

from oss_kbdb.domain.models import ExtractedDocument


def extract(content: bytes, key: str, content_type: str | None = None) -> ExtractedDocument:
    suffix = PurePosixPath(key).suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        reader = PdfReader(__import__("io").BytesIO(content))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return ExtractedDocument(text="\n\n".join(pages), pages=pages)
    text = content.decode("utf-8", errors="replace")
    if suffix in {".html", ".htm"} or (content_type or "").startswith("text/html"):
        text = BeautifulSoup(text, "html.parser").get_text("\n")
    return ExtractedDocument(text=text)
