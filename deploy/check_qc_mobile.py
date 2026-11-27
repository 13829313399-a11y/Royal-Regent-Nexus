"""Check the actual HTTPS route used by a phone, without credentials or a live QR."""
import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


PREFIX = "/api/qc-mobile"
ASSETS = {
    "app/": ({"text/html"}, 'id="task-list"'),
    "app/app.css": ({"text/css"}, ".mobile-task"),
    "app/app.js": ({"text/javascript", "application/javascript"}, "function renderMobileTask"),
    "app/remote.js": ({"text/javascript", "application/javascript"}, "window.QcMobileRemote"),
    "app/qc-photo-shapes.js": ({"text/javascript", "application/javascript"}, "QcPhotoShapes"),
    "app/qc-glass-guide.js": ({"text/javascript", "application/javascript"}, "QcGlassGuide"),
    "app/qc-glass-guide.css": ({"text/css"}, ".qc-glass-guide"),
    "app/icon.svg": ({"image/svg+xml"}, "<svg"),
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def final_origin(value):
    origin = value.strip().rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.path or any(sign in origin for sign in "?#")
            or parsed.username is not None or parsed.port not in (None, 443)):
        raise ValueError("provide the final HTTPS origin, without credentials or path")
    return f"https://{parsed.hostname}"


def verify(origin, opener=None):
    origin = final_origin(origin)
    opener = opener or build_opener(ProxyHandler({}), NoRedirect())
    results = {}

    def request(path, status, types, data=None):
        url = origin + PREFIX + "/" + path
        headers = {"Cache-Control": "no-cache"}
        if data is not None:
            headers.update({"Origin": origin, "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"})
        req = Request(url, headers=headers, data=json.dumps(data).encode() if data is not None else None)
        try:
            result = opener.open(req, timeout=5)
        except HTTPError as exc:
            result = exc
        except (OSError, URLError) as exc:
            raise ValueError(f"{path}: HTTPS connection failed ({exc})") from exc
        with result:
            if result.code != status:
                raise ValueError(f"{path}: expected HTTP {status}, got {result.code}")
            if result.headers.get_content_type() not in types:
                raise ValueError(f"{path}: unexpected Content-Type")
            if status == 200 and not re.search(r"(?:^|,)\s*no-store\b", result.headers.get("Cache-Control", ""), re.I):
                raise ValueError(f"{path}: missing Cache-Control: no-store")
            content = result.read(512 * 1024 + 1)
            if not content or len(content) > 512 * 1024:
                raise ValueError(f"{path}: empty or oversized response")
        results[path] = status
        return content

    if json.loads(request("health", 200, {"application/json"})) != {"service": "qc-mobile", "ready": True}:
        raise ValueError("health: unexpected readiness response")
    for path, (types, marker) in ASSETS.items():
        if marker.encode() not in request(path, 200, types):
            raise ValueError(f"{path}: mobile asset not found in response")
    # The expired/unpaired state must never expose inspection data. An invalid
    # ticket reaches validation only, so we can also check HTTPS Origin handling.
    if json.loads(request("context", 401, {"application/json"})) != {"detail": "请从验货台重新扫码"}:
        raise ValueError("context: unexpected anonymous response")
    if json.loads(request("exchange", 422, {"application/json"}, {"ticket": ""})) != {"detail": "二维码无效，请重新生成"}:
        raise ValueError("exchange: unexpected ticket validation response")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="final HTTPS origin used by employees' phones")
    args = parser.parse_args()
    try:
        results = verify(args.url)
    except (ValueError, OSError, URLError) as exc:
        parser.exit(1, f"QC mobile check failed: {exc}\n")
    print(json.dumps({"service": "qc-mobile", "ready": True, "checks": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
