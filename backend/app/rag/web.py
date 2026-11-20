"""Restricted HTTPS document fetching for the existing RAG ingestion pipeline."""

import ipaddress
import re
import socket
from codecs import lookup
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/xhtml+xml",
    "text/html",
}
_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class WebDocument:
    content: bytes
    mime_type: str


def fetch_web_document(
    url: str,
    trusted_domains: Iterable[str],
    max_bytes: int,
    *,
    client: httpx.Client | None = None,
    resolver: Callable[[str, int], Iterable[str]] | None = None,
) -> WebDocument:
    """Fetch one trusted PDF/HTML document without following untrusted redirects."""
    allowed_hosts = {_normalize_host(domain) for domain in trusted_domains}
    resolve = resolver or _resolve_addresses
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        current_url = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            _validate_url(current_url, allowed_hosts, resolve)
            with http_client.stream(
                "GET",
                current_url,
                headers={"Accept": "application/pdf, text/html, application/xhtml+xml"},
                follow_redirects=False,
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location or redirect_count == _MAX_REDIRECTS:
                        raise ValueError("Document URL has a missing or excessive redirect")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                mime_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                if mime_type not in _SUPPORTED_CONTENT_TYPES:
                    raise ValueError(f"Unsupported document content type: {mime_type or 'missing'}")
                declared_size = response.headers.get("content-length")
                if declared_size:
                    try:
                        declared_size_bytes = int(declared_size)
                    except ValueError as error:
                        raise ValueError("Document has an invalid Content-Length") from error
                    if declared_size_bytes < 0:
                        raise ValueError("Document has an invalid Content-Length")
                    if declared_size_bytes > max_bytes:
                        raise ValueError("Document exceeds the configured download-size limit")
                content = bytearray()
                for block in response.iter_bytes():
                    content.extend(block)
                    if len(content) > max_bytes:
                        raise ValueError("Document exceeds the configured download-size limit")
                payload = bytes(content)
                if mime_type in {"text/html", "application/xhtml+xml"}:
                    payload = _normalize_html_encoding(
                        payload, response.headers.get("content-type", "")
                    )
                _validate_format(payload, mime_type)
                return WebDocument(payload, mime_type)
    except httpx.HTTPError as error:
        raise ValueError("Unable to fetch the trusted document URL") from error
    finally:
        if client is None:
            http_client.close()
    raise ValueError("Document URL could not be fetched")


def _validate_url(
    url: str,
    trusted_domains: set[str],
    resolver: Callable[[str, int], Iterable[str]],
) -> None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("Document URL is invalid") from error
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError("Only credential-free HTTPS URLs on port 443 are allowed")
    host = _normalize_host(hostname)
    if host not in trusted_domains:
        raise ValueError("Document URL host is not in the trusted-domain allowlist")
    try:
        addresses = tuple(resolver(host, 443))
    except OSError as error:
        raise ValueError("Document URL host could not be resolved safely") from error
    if not addresses:
        raise ValueError("Document URL host has no public IP addresses")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as error:
            raise ValueError("Document URL host resolved to an invalid IP address") from error
        if not ip.is_global:
            raise ValueError("Document URL host resolved to a non-public IP address")


def _normalize_host(host: str) -> str:
    try:
        return host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("Trusted document host is invalid") from error


def _resolve_addresses(host: str, port: int) -> Iterator[str]:
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return iter({record[4][0] for record in records})


def _validate_format(content: bytes, mime_type: str) -> None:
    if mime_type == "application/pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("PDF content type does not match the document format")
        return
    try:
        html = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HTML document must use UTF-8 encoding") from error
    if not re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", html):
        raise ValueError("HTML content type does not match the document format")


def _normalize_html_encoding(content: bytes, content_type: str) -> bytes:
    charset_match = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type, re.IGNORECASE)
    if not charset_match:
        header = content[:4096].decode("ascii", errors="ignore")
        charset_match = re.search(
            r"<meta\b[^>]*\bcharset\s*=\s*[\"']?([\w.-]+)",
            header,
            re.IGNORECASE,
        )
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        encoding = lookup(charset)
        return content.decode(encoding.name).encode("utf-8")
    except (LookupError, UnicodeDecodeError) as error:
        label = "UTF-8" if charset.lower() == "utf-8" else charset
        raise ValueError(
            f"HTML document must use a supported, valid {label} encoding"
        ) from error
