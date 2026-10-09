"""Exercise the real production route gate when an Nginx binary is available."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import pytest

from test_maintenance_notice import notice, NOW
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
BINARY = os.environ.get("NGINX_BINARY") or shutil.which("nginx")


@pytest.mark.skipif(not BINARY, reason="Set NGINX_BINARY to exercise real Nginx routes")
def test_api_down_notice_and_all_business_routes_share_the_maintenance_gate(tmp_path):
    hits = []
    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        do_POST = do_GET
        def log_message(self, *args):
            pass
    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    Thread(target=backend.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    site, folder = tmp_path / "site", tmp_path / "notice"
    site.mkdir(); folder.mkdir(); (tmp_path / "logs").mkdir(); (tmp_path / "temp").mkdir()
    (site / "index.html").write_text("BUSINESS PAGE", encoding="utf-8")
    shutil.copyfile(ROOT / "public/maintenance.html", site / "maintenance.html")
    config = (ROOT / "nginx.prod.conf").read_text(encoding="utf-8")
    config = config.replace("listen 80;", f"listen 127.0.0.1:{port};")
    config = config.replace("root /usr/share/nginx/html;", f'root "{site.as_posix()}";')
    config = config.replace("-f /var/run/rrn-notice/active", f'-f "{folder.as_posix()}/active"')
    config = config.replace("alias /var/run/rrn-notice/status.json;", f'alias "{folder.as_posix()}/status.json";')
    config = config.replace("/var/log/nginx/access.log", f'"{(tmp_path / "logs/access.log").as_posix()}"')
    config = config.replace("api:8000", f"127.0.0.1:{backend.server_port}")
    conf = tmp_path / "test.conf"
    conf.write_text(f'daemon off;\nmaster_process off;\npid "{(tmp_path / "test.pid").as_posix()}";\nevents {{}}\nhttp {{\n{config}\n}}', encoding="utf-8")
    args = [str(BINARY), "-p", tmp_path.as_posix() + "/", "-c", conf.as_posix()]
    checked = subprocess.run([*args, "-t"], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    def get(path, method="GET"):
        try:
            response = urlopen(Request(f"http://127.0.0.1:{port}{path}", method=method), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read().decode("utf-8"), response.headers
    try:
        for _ in range(100):
            try:
                code, body, headers = get("/deployment-status.json")
                break
            except OSError:
                time.sleep(.05)
        else:
            pytest.fail("Nginx did not start")
        assert code == 200 and json.loads(body)["phase"] == "idle"
        assert "no-store" in headers["Cache-Control"]
        state = notice.publish(folder, "start", now=NOW)
        assert get("/modules/sales-business")[1] == "BUSINESS PAGE"
        notice.publish(folder, "maintenance", notice_id=state["id"], now=NOW + timedelta(minutes=5))
        before = list(hits)
        for path in ["/modules/sales-business", "/api/foo", "/api/customer-orders/import",
                     "/api/customer-order-ledger/imports/test", "/api/internal-quotes/test", "/api/tools/pdf-rename/preview"]:
            code, body, _ = get(path, "POST" if path.startswith("/api/") else "GET")
            assert code == 503 and "系统正在维护" in body
        assert hits == before  # No business call reaches the API during cutover.
        assert get("/health")[0] == 200
        assert json.loads(get("/deployment-status.json")[1])["phase"] == "maintenance"
        assert get("/maintenance.html")[0] == 200
        backend_port = backend.server_port
        backend.shutdown(); backend.server_close()
        assert get("/health")[0] == 502
        assert json.loads(get("/deployment-status.json")[1])["phase"] == "maintenance"
        assert get("/maintenance.html")[0] == 200
        backend = ThreadingHTTPServer(("127.0.0.1", backend_port), Backend)
        Thread(target=backend.serve_forever, daemon=True).start()
        assert get("/health")[0] == 200
        notice.publish(folder, "complete", notice_id=state["id"], now=NOW + timedelta(minutes=6))
        assert get("/modules/sales-business")[1] == "BUSINESS PAGE"
        assert get("/api/foo")[0] == 200
        assert json.loads(get("/deployment-status.json")[1])["phase"] == "completed"
    finally:
        subprocess.run([*args, "-s", "quit"], capture_output=True, **options)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate()
        backend.shutdown(); backend.server_close()
