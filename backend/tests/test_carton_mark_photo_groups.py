"""Photo grouping never changes source identity or broadens order visibility."""
import importlib

from test_molding_sample_api import login_as, make_client
from test_carton_mark_assets import seed_order, upload
from test_carton_mark_asset_images import photo_bytes
from test_carton_mark_api import _pdf_bytes

BASE = "/api/carton-mark/assets"
SCOPE = {"factory_id": "huaxing"}


def body(assets, contract="", order=None):
    return {"assets": [{"id": a["id"], "revision": a["revision"]} for a in assets],
            "contract_number": contract, "order_id": order}


def photos(client):
    return [row["asset"] for row in upload(client, [
        ("手机照片.png", photo_bytes(color="red")),
        ("微信图片.png", photo_bytes(color="blue")),
        ("未命名.png", photo_bytes(color="green")),
    ])]


def test_unnamed_group_bind_merge_ungroup_and_archive_restore(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            seed_order(db, importlib.import_module("app.models.carton_procurement"), "photo-target")
            seed_order(db, importlib.import_module("app.models.carton_procurement"), "foreign-target", factory="huakang-a")
        options = client.get(BASE + "/binding-orders", params=SCOPE)
        assert options.status_code == 200
        assert [order["id"] for order in options.json()] == ["photo-target"]
        a, b, c = photos(client)
        assert all(photo["binding_status"] == "UNBOUND" for photo in [a, b, c])
        saved = client.post(BASE + "/photo-groups", params=SCOPE, json=body([a, b]))
        assert saved.status_code == 200, saved.text
        grouped = saved.json()
        group_id = grouped[0]["photo_group_id"]
        assert group_id and {photo["photo_group_id"] for photo in grouped} == {group_id}
        assert all(photo["binding_status"] == "UNBOUND" and photo["revision"] == 2 for photo in grouped)
        single = client.put(BASE + f"/{a['id']}/binding", params=SCOPE, json={"contract_number": "4500222793", "revision": 2})
        assert single.status_code == 409
        bound = client.put(BASE + f"/photo-groups/{group_id}/binding", params=SCOPE, json=body(grouped, order="photo-target"))
        assert bound.status_code == 200, bound.text
        grouped = bound.json()
        assert all(photo["bound_order_id"] == "photo-target" and photo["recognition_source"] == "manual_order" for photo in grouped)
        assert all(photo["contract_number"] == "4500222793" for photo in grouped)
        merged = client.post(BASE + "/photo-groups", params=SCOPE, json=body([*grouped, c], "4500222793", "photo-target"))
        assert merged.status_code == 200, merged.text
        grouped = merged.json()
        assert len({photo["photo_group_id"] for photo in grouped}) == 1 and len(grouped) == 3
        group_id = grouped[0]["photo_group_id"]
        # Moving out a single member leaves its original and binding, but never
        # allows a later restore to silently re-enter a re-bound group.
        removed = grouped[0]
        assert client.delete(BASE + f"/{removed['id']}", params={**SCOPE, "revision": removed["revision"]}).status_code == 204
        color = {a["id"]: "red", b["id"]: "blue", c["id"]: "green"}[removed["id"]]
        restored = upload(client, [(removed["file_name"], photo_bytes(color=color))])[0]["asset"]
        assert restored["photo_group_id"] is None and restored["bound_order_id"] == "photo-target"
        remaining = [photo for photo in grouped if photo["id"] != removed["id"]]
        dissolved = client.post(BASE + f"/photo-groups/{group_id}/ungroup", params=SCOPE, json=body(remaining))
        assert dissolved.status_code == 200, dissolved.text
        assert all(photo["photo_group_id"] is None and photo["bound_order_id"] == "photo-target" for photo in dissolved.json())
        assert client.get(BASE + f"/{a['id']}/document", params=SCOPE).content == photo_bytes(color="red")
        with SessionLocal() as db:
            db.delete(db.get(CartonOrder, "photo-target"))
            db.commit()
            seed_order(db, importlib.import_module("app.models.carton_procurement"), "later-order")
        assert all(photo["binding_status"] == "NO_ORDER" and not photo["orders"] for photo in client.get(BASE, params=SCOPE).json())


def test_group_rejects_partial_stale_foreign_mixed_and_duplicate_requests_atomically(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        a, b, c = photos(client)
        pdf = upload(client, [("普通.pdf", _pdf_bytes())])[0]["asset"]
        for payload in [body([a]), body([a, a]), body([a, pdf])]:
            assert client.post(BASE + "/photo-groups", params=SCOPE, json=payload).status_code == 422
        assert client.post(BASE + "/photo-groups", params={"factory_id": "huakang-a"}, json=body([a, b])).status_code == 404
        grouped = client.post(BASE + "/photo-groups", params=SCOPE, json=body([a, b])).json()
        group_id = grouped[0]["photo_group_id"]
        assert client.post(BASE + "/photo-groups", params=SCOPE, json=body([grouped[0], c])).status_code == 409
        assert client.put(BASE + f"/photo-groups/{group_id}/binding", params=SCOPE, json=body([grouped[0]], "CONTRACT-NEW")).status_code == 409
        stale = body(grouped, "CONTRACT-NEW")
        # Force the last row in the sorted CAS sequence to conflict, verifying
        # rollback of earlier successful updates and their audit rows.
        stale["assets"][-1]["revision"] = 1
        assert client.put(BASE + f"/photo-groups/{group_id}/binding", params=SCOPE, json=stale).status_code == 409
        current = {photo["id"]: photo for photo in client.get(BASE, params=SCOPE).json()}
        assert all(current[photo["id"]]["contract_number"] == "" and current[photo["id"]]["revision"] == 2 for photo in grouped)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            assert len(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == "CARTON_MARK_PHOTO_GROUP_SAVED")).all()) == 2
        # A full merge changes the group identity; old binding requests cannot
        # change either the new members or the previous members.
        merged = client.post(BASE + "/photo-groups", params=SCOPE, json=body([*grouped, c])).json()
        assert len(merged) == 3
        assert client.put(BASE + f"/photo-groups/{group_id}/binding", params=SCOPE, json=body(grouped, "CONTRACT-OLD")).status_code == 409


def test_group_binding_checks_target_scope_and_write_permission(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        from app.db import SessionLocal
        from app.services.auth import AuthContext, get_current_user
        with SessionLocal() as db:
            seed_order(db, importlib.import_module("app.models.carton_procurement"), "own-target")
            seed_order(db, importlib.import_module("app.models.carton_procurement"), "other-target", factory="huakang-a")
        assets = photos(client)[:2]
        assert client.post(BASE + "/photo-groups", params=SCOPE, json=body(assets, order="other-target")).status_code == 404
        assert client.post(BASE + "/photo-groups", params=SCOPE, json=body(assets, "WRONG-CONTRACT", "own-target")).status_code == 422
        user = AuthContext(id="read-only", username="read-only", display_name="只读",
            roles=("纸箱仓管",), role_codes=("carton_warehouse_keeper",), permissions=frozenset({"carton_mark:read"}),
            factory_scopes=("huaxing",), department_scopes=("pmc-warehouse",))
        client.app.dependency_overrides[get_current_user] = lambda: user
        assert client.get(BASE + "/binding-orders", params=SCOPE).status_code == 403
        assert client.post(BASE + "/photo-groups", params=SCOPE, json=body(assets)).status_code == 403
