"""Photo originals are linked by filenames and never interpreted as QC templates."""
import importlib
from io import BytesIO

import pytest
from PIL import Image

from test_molding_sample_api import login_as, make_client
from test_carton_mark_assets import seed_order, upload


def photo_bytes(fmt="PNG", color="white"):
    output = BytesIO()
    Image.new("RGB", (16, 12), color).save(output, fmt)
    return output.getvalue()


@pytest.mark.parametrize("extension,fmt", [("jpg", "JPEG"), ("JPEG", "JPEG"), ("png", "PNG"), ("webp", "WEBP")])
def test_photo_filename_recognition_uses_contract_without_reading_picture(extension, fmt):
    service = importlib.import_module("app.services.carton_mark_assets")
    recognized = service.recognize_asset(f"4500222793_正唛_1.{extension}", photo_bytes(fmt), ["4500222793"])
    assert recognized["kind"] == "image"
    assert recognized["contract_number"] == "4500222793"
    assert recognized["recognition_source"] == "filename"


@pytest.mark.parametrize("filename,contracts,expected", [
    ("手工单_4500222793_侧面.jpg", ["4500222793"], "4500222793"),
    ("IMG_20261006.jpg", ["4500222793"], "IMG_20261006"),
    ("手工单.jpg", ["4500222793"], ""),
    ("手工单_45002227930.jpg", ["4500222793"], ""),
    ("4500222793-1.jpg", ["4500222793"], "4500222793-1"),
    ("手工单_4500222793_4500222794.jpg", ["4500222793", "4500222794"], ""),
])
def test_photo_recognition_keeps_unknown_and_conflicting_names_optional(filename, contracts, expected):
    service = importlib.import_module("app.services.carton_mark_assets")
    result = service.recognize_asset(filename, photo_bytes("JPEG"), contracts)
    assert result["contract_number"] == expected
    if len(result["candidates"]) > 1:
        assert "多个合同号" in result["warning"]


def test_rejects_mislabeled_corrupted_animated_and_excessive_photos(monkeypatch):
    service = importlib.import_module("app.services.carton_mark_assets")
    error = importlib.import_module("app.services.carton_mark").CartonMarkDocumentError
    for filename, content in [("photo.jpg", photo_bytes()), ("photo.png", b"<svg/>"),
                              ("photo.png", photo_bytes()[:-16]), ("photo.svg", b"<svg/>")]:
        with pytest.raises(error):
            service.recognize_asset(filename, content, [])
    buffer = BytesIO()
    Image.new("RGB", (16, 12), "red").save(buffer, "WEBP", save_all=True,
        append_images=[Image.new("RGB", (16, 12), "blue")], duration=100)
    with pytest.raises(error, match="静态"):
        service.recognize_asset("photo.webp", buffer.getvalue(), [])
    monkeypatch.setattr(service, "MAX_ASSET_IMAGE_PIXELS", 100)
    with pytest.raises(error, match="像素"):
        service.recognize_asset("photo.png", photo_bytes(), [])


def test_batch_photos_preserve_originals_dedup_preview_and_optional_order_binding(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        db_module = importlib.import_module("app.db")
        carton = importlib.import_module("app.models.carton_procurement")
        with db_module.SessionLocal() as db:
            seed_order(db, carton, "photo-order-a")
            seed_order(db, carton, "photo-order-b", item="100370")
            seed_order(db, carton, "photo-foreign", factory="huakang-a")
        jpg, png, webp = photo_bytes("JPEG"), photo_bytes("PNG"), photo_bytes("WEBP")
        result = upload(client, [("4500222793_正唛.jpg", jpg), ("4500222793_侧唛.png", png),
                                ("手工单.webp", webp), ("4500222793_坏图.jpg", b"bad-image")])
        assert [row["status"] for row in result] == ["created", "created", "created", "failed"]
        for row in result[:2]:
            assert row["asset"]["binding_status"] == "BOUND"
            assert {order["id"] for order in row["asset"]["orders"]} == {"photo-order-a", "photo-order-b"}
        assert result[2]["asset"]["binding_status"] == "UNBOUND"
        image = result[0]["asset"]
        url = f"/api/carton-mark/assets/{image['id']}/document"
        original = client.get(url, params={"factory_id": "huaxing", "preview": True})
        assert original.content == jpg
        assert original.headers["content-type"] == "image/jpeg"
        assert original.headers["content-disposition"].startswith("inline;")
        assert original.headers["cache-control"] == "private, no-store"
        assert original.headers["x-content-type-options"] == "nosniff"
        assert client.get(url, params={"factory_id": "huaxing"}).headers["content-disposition"].startswith("attachment;")
        assert client.get(url, params={"factory_id": "huakang-a"}).status_code == 404
        repeat = upload(client, [("4500222793_正唛.jpg", jpg)])[0]
        assert repeat["status"] == "duplicate" and repeat["asset"]["id"] == image["id"]
        unbound = result[2]["asset"]
        bound = client.put(f"/api/carton-mark/assets/{unbound['id']}/binding", params={"factory_id": "huaxing"},
                          json={"contract_number": "4500222793", "revision": 1})
        assert bound.status_code == 200 and bound.json()["binding_status"] == "BOUND"
        # A photo must not be accepted as either stored source of the QC check.
        rejected = client.post("/api/carton-mark/templates", data={"factory_id": "huaxing", "customer_name": "ZURU",
            "item": "100369", "contract_number": "4500222793", "excel_asset_id": image["id"], "pdf_asset_id": image["id"]})
        assert rejected.status_code == 422 and "文件类型" in rejected.text
