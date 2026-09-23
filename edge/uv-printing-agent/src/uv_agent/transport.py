import json
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("redirect_not_allowed")


class Transport:
    def __init__(self, base_url, token=None, *, allow_loopback_http=False):
        parsed = urlsplit(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("invalid_server_url")
        if parsed.scheme != "https" and not (allow_loopback_http and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("https_required")
        self.base_url, self.token = base_url.rstrip('/'), token
        self.opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

    def request(self, path, data=None):
        if not path.startswith("/api/internal/uv-agent/") or '..' in path:
            raise ValueError("endpoint_not_allowed")
        headers = {"Content-Type":"application/json"}
        if self.token:
            headers["Authorization"] = "Bearer "+self.token
        request = Request(self.base_url+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        with self.opener.open(request, timeout=35) as response:
            payload = response.read(2*1024*1024+1)
            if len(payload)>2*1024*1024:
                raise ValueError("response_too_large")
            return json.loads(payload)
