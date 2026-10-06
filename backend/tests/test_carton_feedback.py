import importlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from uuid import uuid4
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin
from fastapi import HTTPException

from test_molding_sample_api import login_as, make_client


def picture(color="white"):
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-note", "must not survive normalization")
    Image.new("RGB", (80, 60), color).save(output, "PNG", pnginfo=metadata)
    return output.getvalue()


def submit(client, key=None, factory="huaxing", title="数量显示问题", files=None):
    return client.post("/api/carton-feedback", data={"factory_id": factory, "title": title,
        "description": "点击库存后数量不一致\n截图 1 批注：1. 请查看数字", "context_path": "https://bad.example/?token=secret",
        "request_key": key or uuid4().hex}, files=files or [("files", ("screen.png", picture(), "image/png"))])


def test_private_feedback_owner_admin_factory_isolation_and_reply_cas(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        files = [("files", ("first.png", picture(), "image/png")), ("files", ("second.png", picture("black"), "image/png"))]
        # Reverse UUID order makes an accidental ID sort deterministically fail.
        with monkeypatch.context() as patch:
            service = importlib.import_module("app.services.carton_feedback")
            identifiers = iter(["parent", "image-z", "image-a"])
            patch.setattr(service, "uuid4", lambda: SimpleNamespace(hex=next(identifiers)))
            response = submit(client, "stable-request", files=files)
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["status"] == "OPEN" and row["revision"] == 1
        assert row["context_path"] == "/modules/pmc-warehouse/carton-procurement"
        assert submit(client, "stable-request", files=files).json()["id"] == row["id"]
        assert submit(client, "stable-request", title="修改内容").status_code == 409
        url = f"/api/carton-feedback/{row['id']}?factory_id=huaxing"
        image_url = f"/api/carton-feedback/{row['id']}/images/{row['images'][0]}?factory_id=huaxing"
        screenshot = client.get(image_url)
        assert screenshot.status_code == 200 and screenshot.headers["cache-control"] == "private, no-store"
        assert screenshot.headers["x-content-type-options"] == "nosniff"
        with Image.open(BytesIO(screenshot.content)) as image:
            assert image.format == "PNG" and "private-note" not in image.info
            assert image.getpixel((0, 0)) == (255, 255, 255)
        second = client.get(image_url.replace(row['images'][0], row['images'][1]))
        with Image.open(BytesIO(second.content)) as image:
            assert image.getpixel((0, 0)) == (0, 0, 0)
        assert client.get("/api/carton-feedback", params={"factory_id": "huaxing", "all_feedback": True}).status_code == 403
        assert client.post(f"/api/carton-feedback/{row['id']}/reply?factory_id=huaxing",
            json={"revision": 1, "status": "FIXED", "body": "冒充管理员"}).status_code == 403
        login_as(client, "carton_supervisor")
        assert client.get("/api/carton-feedback?factory_id=huaxing").json()["can_manage"] is False
        assert client.get(url).status_code == 404
        assert client.get(image_url).status_code == 404
        assert client.get("/api/carton-feedback?factory_id=huaxing").json()["feedbacks"] == []
        login_as(client, "admin")
        assert client.get(url).status_code == 200 and client.get(image_url).status_code == 200
        assert client.get(f"/api/carton-feedback/{row['id']}?factory_id=huakang-a").status_code == 404
        assert client.get(image_url.replace("huaxing", "huakang-a")).status_code == 404
        reply_url = f"/api/carton-feedback/{row['id']}/reply?factory_id=huaxing"
        assert client.post(reply_url, json={"revision": 1, "status": "FIXED", "body": "  "}).status_code == 422
        assert client.post(reply_url, json={"revision": 1, "status": "UNKNOWN", "body": "说明"}).status_code == 422
        fixed = client.post(reply_url, json={"revision": 1, "status": "FIXED", "body": "已修正数量显示"})
        assert fixed.status_code == 200 and fixed.json()["revision"] == 2
        barrier = Barrier(2)
        def concurrent_reply(status):
            barrier.wait(timeout=10)
            return client.post(reply_url, json={"revision": 2, "status": status, "body": f"再次核对：{status}"})
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(concurrent_reply, ("OPEN", "DECLINED")))
        assert sorted(result.status_code for result in results) == [200, 409]
        login_as(client, "carton_warehouse")
        detail = client.get(url).json()
        assert detail["revision"] == 3 and len(detail["replies"]) == 2
        assert detail["replies"][0]["body"] == "已修正数量显示"
        assert detail["replies"][-1]["status"] == detail["status"]
        assert client.get("/api/carton-feedback?factory_id=huakang-a").status_code == 403
        login_as(client, "engineer")
        assert client.get(url).status_code == 403 and client.get(image_url).status_code == 403
        client.cookies.clear()
        assert client.get(image_url).status_code == 401


def test_only_admin_can_publish_idempotent_factory_scoped_updates(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        payload = {"title": "库存查询更新", "body": "看板库存卡片可以直接进入库存页面。", "request_key": "publish-1"}
        url = "/api/carton-feedback/updates/publish?factory_id=huaxing"
        assert client.post(url, json=payload).status_code == 403
        login_as(client, "admin")
        first = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        assert client.post(url, json=payload).json() == first.json()
        assert client.post(url, json={**payload, "body": "不同内容"}).status_code == 409
        assert client.post(url, json={**payload, "title": "  "}).status_code == 422
        login_as(client, "carton_warehouse")
        workspace = client.get("/api/carton-feedback?factory_id=huaxing").json()
        assert len(workspace["updates"]) == 1 and workspace["updates"][0]["body"] == payload["body"]
        assert "request_key" not in workspace["updates"][0]
        login_as(client, "admin")
        assert client.get("/api/carton-feedback?factory_id=huakang-a").json()["updates"] == []


def test_malformed_screenshot_limits_and_missing_factory_do_not_create_feedback(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "carton_warehouse")
        assert submit(client, files=[("files", ("bad.png", b"not an image", "image/png"))]).status_code == 422
        assert submit(client, files=[("files", ("large.png", b"x" * (5 * 1024 * 1024 + 1), "image/png"))]).status_code == 413
        assert submit(client, files=[("files", ("a.png", picture(), "image/png"))] * 4).status_code == 422
        assert client.post("/api/carton-feedback", data={"title": "缺厂区"}).status_code == 422
        assert client.get("/api/carton-feedback?factory_id=huaxing").json()["feedbacks"] == []
        # Text-only feedback is allowed.
        result = client.post("/api/carton-feedback", data={"factory_id": "huaxing", "title": "只写文字",
            "description": "说明问题", "context_path": "/modules/pmc-warehouse/carton-procurement", "request_key": "text-only"})
        assert result.status_code == 200 and result.json()["images"] == []


def test_image_normalization_rejects_unsupported_and_excessive_pixels():
    service = importlib.import_module("app.services.carton_feedback")
    output = BytesIO()
    Image.new("RGB", (10, 10)).save(output, "GIF")
    with pytest.raises(HTTPException) as error:
        service.normalize_image(output.getvalue())
    assert error.value.status_code == 422

    output = BytesIO()
    Image.new("1", (4001, 4000)).save(output, "PNG")
    with pytest.raises(HTTPException) as error:
        service.normalize_image(output.getvalue())
    assert error.value.status_code == 422


def test_supplier_feedback_uses_canonical_service_scope_private_images_and_targeted_updates(monkeypatch):
    from test_carton_supplier_portal import setup_portal, supplier_login, revoke_supplier_permission
    with make_client(monkeypatch) as client:
        setup_portal(client)
        params = {"factory_id": "huaxing", "portal": "supplier"}
        assert client.get("/api/carton-feedback", params=params).status_code == 200
        assert client.get("/api/carton-feedback?factory_id=huaxing").status_code == 403
        assert client.get("/api/carton-feedback", params={**params, "factory_id": "huakang-a"}).status_code == 403
        response = client.post("/api/carton-feedback", data={**params, "title": "供应商问题", "description": "接单显示异常",
            "context_path": "/modules/pmc-warehouse/carton-procurement", "request_key": "supplier-feedback"},
            files=[("files", ("screen.png", picture(), "image/png"))])
        assert response.status_code == 200, response.text
        row = response.json()
        assert row["context_path"] == "/carton-supplier"
        detail_url = f"/api/carton-feedback/{row['id']}"
        image_url = detail_url + f"/images/{row['images'][0]}"
        assert client.get(image_url, params=params).status_code == 200
        assert client.get("/api/carton-feedback", params={**params, "all_feedback": True}).status_code == 403
        assert client.post(detail_url + "/reply", params=params, json={"revision": 1, "status": "FIXED", "body": "越权"}).status_code == 403
        publication = {"title": "新入口", "body": "右上角查看反馈与变更", "request_key": "supplier-update", "audience": "SUPPLIER"}
        assert client.post("/api/carton-feedback/updates/publish", params=params, json=publication).status_code == 403
        login_as(client, "admin")
        assert row["id"] in {r["id"] for r in client.get("/api/carton-feedback", params={"factory_id": "huaxing", "all_feedback": True}).json()["feedbacks"]}
        assert client.post(detail_url + "/reply?factory_id=huaxing", json={"revision": 1, "status": "FIXED", "body": "已修正接单显示"}).status_code == 200
        private = submit(client, title="内部问题").json()
        url = "/api/carton-feedback/updates/publish?factory_id=huaxing"
        external = client.post(url, json=publication)
        assert external.status_code == 200, external.text
        assert client.post(url, json=publication).json() == external.json()
        assert client.post(url, json={**publication, "audience": "INTERNAL"}).status_code == 409
        assert client.post(url, json={**publication, "audience": "INTERNAL", "title": "内部敏感说明", "request_key": "internal-update"}).status_code == 200
        # Even an administrator using the supplier portal cannot enumerate other authors.
        assert client.get(detail_url, params=params).status_code == 404
        assert client.get(image_url, params=params).status_code == 404
        supplier_login(client)
        workspace = client.get("/api/carton-feedback", params=params).json()
        assert workspace["can_manage"] is False
        assert {r["id"] for r in workspace["feedbacks"]} == {row["id"]}
        assert len(workspace["updates"]) == 1 and workspace["updates"][0]["audience"] == "SUPPLIER"
        assert client.get(detail_url, params=params).json()["replies"][0]["body"] == "已修正接单显示"
        assert client.get(f"/api/carton-feedback/{private['id']}", params=params).status_code == 404
        assert client.get(f"/api/carton-feedback/{private['id']}/images/{private['images'][0]}", params=params).status_code == 404
        revoke_supplier_permission()
        assert client.get(detail_url, params=params).status_code == 403
        assert client.get(image_url, params=params).status_code == 403
