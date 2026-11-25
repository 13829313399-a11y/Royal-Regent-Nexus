import importlib.util
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_qc_mobile", ROOT / "deploy/check_qc_mobile.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


@pytest.mark.parametrize("broken", [None, "redirect", "wrong-asset", "cached", "csrf-proxy", "unready"])
def test_release_probe_traverses_real_paths_without_credentials(broken):
    origin = "https://qc.company.example"
    seen = []

    class Response(BytesIO):
        code = 200

    class Proxy:
        def open(self, req, timeout):
            assert timeout == 5
            assert req.full_url.startswith(origin + CHECK.PREFIX + "/")
            assert not req.get_header("Cookie") and not req.get_header("Authorization")
            path = req.full_url.split(CHECK.PREFIX + "/", 1)[1]
            seen.append(path)
            status = 200
            mime = "application/json"
            cache = "no-store"
            if path == "health":
                content = json.dumps({"service": "qc-mobile", "ready": broken != "unready"})
            elif path in CHECK.ASSETS:
                types, content = CHECK.ASSETS[path]
                mime = sorted(types)[0]
                if path == "app/remote.js":
                    if broken == "redirect":
                        raise HTTPError(req.full_url, 302, "Moved", Message(), BytesIO())
                    if broken == "wrong-asset":
                        content = "<html>Desktop index.html</html>"
                    if broken == "cached":
                        cache = "public, max-age=3600"
            elif path == "context":
                status, content = 401, json.dumps({"detail": "请从验货台重新扫码"})
            else:
                assert path == "exchange"
                assert req.get_method() == "POST" and req.get_header("Origin") == origin
                assert json.loads(req.data) == {"ticket": ""}
                status, content = (403 if broken == "csrf-proxy" else 422), json.dumps({"detail": "二维码无效，请重新生成"})
            if path != "exchange":
                assert req.get_method() == "GET"
            response = Response(content.encode())
            response.code = status
            response.headers = Message()
            response.headers["Content-Type"] = mime
            response.headers["Cache-Control"] = cache
            return response

    if broken is None:
        assert list(CHECK.verify(origin, opener=Proxy())) == ["health", *CHECK.ASSETS, "context", "exchange"]
    else:
        with pytest.raises(ValueError):
            CHECK.verify(origin, opener=Proxy())
        if broken in {"redirect", "wrong-asset", "cached", "unready"}:
            assert "exchange" not in seen


def test_release_uses_existing_api_proxy_and_packages_mobile_assets():
    config = (ROOT / "nginx.prod.conf").read_text()
    start = config.index("location /api/ {")
    api = config[start:config.index("\n  }", start)]
    assert "proxy_pass $api_upstream$request_uri;" in api
    assert "proxy_set_header Host $host;" in api
    docker = (ROOT / "Dockerfile.backend").read_text()
    assert "COPY services/qc-department/ /app/services/qc-department/" in docker
    assert "QC_MOBILE_PUBLIC_ORIGIN=" in (ROOT / ".env.production.example").read_text()
