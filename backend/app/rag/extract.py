"""Conservative document text extraction; no network access."""

from html.parser import HTMLParser
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def extract_text(content: bytes, mime_type: str) -> str:
    if mime_type == "text/plain":
        text = content.decode("utf-8")
    elif mime_type in {"text/html", "application/xhtml+xml"}:
        parser = _TextParser()
        parser.feed(content.decode("utf-8"))
        text = " ".join(parser.parts)
    elif mime_type == "application/pdf":
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported")
            text = " ".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, OSError) as error:
            raise ValueError("PDF is invalid or could not be read") from error
        if not text.strip():
            raise ValueError("PDF contains no extractable text; it may be empty or scanned")
    else:
        raise ValueError("Only UTF-8 plain text, HTML, and PDF documents are supported")
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Document contains no extractable text")
    return normalized
