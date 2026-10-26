"""Public reads: deterministic adversarial transport tests, no external network."""
import asyncio
from email.message import Message
import ipaddress
import json
import socket

import pytest

from app.services.assistant import web_fetch_worker as worker, web_pages
from app.services.assistant.errors import AssistantError


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:pass@example.com/", "https://example.com:444/", "http://localhost/", "http://a.local/", "http://a.internal/", "http://[fe80::1%25eth0]/", "https://example.com\\@127.0.0.1/", "https://example.com/\r\nHost:x"])
def test_invalid_targets_are_rejected_before_dns(url):
    with pytest.raises(worker.ReadError):
        worker.target(url)


def address(ip):
    return (socket.AF_INET6 if ipaddress.ip_address(ip).version == 6 else socket.AF_INET,
            socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254", "100.64.0.1", "198.18.1.168", "0.0.0.0", "224.0.0.1", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "2002:7f00:1::1", "64:ff9b::7f00:1"])
def test_dns_any_private_answer_rejects_entire_set(monkeypatch, ip):
    monkeypatch.setattr(worker.socket, "getaddrinfo", lambda *a, **k: [address("93.184.216.34"), address(ip)])
    with pytest.raises(worker.ReadError, match="page_address_forbidden"):
        worker.addresses("public.example", 443)


def test_pinned_numeric_connection_preserves_tls_hostname(monkeypatch):
    seen = []
    class Socket:
        def settimeout(self, value): seen.append(("timeout", value))
        def connect(self, value): seen.append(("connect", value))
        def close(self): seen.append(("close",))
    sock = Socket()
    class TLS:
        def set_alpn_protocols(self, value): seen.append(("alpn", value))
        def wrap_socket(self, value, *, server_hostname):
            assert value is sock
            seen.append(("sni", server_hostname))
            return value
    monkeypatch.setattr(worker.socket, "socket", lambda *a: sock)
    monkeypatch.setattr(worker.socket, "getaddrinfo", lambda *a, **k: pytest.fail("second DNS lookup"))
    monkeypatch.setattr(worker.ssl, "create_default_context", TLS)
    connection = worker.connect("https", "public.example", 443, [address("93.184.216.34")])
    assert ("connect", ("93.184.216.34", 443)) in seen
    assert ("sni", "public.example") in seen and connection.auto_open is False
    assert connection.sock is sock


class Response:
    def __init__(self, status=200, body=b"A real paragraph with more than forty characters for source evidence.", **headers):
        self.status, self.body = status, body
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        for k, v in headers.items():
            del self.headers[k]
            self.headers[k] = v
    def getheader(self, name, default=None): return self.headers.get(name, default)
    def read(self, size): return self.body[:size]


def transport(monkeypatch, responses):
    connections = []
    class Connection:
        def __init__(self, host): self.host, self.closed = host, False
        def request(self, method, path, headers): self.request_args = method, path, headers
        def getresponse(self): return responses.pop(0)
        def close(self): self.closed = True
    def connect(scheme, host, port, resolved):
        c = Connection(host)
        connections.append(c)
        return c
    monkeypatch.setattr(worker, "connect", connect)
    monkeypatch.setattr(worker.socket, "getaddrinfo", lambda host, *a, **k: [address("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34")])
    return connections


def test_redirect_to_private_is_blocked_and_connection_closed(monkeypatch):
    connections = transport(monkeypatch, [Response(302, Location="http://127.0.0.1/latest/meta-data/")])
    with pytest.raises(worker.ReadError, match="page_address_forbidden"):
        worker.read("https://public.example/")
    assert len(connections) == 1 and connections[0].closed


@pytest.mark.parametrize("response,code", [
    (Response(**{"Content-Length": str(worker.MAX_BYTES + 1)}), "page_too_large"),
    (Response(body=b"a" * (worker.MAX_BYTES + 1)), "page_too_large"),
    (Response(**{"Content-Type": "application/pdf"}), "page_type_unsupported"),
    (Response(**{"Content-Encoding": "gzip"}), "page_encoding_unsupported"),
    (Response(401), "page_http_401"),
    (Response(body=b"empty"), "page_content_empty"),
])
def test_response_limits_do_not_return_page_content(monkeypatch, response, code):
    connections = transport(monkeypatch, [response])
    with pytest.raises(worker.ReadError, match=code): worker.read("https://public.example/")
    assert connections[0].closed


def test_success_has_original_and_final_url_hash_time_excerpt_and_no_script(monkeypatch):
    raw = b"<title>Public title</title><script>secret script</script><p>Public text with forty or more readable characters for evidence.</p>"
    connections = transport(monkeypatch, [Response(302, Location="/final"), Response(body=raw, **{"Content-Type": "text/html; charset=utf-8"})])
    result = worker.read("https://public.example/start")
    assert result["url"].endswith("/start") and result["final_url"].endswith("/final")
    assert result["title"] == "Public title" and "secret script" not in result["text"]
    assert len(result["content_hash"]) == 64 and "+00:00" in result["retrieved_at"]
    assert result["redirects"] == 1 and all(c.closed for c in connections)
    headers = connections[-1].request_args[2]
    assert not any(k.lower() in ("cookie", "authorization", "referer") for k in headers)


@pytest.mark.parametrize("cancel", [False, True])
def test_deadline_or_cancellation_kills_child_and_does_not_pass_credentials(monkeypatch, cancel):
    observed = {}
    class Child:
        returncode = None
        async def communicate(self, body):
            observed["request"] = json.loads(body)
            await asyncio.Future()
        def kill(self): self.returncode = -1; observed["killed"] = True
        async def wait(self): observed["waited"] = True
    async def create(*args, **kwargs):
        observed["env"] = kwargs["env"]
        return Child()
    monkeypatch.setenv("ASSISTANT_QWEN_API_KEY", "never-pass-to-public-reader")
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy")
    monkeypatch.setattr(web_pages.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(web_pages, "READ_TIMEOUT_SECONDS", .01)
    async def run():
        task = asyncio.create_task(web_pages.read("https://public.example/"))
        if cancel:
            await asyncio.sleep(0)
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else AssistantError): await task
    asyncio.run(run())
    assert observed["killed"] and observed["waited"]
    assert "ASSISTANT_QWEN_API_KEY" not in observed["env"] and "HTTPS_PROXY" not in observed["env"]


def test_real_child_rejects_localhost_without_network():
    with pytest.raises(AssistantError) as error:
        asyncio.run(web_pages.read("http://localhost/"))
    assert error.value.detail["code"] == "page_address_forbidden"
