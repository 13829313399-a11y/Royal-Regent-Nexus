"""Independent mark evidence journeys: same isolated DB, three real accounts."""
from contextlib import ExitStack
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
import json

import pytest


FACTORY = "huaxing"
SCOPE = {"factory_id": FACTORY}
ASSETS = "/api/carton-mark/assets"
SUP_ASSETS = "/api/carton-supplier/carton-mark/assets"
SPECIAL = "/api/carton-special-requests"
SUP_SPECIAL = "/api/carton-supplier/special-requests"
PROCUREMENT = "/api/carton-procurement"


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def command(row, **changes):
    return dict(factory_id=FACTORY, request_id=uuid4().hex, expected_revision=row["revision"]) | changes


def image(color="white"):
    from PIL import Image
    output = BytesIO()
    Image.new("RGB", (18, 12), color).save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def actors(monkeypatch, tmp_path):
    # No app/helper import happens before these disposable paths are installed.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "guard.db").as_posix())
    for key in ("TEMP", "TMP", "TMPDIR"): monkeypatch.setenv(key, str(tmp_path))
    import test_molding_sample_api as fixture
    monkeypatch.setattr(fixture, "TEST_TMP_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from test_carton_supplier_portal import setup_portal, supplier_login, accept_all
    with fixture.make_client(monkeypatch) as seed:
        original = setup_portal(seed)
        with ExitStack() as stack:
            warehouse, supervisor, supplier = [TestClient(seed.app) for _ in range(3)]
            for client in (warehouse, supervisor, supplier): stack.callback(client.close)
            warehouse_profile = fixture.login_as(warehouse, "warehouse_keeper")
            fixture.login_as(supervisor, "carton_supervisor")
            supplier_login(supplier)
            assert warehouse.cookies is not supervisor.cookies and supplier.cookies is not warehouse.cookies
            accept_all(supplier)
            from app.services import carton_procurement as core
            monkeypatch.setattr(core, "business_now", lambda: datetime(2026, 10, 22, 12))
            monkeypatch.setattr(core, "business_today", lambda: "2026-10-22")
            workshop = ok(supervisor.post(PROCUREMENT + "/master-data", json=dict(factory_id=FACTORY,
                kind="WORKSHOP", code="箱唛独立测试车间", data={}, reason="隔离夹具实际车间")), 201)
            yield SimpleNamespace(warehouse=warehouse, supervisor=supervisor, supplier=supplier,
                order=original, workshop_id=workshop["id"], warehouse_id=warehouse_profile["id"])


def special(actors, identifier, *, external=False, client=None):
    return ok((client or (actors.supplier if external else actors.warehouse)).get(
        (SUP_SPECIAL if external else SPECIAL) + f"/{identifier}", params=SCOPE))


def create_special(actors, kind="SAMPLE", *, accepted=True, priced=False, customer_code="DICKIE", client=None):
    client=client or actors.warehouse
    data = dict(factory_id=FACTORY, request_id=uuid4().hex, expected_revision=0, kind=kind,
        title="箱唛留证不控制采购", requester_name="实际经办人", customer_code=customer_code,
        required_date="2026-10-20", workshop_id=actors.workshop_id if kind == "WORKSHOP_MISC" else "",
        lines=[dict(packaging_type="外箱", paper_quality="A33+B", specification="20*10*8", dimension_unit="cm",
            quantity="100", unit="个")])  # mark_mode omitted deliberately.
    row = ok(client.post(SPECIAL, json=data), 201)
    row = ok(client.post(SPECIAL + f"/{row['id']}/send", json=command(row)))
    if priced:
        row = ok(actors.supplier.post(SUP_SPECIAL + f"/{row['id']}/quote", json=command(row,
            version_id=row["current_version_id"], pricing_kind="CHARGEABLE", promised_date="2026-10-20",
            lines=[dict(line_id=paper["id"], unit_price="2") for paper in row["lines"]])))
        row = ok(actors.supervisor.post(SPECIAL + f"/{row['id']}/approve", json=command(row,
            quote_version_id=row["quote_version_id"])))
    if accepted: accept_special(actors, row)
    return special(actors, row["id"], client=client)


def accept_special(actors, row):
    ok(actors.supplier.post("/api/carton-supplier/changes/respond", json=dict(factory_id=FACTORY,
        source_kind="SPECIAL", source_id=row["current_version_id"], expected_revision=row["revision"],
        action="ACCEPT", promised_date="2026-10-20", request_id=uuid4().hex)))


def target(actors, identifier, *, external=False):
    prefix = "/api/carton-supplier/carton-mark" if external else ASSETS
    rows = ok((actors.supplier if external else actors.warehouse).get(prefix + "/binding-targets", params=SCOPE))
    row = next(value for value in rows if value["order_id"] == identifier)
    return dict(order_kind=row["order_kind"], order_id=identifier, expected_revision=row["revision"], issue_id=row["issue_id"])


def asset(actors, identifier, *, external=False):
    rows = ok((actors.supplier if external else actors.warehouse).get(SUP_ASSETS if external else ASSETS, params=SCOPE))
    return next(row for row in rows if row["id"] == identifier)


def upload(actors, *, external=False, targets=None, request_id=None, color="white", filename="camera.png", expected=200):
    request_id = request_id or uuid4().hex
    if external:
        response = actors.supplier.post(SUP_ASSETS + "/upload", data=dict(factory_id=FACTORY,
            request_id=request_id, targets_json=json.dumps(targets or [])),
            files=[("files", (filename, image(color), "image/png"))])
        return ok(response, 201)[0], request_id
    options = dict(status="PENDING", sharing_mode="SUPPLIER", request_id=request_id)
    if targets is not None: options["targets"] = targets
    response = actors.warehouse.post(ASSETS + "/batch", data=dict(factory_id=FACTORY,
        options_json=json.dumps([options])), files=[("files", (filename, image(color), "image/png"))])
    return ok(response, expected)[0], request_id


def associate(actors, source, targets, *, external=False, request_id=None, client=None, expected=200):
    client = client or (actors.supplier if external else actors.warehouse)
    payload = dict(revision=source["revision"], request_id=request_id or uuid4().hex, targets=targets)
    response = client.put((SUP_ASSETS if external else ASSETS) + f"/{source['id']}/associations", params=SCOPE, json=payload)
    assert response.status_code == expected, response.text
    return response.json(), payload


def procurement_facts():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonPurchaseOrderIssue
    from app.models.carton_supplier_portal import SupplierCommitment, SupplierShipmentLine
    from app.models.carton_special_requests import SpecialRequest, SpecialVersion, SpecialShipmentLine
    from app.models.auth import SystemNotification
    result = {}
    with SessionLocal() as db:
        for model in (CartonOrder, CartonOrderLine, CartonPurchaseOrderIssue, SupplierCommitment,
                      SupplierShipmentLine, SpecialRequest, SpecialVersion, SpecialShipmentLine, SystemNotification):
            table = model.__table__
            result[table.name] = [dict(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
    return result


def ship(actors, row, qty="1", *, expected=200, version_id=None):
    payload = command(row, version_id=version_id or row["current_version_id"], delivery_note_no="MARK-DN-"+uuid4().hex[:12],
        delivery_date="2026-10-20", lines=[dict(line_id=row["lines"][0]["id"], quantity=qty, unit_price="2")])
    response = actors.supplier.post(SUP_SPECIAL + f"/{row['id']}/ship", json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def assert_visible_targets(source, expected):
    assert {(row["order_kind"], row["order_id"]) for row in source["associations"]} == set(expected)
    assert not source["pending_bindings"]


def test_direct_regular_sample_misc_links_replace_clear_without_procurement_or_ready(actors):
    sample = create_special(actors, priced=True)
    misc = create_special(actors, "WORKSHOP_MISC")
    assert not sample["lines"][0]["mark_ready"] and sample["status"] == "READY"
    sample = ship(actors, sample)
    misc = ship(actors, misc)
    source = upload(actors, targets=[])[0]["asset"]
    assert source["workflow"]["status"] == "PENDING"
    wanted = [target(actors, row_id) for row_id in (actors.order["id"], sample["id"], misc["id"])]
    before = procurement_facts()
    linked, _ = associate(actors, source, wanted)
    assert procurement_facts() == before
    expected = {("REGULAR",actors.order["id"]),("SAMPLE",sample["id"]),("MISC",misc["id"])}
    assert_visible_targets(linked, expected)
    assert_visible_targets(asset(actors, source["id"], external=True), expected)
    assert linked["workflow"]["status"] == "PENDING"
    for row in (sample,misc):
        refreshed = special(actors, row["id"])
        assert any(item["id"] == source["id"] and not item.get("line_id") for item in refreshed["mark_assets"])
        assert refreshed["supplier_confirmation"]["status"] == "ACCEPTED"
    replaced, _ = associate(actors, linked, wanted[:2], external=True)
    assert_visible_targets(replaced, {("REGULAR",actors.order["id"]),("SAMPLE",sample["id"])})
    assert procurement_facts() == before
    cleared, _ = associate(actors, replaced, [], external=True)
    assert_visible_targets(cleared, set())
    assert procurement_facts() == before
    linked, _ = associate(actors, cleared, wanted, external=True)
    assert_visible_targets(linked, expected)
    assert procurement_facts() == before
    ship(actors, special(actors,sample["id"]), "2")
    ship(actors, special(actors,misc["id"]), "2")


def test_missing_marks_dispatch_still_enforces_acceptance_quantity_and_original_regular_import(actors):
    row = create_special(actors, accepted=False)
    assert row["lines"][0]["mark_mode"] == "PENDING"
    ship(actors,row,expected=409)
    accept_special(actors,row)
    row=ship(actors,special(actors,row["id"]),"5")
    ship(actors,row,"96",expected=409)
    wrong_version = dict(row, current_version_id="historical-version")
    ship(actors,wrong_version,"1",expected=409)
    from test_carton_supplier_portal import _dongkang_delivery_file
    current=ok(actors.supplier.get("/api/carton-supplier/workspace",params=SCOPE))["orders"][0]
    original=_dongkang_delivery_file(current,source_price="2")
    files={"file":("东康原单.xlsx",original)}
    preview=ok(actors.supplier.post("/api/carton-supplier/shipments/import-preview",files=files))
    assert all(group["ready"] for group in preview["groups"])
    confirmed=ok(actors.supplier.post("/api/carton-supplier/shipments/import-confirm",files=files,data=dict(
        sha256=preview["sha256"],selections=json.dumps([dict(factory_id=FACTORY,delivery_note_no="DK-IMPORT-01")]))))
    assert len(confirmed["shipments"]) == 1
    assert ok(actors.supplier.post("/api/carton-supplier/shipments/import-confirm",files=files,data=dict(
        sha256=preview["sha256"],selections=json.dumps([dict(factory_id=FACTORY,delivery_note_no="DK-IMPORT-01")]))))["shipments"][0]["id"] == confirmed["shipments"][0]["id"]


@pytest.mark.parametrize("external",[False,True])
def test_upload_and_direct_link_retry_are_atomic_and_recoverable(actors,external):
    row=create_special(actors)
    targets=[target(actors,row["id"],external=external)]
    bad=[dict(targets[0],expected_revision=targets[0]["expected_revision"]-1)]
    before=ok(actors.warehouse.get(ASSETS,params=SCOPE))
    failed,rid=upload(actors,external=external,targets=bad)
    assert failed["status"] == "failed" and not failed.get("asset")
    assert ok(actors.warehouse.get(ASSETS,params=SCOPE)) == before
    outcome,rid=upload(actors,external=external,targets=targets,request_id=uuid4().hex)
    assert outcome["status"] == "created"
    source=outcome["asset"]
    assert_visible_targets(source,{("SAMPLE",row["id"])})
    assert source["workflow"]["status"] != "READY"
    repeated,_=upload(actors,external=external,targets=targets,request_id=rid)
    assert repeated["asset"]["id"] == source["id"]
    assert len(ok(actors.warehouse.get(ASSETS,params=SCOPE))) == len(before)+1
    source=asset(actors,source["id"],external=external)
    linked,payload=associate(actors,source,targets,external=external)
    client=actors.supplier if external else actors.warehouse
    prefix=SUP_ASSETS if external else ASSETS
    assert ok(client.put(prefix+f"/{source['id']}/associations",params=SCOPE,json=payload))["id"] == source["id"]
    assert client.put(prefix+f"/{source['id']}/associations",params=SCOPE,json={**payload,"targets":[]}).status_code == 409
    denied,_=associate(actors,linked,[dict(targets[0],issue_id="stale-issued-version")],external=external,expected=409)
    assert asset(actors,source["id"],external=external)["revision"] == linked["revision"]
    cleared,_=associate(actors,linked,[],external=external)
    restored,_=associate(actors,cleared,targets,external=external)
    assert restored["id"] == source["id"]
    assert len(ok(actors.warehouse.get(ASSETS,params=SCOPE))) == len(before)+1


def test_old_mark_routes_only_append_evidence_and_keep_quote_acceptance(actors):
    row=create_special(actors,priced=True)
    source=upload(actors,targets=[])[0]["asset"]
    before=procurement_facts()
    data=command(row,mark_mode="EXISTING",asset_id=source["id"],asset_revision=source["revision"])
    updated=ok(actors.supplier.post(SUP_SPECIAL+f"/{row['id']}/lines/{row['lines'][0]['id']}/mark",json=data))
    assert procurement_facts() == before
    assert not updated["lines"][0]["mark_ready"]
    assert len(updated["attachments"]) == 1
    supplier_attachment=updated["attachments"][0]
    assert supplier_attachment["filename"] == source["file_name"] and supplier_attachment["role"] == "DRAFT"
    assert ok(actors.supplier.post(SUP_SPECIAL+f"/{row['id']}/lines/{row['lines'][0]['id']}/mark",json=data)) == updated
    endpoint=SPECIAL+f"/{row['id']}/lines/{row['lines'][0]['id']}/mark"
    assert actors.warehouse.post(endpoint,json=data | {"request_id":uuid4().hex}).status_code == 409
    source=asset(actors,source["id"])
    data=command(row,mark_mode="EXISTING",asset_id=source["id"],asset_revision=source["revision"])
    updated=ok(actors.warehouse.post(endpoint,json=data))
    assert len(updated["attachments"]) == 2
    assert updated["attachments"][-1]["id"] != supplier_attachment["id"]
    assert ok(actors.warehouse.post(endpoint,json=data)) == updated
    assert procurement_facts() == before
    assert asset(actors,source["id"])["workflow"]["status"] == "PENDING"
    supplier_upload_data=command(row,role="DRAFT")
    supplier_upload_files={"file":("supplier-pending.png",image("green"),"image/png")}
    supplier_upload_endpoint=SUP_SPECIAL+f"/{row['id']}/attachments"
    uploaded=ok(actors.supplier.post(supplier_upload_endpoint,data=supplier_upload_data,files=supplier_upload_files),201)
    supplier_sources=[item for item in uploaded["mark_assets"] if item["file_name"] == "supplier-pending.png"]
    assert len(supplier_sources) == 1 and not supplier_sources[0].get("line_id")
    assert any(item["filename"] == "supplier-pending.png" and item["role"] == "DRAFT" for item in uploaded["attachments"])
    assert ok(actors.supplier.post(supplier_upload_endpoint,data=supplier_upload_data,files=supplier_upload_files),201) == uploaded
    assert procurement_facts() == before
    updated=ok(actors.warehouse.post(SPECIAL+f"/{row['id']}/attachments",data=command(row,role="CONFIRMED"),
        files={"file":("new-pending.png",image("blue"),"image/png")}),201)
    assert procurement_facts() == before
    assert all(item["role"] != "CONFIRMED" for item in updated["attachments"])
    assert any(item["filename"] == "new-pending.png" and item["role"] == "DRAFT" for item in updated["attachments"])
    assert any(item["file_name"] == "new-pending.png" for item in updated["mark_assets"])
    assert updated["status"] == row["status"] and updated["quote_version_id"] == row["quote_version_id"]
    assert updated["promised_date"] == row["promised_date"]
    assert updated["supplier_confirmation"]["status"] == "ACCEPTED"
    assert all(item["workflow"]["status"] != "READY" for item in ok(actors.warehouse.get(ASSETS,params=SCOPE)))
    ship(actors,updated)


def test_special_order_revision_inherits_associations_and_dispatched_files_stay_frozen(actors):
    row=create_special(actors,priced=True)
    wanted=[target(actors,row["id"])]
    original=upload(actors,targets=wanted)[0]["asset"]
    before=procurement_facts()
    sent=ship(actors,row)
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_special_requests import SpecialShipmentLine
    with SessionLocal() as db:
        frozen=[(paper.id,paper.snapshot_json) for paper in db.scalars(select(SpecialShipmentLine))]
    old_manifest=json.loads(frozen[0][1])["file_manifest"]
    entry=next(value for value in old_manifest if value.get("asset_id") == original["id"])
    assert entry["asset_revision"] == original["revision"] and entry["sha256"] == original["sha256"]
    assert entry.get("line_id","") == ""
    options=dict(status="PENDING",previous_asset_id=original["id"],previous_revision=original["revision"],request_id=uuid4().hex)
    revised=ok(actors.warehouse.post(ASSETS+"/batch",data=dict(factory_id=FACTORY,options_json=json.dumps([options])),
        files=[("files",("new-version.png",image("yellow"),"image/png"))]))[0]["asset"]
    assert revised and revised["id"] != original["id"]
    assert_visible_targets(revised,{("SAMPLE",row["id"])})
    assert revised["workflow"]["status"] == "PENDING"
    refreshed=special(actors,row["id"])
    for key in ("current_version_id","quote_version_id","pricing_kind","promised_date","status"):
        assert refreshed[key] == sent[key]
    assert refreshed["supplier_confirmation"]["status"] == "ACCEPTED"
    with SessionLocal() as db:
        assert [(paper.id,paper.snapshot_json) for paper in db.scalars(select(SpecialShipmentLine))] == frozen
    downloaded=actors.supplier.get(SUP_ASSETS+f"/{original['id']}/document",params=SCOPE)
    assert downloaded.status_code == 200 and downloaded.content == image()
    assert len(ok(actors.supplier.get(SUP_ASSETS,params=SCOPE))) == 2
    # The first batch is immutable even if the current reference is replaced/cleared.
    revised,_=associate(actors,revised,[])
    with SessionLocal() as db:
        assert [(paper.id,paper.snapshot_json) for paper in db.scalars(select(SpecialShipmentLine))] == frozen
    dispatched=actors.supplier.get(SUP_SPECIAL+f"/{row['id']}/attachments/{entry['attachment_id']}",params=SCOPE)
    assert dispatched.status_code == 200 and dispatched.content == image()


def test_legacy_pending_binding_requires_no_separate_approval_and_is_not_auto_migrated(actors):
    source=upload(actors,targets=[])[0]["asset"]
    from app.db import SessionLocal
    from app.models.carton_mark import CartonMarkAsset
    from app.models.auth import AuthUser
    from app.services.auth import build_auth_context
    from app.services import carton_mark_assets as library, carton_mark_sharing as sharing
    current_target=target(actors,actors.order["id"])
    with SessionLocal() as db:
        stored=db.get(CartonMarkAsset,source["id"])
        actor=build_auth_context(db,db.get(AuthUser,actors.warehouse_id))
        # Exact retained pre-upgrade request; GETs must neither apply nor erase it.
        library.audit(db,actor,stored,sharing.PROPOSED,dict(id="LEGACY-PENDING",order_id=actors.order["id"],
            order_no=actors.order["order_no"],contract_no=actors.order["contract_no"],item_no=actors.order["item_no"],
            issue_id=current_target["issue_id"],supplier_id=stored.shared_supplier_id if hasattr(stored,"shared_supplier_id") else
                sharing.current(db,stored)["shared_supplier_id"],sha256=stored.sha256,requested_at="2026-10-19T12:00:00"))
        db.commit()
    visible=asset(actors,source["id"],external=True)
    assert len(visible["pending_bindings"]) == 1 and not visible["associations"]
    assert len(asset(actors,source["id"],external=True)["pending_bindings"]) == 1
    before=procurement_facts()
    linked=ok(actors.supplier.put(SUP_ASSETS+f"/{source['id']}/binding",params=SCOPE,
        json=dict(revision=visible["revision"],order_ids=[actors.order["id"]])))
    assert_visible_targets(linked,{("REGULAR",actors.order["id"])})
    assert procurement_facts() == before
    from app.models.carton_procurement import CartonAuditEvent
    from sqlalchemy import select
    with SessionLocal() as db:
        assert any(json.loads(event.detail_json).get("id") == "LEGACY-PENDING" for event in db.scalars(select(
            CartonAuditEvent).where(CartonAuditEvent.event_type == sharing.PROPOSED)))


@pytest.mark.parametrize("old_state",["CANCELLED","DELETED"])
def test_cancelled_or_deleted_previous_customer_cannot_be_used_to_clear_without_permission(actors,old_state):
    source=upload(actors,targets=[target(actors,actors.order["id"])])[0]["asset"]
    from sqlalchemy import select,delete
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonOrder,CartonCustomer
    from app.models.carton_customer_assignment import CartonCustomerAssignment
    from test_molding_sample_api import ensure_test_user
    ensure_test_user("carton_warehouse")
    from app.models.auth import AuthUser
    with SessionLocal() as db:
        old=db.get(CartonOrder,actors.order["id"])
        if old_state == "CANCELLED": old.status="CANCELLED"
        else: old.deleted_at="2026-10-20T12:00:00"
        customer=db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id==FACTORY,CartonCustomer.customer_code=="DICKIE"))
        peer=db.scalar(select(AuthUser).where(AuthUser.username=="carton_warehouse"))
        db.execute(delete(CartonCustomerAssignment).where(CartonCustomerAssignment.customer_id==customer.id))
        db.add(CartonCustomerAssignment(customer_id=customer.id,user_id=peer.id,factory_id=FACTORY))
        db.commit()
    response=actors.warehouse.put(ASSETS+f"/{source['id']}/associations",params=SCOPE,
        json=dict(revision=source["revision"],request_id=uuid4().hex,targets=[]))
    assert response.status_code == 403,response.text
    # A supervisor with direct order_adjust may remove an old relationship.
    cleared,_=associate(actors,source,[],client=actors.supervisor)
    assert_visible_targets(cleared,set())


def test_association_customer_supplier_factory_and_fresh_permission_boundaries(actors,monkeypatch):
    original_target=target(actors,actors.order["id"])
    source=upload(actors,targets=[original_target])[0]["asset"]
    ok(actors.supervisor.post(PROCUREMENT+"/customers",json=dict(factory_id=FACTORY,
        customer_code="OTHERCLIENT",customer_name="其他客户")),201)
    other=create_special(actors,customer_code="OTHERCLIENT",client=actors.supervisor)
    other_target=target(actors,other["id"],external=True)
    before=procurement_facts()
    associate(actors,source,[original_target,other_target],client=actors.supervisor,expected=422)
    associate(actors,source,[original_target,other_target],external=True,expected=422)
    assert asset(actors,source["id"])["revision"] == source["revision"]
    assert procurement_facts() == before
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.carton_procurement import CartonSupplier
    with SessionLocal() as db:
        db.add(CartonSupplier(id="MARK-OTHER",factory_id=FACTORY,supplier_code="MARK-OTHER",
            supplier_name="其他供应商",status="ACTIVE",created_at="2026-10-20",updated_at="2026-10-20"))
        db.commit()
    private=ok(actors.supervisor.post(ASSETS+"/batch",data=dict(factory_id=FACTORY,options_json=json.dumps([
        dict(status="PENDING",sharing_mode="SUPPLIER",supplier_id="MARK-OTHER",targets=[])])),
        files=[("files",("other-supplier.png",image("red"),"image/png"))]))[0]["asset"]
    assert private
    assert actors.supplier.get(SUP_ASSETS+f"/{private['id']}/document",params=SCOPE).status_code == 404
    assert actors.supplier.put(SUP_ASSETS+f"/{private['id']}/associations",params=SCOPE,
        json=dict(revision=private["revision"],request_id=uuid4().hex,targets=[])).status_code == 404
    for client,prefix in ((actors.warehouse,ASSETS),(actors.supplier,SUP_ASSETS)):
        response=client.put(prefix+f"/{source['id']}/associations",params={"factory_id":"huakang-a"},
            json=dict(revision=source["revision"],request_id=uuid4().hex,targets=[]))
        assert response.status_code in {403,404},response.text
    from test_carton_supplier_portal import revoke_supplier_permission
    revoke_supplier_permission("carton_supplier:edit")
    associate(actors,source,[],external=True,expected=403)
    assert asset(actors,source["id"])["revision"] == source["revision"]
    from app.models.auth import AuthUser
    from app.services import carton_procurement as core
    old_lock=core._lock_receipt_factory
    touched=[]
    def disabled_after_lock(db,factory):
        old_lock(db,factory)
        actor=db.get(AuthUser,actors.warehouse_id)
        actor.status="disabled"
        db.flush()
        touched.append(True)
    monkeypatch.setattr(core,"_lock_receipt_factory",disabled_after_lock)
    associate(actors,source,[],expected=403)
    monkeypatch.setattr(core,"_lock_receipt_factory",old_lock)
    assert touched
    assert asset(actors,source["id"])["revision"] == source["revision"]
    assert procurement_facts() == before


def test_extra_pending_or_undeclared_marks_dispatch_but_real_receiving_classification_is_required(actors):
    extra=dict(packaging_type="外箱",paper_quality="A33+B",specification="20*10*8",dimension_unit="cm",
        quantity="10",unit="个",unit_price="0",purpose="车间周转用纸品",free_confirmed=False)
    payload=command({"revision":0},delivery_note_no="EXTRA-MARK-PENDING",delivery_date="2026-10-20",extra_lines=[extra])
    path="/api/carton-supplier/unified-deliveries"
    assert actors.supplier.post(path,json=payload).status_code == 422
    extra["free_confirmed"]=True
    group=ok(actors.supplier.post(path,json=payload),201)
    row=group["special"][0]
    assert row["origin"] == "SUPPLIER_EXTRA" and row["lines"][0]["mark_mode"] == "PENDING"
    assert not row["lines"][0]["mark_ready"]
    shipment=row["shipments"][0]
    locations=ok(actors.warehouse.get(PROCUREMENT+"/inventory/locations",params=SCOPE))
    location=next(value["id"] for value in locations if value["bin_code"]=="A-01")
    receive=dict(factory_id=FACTORY,request_id=uuid4().hex,expected_revision=0,acceptance_date="2026-10-20",
        special=[dict(request_id=row["id"],shipment_id=shipment["id"],expected_revision=row["revision"],
            lines=[dict(shipment_line_id=shipment["lines"][0]["id"],received_quantity="10",
                location_allocations=[dict(location_id=location,quantity="10")])])])
    endpoint="/api/carton-unified-deliveries/"+group["id"]+"/receive"
    assert actors.warehouse.post(endpoint,json=receive).status_code == 422
    receive["special"][0].update(received_kind="WORKSHOP_MISC",requester_name="实际车间经办人")
    assert actors.warehouse.post(endpoint,json=receive).status_code == 422
    receive["special"][0]["workshop_id"]=actors.workshop_id
    accepted=ok(actors.warehouse.post(endpoint,json=receive))
    assert accepted["special"][0]["kind"] == "WORKSHOP_MISC"
