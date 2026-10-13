import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
import importlib.util
from io import BytesIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import customer_order_ledger as api
from app.db import get_db
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerVersion as Version, OrderLedgerDispatch as Dispatch, OrderLedgerShipment as Shipment, OrderLedgerSource as Source
from app.schemas.customer_order_ledger import AmendIn, DispatchIn, ReasonIn, RestoreIn, ShipmentIn
from app.services import customer_order_ledger as service
from app.services.auth import AuthContext, AuthGrantContext, get_current_user


def migration():
    path = Path(__file__).parents[1] / "alembic/versions/20260914_0112_customer_order_ledger.py"
    spec = importlib.util.spec_from_file_location("ledger_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        yield db


def preview(factory="huaxing", qty="10000", reference="000123"):
    return dict(factory_id=factory, customer_code="buzzbee", customer_name="BuzzBee", rows=[dict(
        id="preview-row-1", reference_no=reference, product_no="000045", po_no="PO-0001",
        quantity=qty, requested_ship_date="2026-10-01", unit_price_hkd="5.50", amount_hkd="55000",
        packaging="客户指定箱唛", barcode="00000123", lineage={"quantity": "PO 行 7"}, issues=[],
    )])


def ingest(db, payload=None):
    result = service.import_preview(db, preview=payload or preview(), files=[("PO.pdf", b"PO", "formal")],
        source_kind="formal", actor="业务员 (user-1)", reason="已核对订单", controls={})
    db.commit()
    return service.get_line(db, result["items"][0]["factory_id"], result["items"][0]["id"])


def ship_body(line, qty="3000", key="request-0001", document="SHIP-001"):
    return ShipmentIn(expected_revision=line.revision, quantity=qty, ship_date=date(2026, 1, 1),
        document_no=document, idempotency_key=key, note="凭出货单确认")


def test_import_is_persisted_idempotent_and_preserves_extensions(db):
    source = preview()
    before = deepcopy(source)
    line = ingest(db, source)
    assert source == before
    assert line.product_no == "000045" and line.reference_no == "000123"
    assert line.data["barcode"] == "00000123"
    assert line.data["lineage"] == {"quantity": "PO 行 7"}
    assert ingest(db).id == line.id
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1
    with Session(db.bind) as second:
        assert service.get_line(second, "huaxing", line.id).quantity == Decimal("10000")


def test_batch_conflict_rolls_back_all_new_rows_and_files(db):
    ingest(db)
    payload = preview()
    payload["rows"] = [preview(reference="NEW")["rows"][0], preview(qty="3")["rows"][0]]
    with pytest.raises(HTTPException) as error:
        api.transaction(db, lambda: service.import_preview(db, preview=payload,
            files=[("NEW.pdf", b"NEW", "formal")], source_kind="formal", actor="a", reason="", controls={}))
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Source)) == 1


def test_cross_factory_identity_and_access_are_separate(db):
    hx = ingest(db)
    hd = ingest(db, preview("huadeng"))
    assert hx.id != hd.id
    with pytest.raises(HTTPException) as error:
        service.get_line(db, "huadeng", hx.id)
    assert error.value.status_code == 404


def test_dispatch_receives_only_order_facts_and_versions_survive_changes(db):
    imported = preview()
    imported["rows"][0].update(line_q="2026-09-24", customer_q="2026-09-25", date_code="2639")
    line = ingest(db, imported)
    service.dispatch(db, line, DispatchIn(expected_revision=1, recipients=["pmc", "injection", "pmc"]), "a")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Dispatch)) == 2
    old = db.scalar(select(Dispatch).where(Dispatch.recipient == "pmc"))
    assert old.snapshot["quantity"] == "10000"
    assert "unit_price_hkd" not in old.snapshot and "lineage" not in old.snapshot
    service.amend(db, line, AmendIn(expected_revision=line.revision, quantity="9000", requested_ship_date="2026-10-02", note="客户改期", reason="客户邮件修改"), "b")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Dispatch)) == 4
    assert old.snapshot["quantity"] == "10000"
    assert line.version == 2
    assert line.data["amount_hkd"] == ""
    assert "派生数据已清空" in line.data["recheck_notice"]
    assert line.data["line_q"] == line.data["customer_q"] == line.data["date_code"] == ""
    assert "交期已调整" in line.data["recheck_notice"]
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="客户通知取消"), "b")
    db.commit()
    assert db.scalar(select(func.count()).select_from(Dispatch)) == 6
    assert db.scalar(select(Dispatch).where(Dispatch.version == 3)).snapshot["status"] == "cancelled"


def test_partial_shipments_idempotency_completion_reversal_and_totals(db):
    line = ingest(db)
    body = ship_body(line)
    service.ship(db, line, body, "a")
    db.commit()
    service.ship(db, line, body, "a")
    db.commit()
    assert service.line_out(db, line)["remaining_quantity"] == "7000"
    assert db.scalar(select(func.count()).select_from(Shipment)) == 1
    service.ship(db, line, ship_body(line, "7000", "request-0002", "SHIP-002"), "a")
    db.commit()
    assert service.line_out(db, line)["remaining_quantity"] == "0"
    first = db.scalar(select(Shipment).where(Shipment.document_no == "SHIP-001"))
    service.reverse_shipment(db, line, first, ReasonIn(expected_revision=line.revision, reason="数量登记错误"), "b")
    db.commit()
    assert service.line_out(db, line)["remaining_quantity"] == "3000"
    assert service.detail(db, line)["shipments"][0]["quantity"]
    assert len(service.detail(db, line)["shipments"]) == 2


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1.00001", "100000000000000"])
def test_invalid_quantities_rejected(value):
    with pytest.raises(HTTPException):
        service.number(value)


def test_edu_identity_uses_customer_contract_not_workbook_allocated_reference(db):
    first = preview(reference="EDUHX001")
    first["customer_code"] = "edu"
    first["rows"][0]["contract_no"] = "C001"
    line = ingest(db, first)
    duplicate = deepcopy(first)
    duplicate["rows"][0]["reference_no"] = "EDUHX999"
    assert ingest(db, duplicate).id == line.id
    different = deepcopy(first)
    different["rows"][0]["contract_no"] = "C002"
    different["rows"][0]["po_no"] = "PO002"
    assert ingest(db, different).id != line.id
    assert db.scalar(select(func.count()).select_from(Line)) == 2


def test_formal_po_reconciliation_keeps_id_shipments_old_references_and_notifies(db):
    line = ingest(db)
    service.dispatch(db, line, DispatchIn(expected_revision=1, recipients=["warehouse"]), "a")
    service.ship(db, line, ship_body(line), "a")
    db.commit()
    new = preview(reference="FORMAL-000123", qty="9000")
    new["rows"][0].update(amount_hkd="49500", carton_mark="CUSTOMER MARK", label="EXACT LABEL")
    result = api.transaction(db, lambda: service.import_preview(db, preview=new,
        files=[("formal.pdf", b"formal PO", "formal")], source_kind="formal", actor="b",
        reason="正式订单核对确认", controls={}, reconcile_line=line, expected_revision=line.revision))
    assert result["items"][0]["id"] == line.id
    assert line.version == 2 and line.shipped_quantity == 3000 and line.quantity == 9000
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(Dispatch).where(Dispatch.version == 2)).snapshot["carton_mark"] == "CUSTOMER MARK"
    assert db.scalar(select(Dispatch).where(Dispatch.version == 2)).snapshot["label"] == "EXACT LABEL"
    with pytest.raises(HTTPException):
        api.transaction(db, lambda: ingest(db, preview()))
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert len(service.detail(db, line)["sources"]) == 2


def test_reconciliation_rejects_other_customer_product_and_already_owned_identity(db):
    line = ingest(db)
    another = ingest(db, preview(reference="OTHER"))
    for payload in (preview(reference="OTHER"), preview("huadeng")):
        with pytest.raises(HTTPException):
            api.transaction(db, lambda: service.import_preview(db, preview=payload, files=[], source_kind="formal",
                actor="a", reason="不允许覆盖已有", controls={}, reconcile_line=line, expected_revision=line.revision))
        db.refresh(line)
    assert line.reference_no == "000123" and another.reference_no == "OTHER"


def test_over_shipping_duplicate_document_and_stale_revision_do_not_write(db):
    line = ingest(db)
    service.ship(db, line, ship_body(line), "a")
    db.commit()
    for operation in (
        lambda: service.ship(db, line, ship_body(line, "8000", "request-0002", "SHIP-002"), "a"),
        lambda: service.ship(db, line, ship_body(line, "1000", "request-0003", "SHIP-001"), "a"),
        lambda: service.amend(db, line, AmendIn(expected_revision=1, quantity="9000", requested_ship_date="", note="", reason="过期页面更新"), "a"),
        lambda: service.amend(db, line, AmendIn(expected_revision=line.revision, quantity="2000", requested_ship_date="", note="", reason="小于走货数量"), "a"),
    ):
        with pytest.raises(HTTPException):
            api.transaction(db, operation)
        db.refresh(line)
    assert line.shipped_quantity == 3000
    assert line.quantity == 10000
    assert db.scalar(select(func.count()).select_from(Shipment)) == 1


def test_two_sessions_cannot_overwrite_a_newer_revision(engine):
    with Session(engine, expire_on_commit=False) as first, Session(engine, expire_on_commit=False) as second:
        line = ingest(first)
        stale = service.get_line(second, "huaxing", line.id)
        revision = stale.revision
        service.dispatch(first, line, DispatchIn(expected_revision=1, recipients=["warehouse"]), "a")
        first.commit()
        with pytest.raises(HTTPException) as error:
            service.dispatch(second, stale, DispatchIn(expected_revision=revision, recipients=["injection"]), "b")
        second.rollback()
        assert error.value.status_code == 409


def test_immutable_evidence_and_guarded_downgrade(db):
    ingest(db)
    with pytest.raises(Exception, match="immutable"):
        db.execute(text("UPDATE order_ledger_versions SET reason='overwrite'"))
    db.rollback()
    with db.bind.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="禁止降级"):
                migration().downgrade()


def test_empty_migration_can_downgrade_and_reupgrade(engine):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration().downgrade()
            assert "order_ledger_lines" not in inspect(connection).get_table_names()
            migration().upgrade()


def user(permissions, department="sales-business", factory="huaxing"):
    codes = frozenset("customer_order:" + value for value in permissions)
    return AuthContext(id="test-user", username="test", display_name="业务员", roles=("test",), role_codes=("test",),
        permissions=codes, factory_scopes=(factory,), department_scopes=(department,),
        grants=(AuthGrantContext(role_id="test", role_name="test", factory_id=factory, department=department, permissions=codes),))


@pytest.fixture
def client(db, monkeypatch):
    from app.services import business_authz
    monkeypatch.setattr(business_authz.settings, "authz_mode", "enforce")
    # Auth audit's unrelated tables need not be present in this isolated domain database.
    monkeypatch.setattr(business_authz, "add_auth_audit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user(["read", "write", "dispatch", "shipment_confirm"])
    with TestClient(app) as client:
        client.test_app = app
        yield client


def cancelled_order(db, payload=None):
    line = ingest(db, payload)
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="用户误点取消"), "业务员")
    db.commit()
    return line


def restore_url(line, factory=None):
    return f"/api/customer-order-ledger/lines/{line.id}/restore?factory_id={factory or line.factory_id}"


def restore_body(line, **changes):
    return dict(expected_revision=line.revision, reason="用户确认误取消恢复", confirmed=True, **changes)


def test_restore_screenshot_order_preserves_identity_sources_and_cancelled_version(client, db):
    payload = preview(factory="huakang-a", qty="5000", reference="7848-5")
    payload.update(customer_code="greentoys", customer_name="Green Toys")
    payload["rows"][0].update(product_no="HELB-1060", requested_ship_date="2026-11-10")
    line = cancelled_order(db, payload)
    original_data = deepcopy(line.data)
    source_ids = service.detail(db, line)["sources"]
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write"], factory="huakang-a")
    response = client.post(restore_url(line), json=restore_body(line))
    assert response.status_code == 200, response.text
    item = response.json()
    assert (item["id"], item["reference_no"], item["product_no"]) == (line.id, "7848-5", "HELB-1060")
    assert (item["status"], item["version"], item["revision"]) == ("active", 3, 3)
    assert (item["quantity"], item["shipped_quantity"], item["remaining_quantity"]) == ("5000", "0", "5000")
    assert item["dispatch_status"] == "unsent"
    assert item["data"] == original_data
    detail = service.detail(db, line)
    assert detail["sources"] == source_ids
    assert [v["data"]["status"] for v in detail["versions"]] == ["active", "cancelled", "active"]
    assert detail["versions"][0]["reason"].startswith("恢复已取消订单：")
    assert detail["versions"][0]["actor"]
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Dispatch)) == 0
    duplicate = client.post(restore_url(line), json=restore_body(line))
    assert duplicate.status_code == 409
    assert service.get_line(db, line.factory_id, line.id).revision == 3
    assert db.scalar(select(func.count()).select_from(Version)) == 3


def test_restore_retains_current_shipping_and_reversal_not_old_snapshot(client, db):
    line = ingest(db)
    service.ship(db, line, ship_body(line), "仓库")
    db.commit()
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="误取消订单"), "业务员")
    db.commit()
    shipment = db.scalar(select(Shipment).where(Shipment.line_id == line.id))
    response = client.post(restore_url(line), json=restore_body(line))
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == "7000"
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="再次误取消"), "业务员")
    db.commit()
    service.reverse_shipment(db, line, shipment, ReasonIn(expected_revision=line.revision, reason="原走货录错了"), "仓库")
    db.commit()
    response = client.post(restore_url(line), json=restore_body(line))
    assert response.status_code == 200
    assert response.json()["shipped_quantity"] == "0"
    assert response.json()["remaining_quantity"] == "10000"
    assert service.detail(db, line)["shipments"][0]["reversed"] is True


@pytest.mark.parametrize("qty,shipped,remaining", [("100", "100", "0"), ("", "0", ""), ("0.3", "0.1", "0.2")])
def test_restore_full_unknown_and_decimal_quantities(client, db, qty, shipped, remaining):
    line = ingest(db, preview(qty=qty))
    if shipped != "0":
        service.ship(db, line, ship_body(line, qty=shipped), "仓库")
        db.commit()
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="误取消订单"), "业务员")
    db.commit()
    response = client.post(restore_url(line), json=restore_body(line))
    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == remaining
    assert response.json()["shipped_quantity"] == shipped


@pytest.mark.parametrize("changes,code", [
    ({"confirmed": False}, 400), ({"confirmed": "true"}, 422),
    ({"reason": "   "}, 422), ({"reason": "短"}, 422), ({"reason": "a" * 501}, 422),
    ({"expected_revision": 1}, 409),
])
def test_restore_invalid_or_stale_request_rolls_back(client, db, changes, code):
    line = cancelled_order(db)
    body = restore_body(line)
    body.update(changes)
    response = client.post(restore_url(line), json=body)
    assert response.status_code == code
    db.refresh(line)
    assert (line.status, line.version, line.revision) == ("cancelled", 2, 2)
    assert db.scalar(select(func.count()).select_from(Version)) == 2


def test_restore_factory_read_only_and_sent_order_permission_guards(client, db):
    line = cancelled_order(db)
    body = restore_body(line)
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read"])
    assert client.post(restore_url(line), json=body).status_code == 403
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write"], factory="huadeng")
    assert client.post(restore_url(line, "huadeng"), json=body).status_code == 404
    assert client.post(restore_url(line, "huaxing"), json=body).status_code == 403
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write"])
    assert client.post(restore_url(line), json=body).status_code == 200
    service.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=["pmc", "warehouse"]), "业务员")
    db.commit()
    service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason="误取消订单"), "业务员")
    db.commit()
    before = deepcopy(service.detail(db, line)["dispatches"])
    assert client.post(restore_url(line), json=restore_body(line)).status_code == 400
    assert client.post(restore_url(line), json=restore_body(line, notify_recipients=True)).status_code == 403
    db.refresh(line)
    assert line.status == "cancelled"
    assert service.detail(db, line)["dispatches"] == before
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write", "dispatch"])
    restored = client.post(restore_url(line), json=restore_body(line, notify_recipients=True))
    assert restored.status_code == 200
    after = service.detail(db, line)["dispatches"]
    snapshots = [row for row in after if row["version"] == line.version]
    assert {row["recipient"] for row in snapshots} == {"pmc", "warehouse"}
    assert all(row["snapshot"]["status"] == "active" and row["snapshot"]["remaining_quantity"] == "10000" for row in snapshots)
    assert all("unit_price_hkd" not in row["snapshot"] for row in snapshots)
    assert all(row["received_at"] == "" for row in snapshots)
    assert all(row in after for row in before)


def test_restore_dispatch_failure_rolls_back_version_and_status(client, db, monkeypatch):
    line = cancelled_order(db)
    def fail(*args, **kwargs):
        raise HTTPException(503, "模拟发送失败")
    monkeypatch.setattr(service, "publish", fail)
    response = client.post(restore_url(line), json=restore_body(line))
    assert response.status_code == 503
    db.refresh(line)
    assert (line.status, line.version, line.revision) == ("cancelled", 2, 2)
    assert db.scalar(select(func.count()).select_from(Version)) == 2


def test_restore_rechecks_recipients_after_lock_without_partial_commit(client, db, monkeypatch):
    line = cancelled_order(db)
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write"])
    original = service.lock_line
    def locked_with_dispatch(db, line, expected):
        original(db, line, expected)
        service.publish(db, line, ["pmc"], "既有发送")
        db.flush()
    monkeypatch.setattr(service, "lock_line", locked_with_dispatch)
    response = client.post(restore_url(line), json=restore_body(line, notify_recipients=True))
    assert response.status_code == 403
    db.refresh(line)
    assert (line.status, line.version, line.revision) == ("cancelled", 2, 2)
    assert db.scalar(select(func.count()).select_from(Version)) == 2


def test_cancel_rechecks_dispatch_authority_after_lock(client, db, monkeypatch):
    line = ingest(db)
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read", "write"])
    original = service.lock_line
    def locked_with_dispatch(db, line, expected):
        original(db, line, expected)
        service.publish(db, line, ["pmc"], "并发发送人员")
        db.flush()
    monkeypatch.setattr(service, "lock_line", locked_with_dispatch)
    response = client.post(f"/api/customer-order-ledger/lines/{line.id}/cancel?factory_id=huaxing",
        json={"expected_revision": line.revision, "reason": "误取消订单"})
    assert response.status_code == 403
    db.refresh(line)
    assert (line.status, line.revision) == ("active", 1)


def test_api_permission_and_factory_isolation(client, db):
    line = ingest(db)
    assert client.get("/api/customer-order-ledger/lines", params={"factory_id": "huaxing"}).json()["total"] == 1
    assert client.get("/api/customer-order-ledger/lines", params={"factory_id": "huadeng"}).status_code == 403
    assert client.get("/api/customer-order-ledger/lines", params={"factory_id": "group"}).status_code == 400
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["read"])
    assert client.post(f"/api/customer-order-ledger/lines/{line.id}/dispatch?factory_id=huaxing", json={"expected_revision": 1, "recipients": ["pmc"]}).status_code == 403
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["inbox_read", "inbox_receive"], "pmc-warehouse")
    assert client.get("/api/customer-order-ledger/inbox?factory_id=huaxing&recipient=injection").status_code == 403
    assert client.get(f"/api/customer-order-ledger/lines/{line.id}?factory_id=huaxing").status_code == 403


def test_api_inbox_receipt_and_server_latest_version(client, db):
    line = ingest(db)
    service.dispatch(db, line, DispatchIn(expected_revision=1, recipients=["pmc"]), "a")
    db.commit()
    service.amend(db, line, AmendIn(expected_revision=2, quantity="9000", requested_ship_date="2026-10-02", note="", reason="客户通知改期"), "a")
    db.commit()
    client.test_app.dependency_overrides[get_current_user] = lambda: user(["inbox_read", "inbox_receive"], "pmc-warehouse")
    result = client.get("/api/customer-order-ledger/inbox?factory_id=huaxing&recipient=pmc&page_size=1").json()
    assert result["items"][0]["latest_version"] == 2
    item_id = result["items"][0]["id"]
    url = f"/api/customer-order-ledger/inbox/{item_id}/receive?factory_id=huaxing&recipient=pmc"
    first = client.post(url)
    assert first.status_code == 200
    assert first.json()["status"] == "received"
    assert client.post(url).json()["received_at"] == first.json()["received_at"]


def test_real_existing_parser_is_reused_and_original_files_unchanged(client, db):
    from test_customer_order_disney_factory import arguments, disney_po
    from app.services.customer_order_unified import create_unified_customer_preview
    args = arguments("huaxing", disney_po())
    original = deepcopy(args)
    parsed = create_unified_customer_preview(**args)
    mapping = api.mapping
    mapping._finalize_preview(parsed, received_date=args["received_date"], current_user=user(["read", "write"]), factory_id="huaxing")
    keys = [i["skip_key"] for r in parsed["rows"] for i in r["issues"] if i.get("can_skip")]
    import json
    form = dict(factory_id="huaxing", received_date=args["received_date"], confirmed="true",
        preview_fingerprint=parsed["preview_fingerprint"], skipped_issue_keys=json.dumps(keys), confirmation_reason="已逐项核对资料")
    files = [("po_files", (name, content, "application/pdf")) for name, content in args["po_files"]]
    files.append(("schedule_file", (args["schedule_file_name"], args["schedule_content"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")))
    response = client.post("/api/customer-order-ledger/imports/disney", data=form, files=files)
    assert response.status_code == 200, response.text
    assert response.json()["created_count"] == 1
    stored = response.json()["items"][0]
    assert stored["quantity"] == parsed["rows"][0]["quantity"]
    assert stored["data"]["product_no"] == parsed["rows"][0]["product_no"]
    assert args == original
    again = client.post("/api/customer-order-ledger/imports/disney", data=form, files=files)
    assert again.status_code == 200, again.text
    assert again.json()["existing_count"] == 1
    form["preview_fingerprint"] = "incorrect"
    assert client.post("/api/customer-order-ledger/imports/disney", data=form, files=files).status_code == 409


def test_api_reconciles_changed_po_against_schedule_containing_old_quantity(client, db):
    from test_customer_order_disney_factory import arguments, disney_po
    from app.services.customer_order_unified import create_unified_customer_preview, export_unified_customer_schedule
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    import json
    args = arguments("huaxing", disney_po())
    raw = create_unified_customer_preview(**args)
    api.mapping._finalize_preview(raw, received_date=args["received_date"], current_user=user(["read", "write"]), factory_id="huaxing")
    keys = {i["skip_key"] for row in raw["rows"] for i in row["issues"] if i.get("can_skip")}
    current_schedule, _, resolved = export_unified_customer_schedule(**args, skipped_issue_keys=keys)
    resolved["customer_name"] = "Disney"
    stored = service.import_preview(db, preview=resolved, files=[], source_kind="supplementary", actor="a", reason="补充订单核对", controls={})
    db.commit()
    line = service.get_line(db, "huaxing", stored["items"][0]["id"])
    reader = PdfReader(BytesIO(args["po_files"][0][1]))
    writer = PdfWriter()
    page = reader.pages[0]
    stream = DecodedStreamObject()
    stream.set_data(page.get_contents().get_data().replace(b"2502 EA", b"3000 EA"))
    page[NameObject("/Contents")] = stream
    writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    changed_args = {**args, "po_files": [("formal.pdf", output.getvalue())], "schedule_content": current_schedule}
    changed = create_unified_customer_preview(**changed_args)
    api.mapping._finalize_preview(changed, received_date=args["received_date"], current_user=user(["read", "write"]), factory_id="huaxing")
    conflict = next(i for row in changed["rows"] for i in row["issues"] if i["code"] == "existing_quantity_conflict")
    assert conflict["can_skip"] is True
    keys = [i["skip_key"] for row in changed["rows"] for i in row["issues"] if i.get("can_skip")]
    response = client.post("/api/customer-order-ledger/imports/disney", data={
        "factory_id": "huaxing", "received_date": args["received_date"], "confirmed": "true",
        "preview_fingerprint": changed["preview_fingerprint"], "skipped_issue_keys": json.dumps(keys),
        "confirmation_reason": "客户确认修改数量", "reconcile_line_id": line.id, "expected_revision": line.revision,
        "reconciliation_reason": "正式 PO 数量已核对", "source_kind": "formal",
    }, files=[("po_files", ("formal.pdf", output.getvalue(), "application/pdf")),
              ("schedule_file", (args["schedule_file_name"], current_schedule, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["reconciled_count"] == 1
    assert result["items"][0]["id"] == line.id
    assert result["items"][0]["quantity"] == "3000"
    assert result["items"][0]["version"] == 2
