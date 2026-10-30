"""Standalone bounded public reader. No app, credentials, cookies or proxy state.

The parent enforces a process deadline, including DNS and TLS. Each hop resolves
once; the socket connects to that exact validated address, retaining TLS SNI.
"""
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin, quote

MAX_BYTES = 1_048_576
MAX_TEXT = 16000
MAX_REDIRECTS = 3


class ReadError(Exception):
    pass


def target(url):
    if not isinstance(url, str) or len(url) > 4096 or any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url:
        raise ReadError("page_url_invalid")
    try:
        value = urlsplit(url)
        host = (value.hostname or "").encode("idna").decode("ascii")
        port = value.port or (443 if value.scheme == "https" else 80)
        if value.scheme not in ("https", "http") or not host or value.username or value.password or port != (443 if value.scheme == "https" else 80):
            raise ValueError()
        if host.lower().rstrip('.').endswith((".localhost", ".local", ".internal")) or host.lower().rstrip('.') == "localhost" or "%" in host:
            raise ReadError("page_address_forbidden")
        authority = f"[{host}]" if ":" in host else host
        path = quote(value.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(value.query, safe="%/?@!$&'()*+,;=:-._~")
        normalized = urlunsplit((value.scheme, authority, path, query, ""))
        return value.scheme, host, port, path + ("?" + query if query else ""), normalized
    except (ValueError, UnicodeError):
        raise ReadError("page_url_invalid") from None


def addresses(host, port):
    try:
        resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ReadError("page_dns_failed") from None
    if not resolved:
        raise ReadError("page_dns_failed")
    for _, _, _, _, address in resolved:
        ip = ipaddress.ip_address(address[0])
        mapped = getattr(ip, "ipv4_mapped", None)
        transitional = ip.version == 6 and (ip.sixtofour or ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48"))
        if not ip.is_global or ip.is_multicast or ip.is_reserved or transitional or (mapped and not mapped.is_global):
            raise ReadError("page_address_forbidden")
    return resolved


def connect(scheme, host, port, resolved):
    family, kind, protocol, _, address = resolved[0]
    sock = socket.socket(family, kind, protocol)
    sock.settimeout(5)
    try:
        sock.connect(address)  # Numeric sockaddr from the checked DNS answer.
        if scheme == "https":
            context = ssl.create_default_context()
            context.set_alpn_protocols(["http/1.1"])
            sock = context.wrap_socket(sock, server_hostname=host)
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.auto_open = False  # Never fall back to hostname DNS/connect.
        connection.sock = sock
        return connection
    except BaseException:
        sock.close()
        raise


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.in_title = False
        self.title = []
        self.text = []
        self.primary = {"main": [], "article": []}
        self.depth = {"main": 0, "article": 0}

    def append(self, value):
        self.text.append(value)
        for tag, depth in self.depth.items():
            if depth:
                self.primary[tag].append(value)

    def handle_starttag(self, tag, attrs):
        if tag in self.depth:
            self.depth[tag] += 1
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.ignored += 1
        if tag == "title":
            self.in_title = True
        if not self.ignored and tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "article", "section"):
            self.append("\n")

    def handle_endtag(self, tag):
        if tag in self.depth:
            self.depth[tag] = max(0, self.depth[tag] - 1)
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.ignored = max(0, self.ignored - 1)
        if tag == "title":
            self.in_title = False
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3"):
            self.append("\n")

    def handle_data(self, text):
        if self.ignored:
            return
        if self.in_title:
            self.title.append(text)
        self.append(text)


def extract(raw, media, charset):
    if charset.lower() not in ("utf-8", "utf8", "gbk", "gb18030", "big5", "iso-8859-1", "windows-1252", "us-ascii"):
        raise ReadError("page_encoding_unsupported")
    try:
        text = raw.decode(charset)
    except (UnicodeError, LookupError):
        raise ReadError("page_encoding_unsupported") from None
    title = ""
    if media in ("text/html", "application/xhtml+xml"):
        parser = PageText()
        parser.feed(text)
        text = "".join(parser.primary["article"] or parser.primary["main"] or parser.text)
        title = " ".join(parser.title)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < 40:
        raise ReadError("page_content_empty")
    return title.strip()[:500], text[:MAX_TEXT], len(text) > MAX_TEXT


def read(url):
    original = url
    visited = set()
    for hop in range(MAX_REDIRECTS + 1):
        scheme, host, port, path, url = target(url)
        if url in visited:
            raise ReadError("page_redirect_loop")
        visited.add(url)
        resolved = addresses(host, port)
        connection = None
        try:
            connection = connect(scheme, host, port, resolved)
            connection.request("GET", path, headers={"User-Agent": "RoyalRegent-Yaoling/3.0 PublicReader", "Accept": "text/html,text/plain,application/xhtml+xml", "Accept-Encoding": "identity", "Connection": "close"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                destination = response.getheader("Location")
                if not destination or hop == MAX_REDIRECTS:
                    raise ReadError("page_redirect_limit")
                url = urljoin(url, destination)
                continue
            if response.status != 200:
                raise ReadError("page_http_" + str(response.status))
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ReadError("page_encoding_unsupported")
            media = response.headers.get_content_type()
            if media not in ("text/html", "application/xhtml+xml", "text/plain"):
                raise ReadError("page_type_unsupported")
            size = response.getheader("Content-Length")
            if size and (not size.isdigit() or int(size) > MAX_BYTES):
                raise ReadError("page_too_large")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ReadError("page_too_large")
            title, text, truncated = extract(raw, media, response.headers.get_content_charset() or "utf-8")
            return dict(url=original, final_url=url, title=title or host, text=text, text_truncated=truncated,
                        content_hash=hashlib.sha256(raw).hexdigest(), retrieved_at=datetime.now(timezone.utc).isoformat(),
                        media_type=media, byte_size=len(raw), redirects=hop)
        except (socket.timeout, TimeoutError):
            raise ReadError("page_timeout") from None
        except (OSError, http.client.HTTPException):
            raise ReadError("page_connection_failed") from None
        finally:
            if connection:
                connection.close()
    raise ReadError("page_redirect_limit")


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.read(8193))
        result = {"ok": True, "page": read(request["url"])}
    except ReadError as error:
        result = {"ok": False, "code": str(error)}
    except Exception:
        result = {"ok": False, "code": "page_read_failed"}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
