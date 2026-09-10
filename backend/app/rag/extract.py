"""Conservative document text extraction; no network access."""

from html.parser import HTMLParser


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
    else:
        raise ValueError("Only UTF-8 plain text and HTML documents are supported")
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("Document contains no extractable text")
    return normalized
