"""Rehearse the employee-network probe through a TLS terminator on loopback only."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from ipaddress import ip_address
import socket
import ssl
from threading import Thread

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_qc_mobile_release_check import CHECK


def test_employee_probe_over_tls_with_and_without_hostname_sni(tmp_path, monkeypatch):
    from app.api import qc_mobile as mobile

    host, ipv4 = "qc.example.test", "1.1.1.1"
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, host)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host), x509.IPAddress(ip_address(ipv4))]), False)
            .sign(key, hashes.SHA256()))
    pem, private = tmp_path / "fixture.pem", tmp_path / "fixture.key"
    pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(pem, private)
    sni = []
    tls.set_servername_callback(lambda sock, name, ctx: sni.append(name))
    monkeypatch.setenv("SSL_CERT_FILE", str(pem))
    monkeypatch.setattr(mobile.settings, "qc_mobile_require_https", True)
    monkeypatch.setattr(mobile.settings, "qc_department_data_dir", str(tmp_path / "companies"))

    async def companies(method, path, params, data):
        assert (method, path, params, data) == ("GET", "api/companies", [], b"")
        return httpx.Response(200, json={"companies": [{"id": v} for v in mobile.COMPANIES.values()]})

    monkeypatch.setattr(mobile, "upstream", companies)
    app = FastAPI()
    app.include_router(mobile.router)
    app.dependency_overrides[mobile.get_db] = lambda: None  # Probe carries no session or valid ticket.
    with TestClient(app) as backend:
        class Proxy(BaseHTTPRequestHandler):
            def forward(self):
                headers = {k: self.headers[k] for k in ("Host", "Origin", "Content-Type", "Sec-Fetch-Site") if k in self.headers}
                resp = backend.request(self.command, self.path, headers=headers,
                                       content=self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self.send_response(resp.status_code)
                for k in ("Content-Type", "Cache-Control"):
                    if k in resp.headers:
                        self.send_header(k, resp.headers[k])
                self.end_headers()
                self.wfile.write(resp.content)

            do_GET = do_POST = forward

        with HTTPServer(("127.0.0.1", 0), Proxy) as proxy:
            proxy.socket = tls.wrap_socket(proxy.socket, server_side=True)
            worker = Thread(target=proxy.serve_forever, daemon=True)
            worker.start()
            lookup = socket.getaddrinfo

            def loopback_only(node, port, *args, **kwargs):
                assert node in {host, ipv4, "mismatch.example.test"} and int(port) == 443
                return lookup("127.0.0.1", proxy.server_port, *args, **kwargs)

            monkeypatch.setattr(socket, "getaddrinfo", loopback_only)
            try:
                for entry, expected_sni in [(host, host), (ipv4, None)]:
                    origin = "https://" + entry
                    monkeypatch.setattr(mobile.settings, "qc_mobile_public_origin", origin)
                    sni.clear()
                    result = CHECK.verify(origin)
                    assert result == {"health": 200, **dict.fromkeys(CHECK.ASSETS, 200), "context": 401, "exchange": 422}
                    assert sni and set(sni) == {expected_sni}
                with pytest.raises(ValueError, match="CERTIFICATE_VERIFY_FAILED"):
                    CHECK.verify("https://mismatch.example.test")
                assert not (tmp_path / "companies").exists()
            finally:
                proxy.shutdown()
                worker.join()
