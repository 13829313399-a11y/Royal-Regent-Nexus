"""360 number mapping changes revise the original ledger line explicitly."""
from copy import deepcopy

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.api import customer_order_ledger as api
from app.models.customer_order_ledger import (
    OrderLedgerLine as Line, OrderLedgerVersion as Version,
    OrderLedgerDispatch as Dispatch, OrderLedgerShipment as Shipment,
    OrderLedgerIdentity as Identity, OrderLedgerSource as Source,
)
from app.schemas.customer_order_ledger import DispatchIn
from app.services import customer_order_ledger as service
from test_customer_order_ledger import db, engine, preview, ship_body


REFERENCE = "RL-765431-17"
RELEASE = "RL765432117"
CUSTOMER_PO = "7654321"
LABEL = "外箱贴 SSCC 条码标签（SSCC Barcode labeled on master carton）"


def payload(*, corrected=False, factory="huakang-a", customer="360"):
    result = preview(factory=factory, reference=REFERENCE)
    result.update(customer_code=customer, customer_name="Example Customer")
    result["rows"][0].update(
        product_no="76540010069", production_no="", contract_no=RELEASE,
        po_no=REFERENCE, label="No stickers", customer_label="",
    )
    if corrected:
        result["rows"][0].update(production_no=RELEASE, contract_no=REFERENCE,
            po_no=CUSTOMER_PO, customer_release_no=RELEASE, customer_label=LABEL)
    return result


def save(db, data, **kwargs):
    return api.transaction(db, lambda: service.import_preview(db, preview=data,
        files=[("360-release.pdf", b"360 corrected source" if data["rows"][0]["po_no"] == CUSTOMER_PO else b"360 old source", "formal")],
        source_kind="formal", actor="sales", reason="核对客户单号和外箱贴纸", controls={}, **kwargs))


def seed(db, **kwargs):
    result = save(db, payload(**kwargs))
    return db.get(Line, result["items"][0]["id"])


@pytest.mark.parametrize("production", ["", REFERENCE, RELEASE])
def test_old_number_mapping_reimport_requires_explicit_revision_without_duplicate(db, production):
    old = payload()
    old["rows"][0]["production_no"] = production
    line = db.get(Line, save(db, old)["items"][0]["id"])
    before = deepcopy(line.data)
    old_key = line.identity_key
    incoming = payload(corrected=True)
    assert service.identity_for(old["rows"][0], "360") == service.identity_for(incoming["rows"][0], "360")
    assert service.resolve_existing_line(db, "huakang-a", "360", incoming["rows"][0]).id == line.id

    with pytest.raises(HTTPException) as error:
        save(db, incoming)

    assert error.value.status_code == 409
    assert "旧 360 单号对应关系" in error.value.detail and "关联原订单" in error.value.detail
    assert line.data == before and line.identity_key == old_key
    assert line.version == line.revision == 1
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1
    assert db.scalar(select(func.count()).select_from(Source)) == 1


def test_explicit_reconciliation_keeps_id_shipments_history_and_sent_snapshots(db):
    old = payload()
    old["rows"][0].update(history_migration={"cutoff_date": "2025-12-31", "opening_shipped_quantity": "0"},
        history_fields={"原合同列": RELEASE}, history_review={"source_sheet": "正单评审表"})
    line = db.get(Line, save(db, old)["items"][0]["id"])
    service.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=["warehouse", "pmc"]), "sales")
    service.ship(db, line, ship_body(line), "warehouse")
    db.commit()
    before = deepcopy(line.data)
    original_version = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 1))
    original_version_data = deepcopy(original_version.data)
    old_dispatches = list(db.scalars(select(Dispatch).where(Dispatch.line_id == line.id)))
    old_snapshots = {item.id: deepcopy(item.snapshot) for item in old_dispatches}
    old_key, old_revision = line.identity_key, line.revision

    result = save(db, payload(corrected=True), reconcile_line=line, expected_revision=line.revision)

    assert result["created_count"] == 0 and result["reconciled_count"] == 1
    assert result["items"][0]["id"] == line.id
    assert line.identity_key == old_key and line.reference_no == REFERENCE
    assert line.version == 2 and line.revision == old_revision + 1
    assert line.quantity == 10000 and line.shipped_quantity == 3000
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Shipment)) == 1
    assert db.scalar(select(func.count()).select_from(Identity)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 2
    assert original_version.data == original_version_data
    assert original_version_data["contract_no"] == RELEASE
    assert original_version_data["po_no"] == REFERENCE
    for key in ("history_migration", "history_fields", "history_review"):
        assert line.data[key] == before[key]
    for item in old_dispatches:
        assert item.snapshot == old_snapshots[item.id]
    new_dispatches = list(db.scalars(select(Dispatch).where(Dispatch.line_id == line.id, Dispatch.version == 2)))
    assert {item.recipient for item in new_dispatches} == {"warehouse", "pmc"}
    for item in new_dispatches:
        assert item.snapshot["contract_no"] == REFERENCE
        assert item.snapshot["po_no"] == CUSTOMER_PO
        assert item.snapshot["customer_release_no"] == RELEASE
        assert item.snapshot["customer_label"] == LABEL
        assert item.snapshot["label"] == "No stickers"
        assert item.snapshot["shipped_quantity"] == "3000"
        assert "unit_price_hkd" not in item.snapshot and "lineage" not in item.snapshot
    assert save(db, payload(corrected=True))["items"][0]["id"] == line.id
    assert line.version == 2 and db.scalar(select(func.count()).select_from(Dispatch)) == 4
    with pytest.raises(HTTPException) as error:
        save(db, payload())
    assert error.value.status_code == 409
    assert line.version == 2 and line.data["po_no"] == CUSTOMER_PO


@pytest.mark.parametrize("change", [
    {"quantity": "9000"}, {"requested_ship_date": "2026-10-02"},
])
def test_number_mapping_prompt_does_not_disguise_quantity_or_date_changes(db, change):
    line = seed(db)
    incoming = payload(corrected=True)
    incoming["rows"][0].update(change)
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409 and "旧 360 单号对应关系" not in error.value.detail
    assert line.version == 1 and line.data["po_no"] == REFERENCE


@pytest.mark.parametrize("change", [
    {"po_no": "7654323"}, {"contract_no": "RL-765431-18"},
    {"customer_release_no": "RL765432118"}, {"production_no": "RL765432118"},
    {"customer_label": "外箱改贴另外一种条码"}, {"quantity": "9000"},
    {"requested_ship_date": "2026-10-02"},
])
def test_corrected_order_real_customer_field_changes_still_block(db, change):
    line = seed(db, corrected=True)
    before = deepcopy(line.data)
    incoming = payload(corrected=True)
    incoming["rows"][0].update(change)
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409 and "旧 360 单号对应关系" not in error.value.detail
    assert line.version == line.revision == 1 and line.data == before
    assert db.scalar(select(func.count()).select_from(Line)) == 1


@pytest.mark.parametrize("factory,customer", [("huaxing", "360"), ("huakang-a", "green-toys")])
def test_prompt_is_limited_to_huakang_a_360_and_does_not_relax_other_customers(db, factory, customer):
    line = seed(db, factory=factory, customer=customer)
    assert save(db, payload(factory=factory, customer=customer))["items"][0]["id"] == line.id
    incoming = payload(corrected=True, factory=factory, customer=customer)
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409 and "旧 360 单号对应关系" not in error.value.detail
    assert line.version == 1 and line.data["contract_no"] == RELEASE


def test_other_factory_same_reference_is_a_separate_order(db):
    local = seed(db)
    foreign = save(db, payload(corrected=True, factory="huaxing"))
    assert foreign["created_count"] == 1 and foreign["items"][0]["id"] != local.id
    assert local.version == 1 and db.scalar(select(func.count()).select_from(Line)) == 2


def test_stale_reconciliation_is_rejected_without_new_version_or_dispatch(db):
    line = seed(db)
    with pytest.raises(HTTPException) as error:
        save(db, payload(corrected=True), reconcile_line=line, expected_revision=0)
    assert error.value.status_code == 409 and "已被其他操作更新" in error.value.detail
    assert line.version == line.revision == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1
    assert db.scalar(select(func.count()).select_from(Dispatch)) == 0
