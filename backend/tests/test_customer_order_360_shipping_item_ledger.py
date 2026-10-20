"""A derived 360 shipping code must not replace the original ledger identity."""
from copy import deepcopy

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api import customer_order_ledger as api
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerVersion as Version
from app.services import customer_order_ledger as service
from test_customer_order_ledger import db, engine, migration
from test_customer_order_360_ledger_compat import payload, save


MISSING = object()


def shipping_payload(shipping=MISSING, *, product="76540010069", factory="huakang-a", customer="360"):
    result = payload(corrected=True, factory=factory, customer=customer)
    row = result["rows"][0]
    row.update(product_no=product, order_type="正单")
    if shipping is not MISSING:
        row["shipping_item"] = shipping
        row["lineage"]["shipping_item"] = "旧排期出货货号格式 · 由原产品编号派生"
    return result


@pytest.mark.parametrize("old_shipping", [MISSING, None, ""])
@pytest.mark.parametrize("product,derived", [
    ("76540010069", "7654001"), ("00765430069", "0076543"),
    ("1234567890.01", "1234567890"), ("0076543", "0076543"),
    ("0076543006", "0076543006"), ("UNRECOGNIZED", ""),
])
def test_new_derived_shipping_field_reuses_old_id_without_rewriting_data(db, old_shipping, product, derived):
    original = shipping_payload(old_shipping, product=product)
    line = db.get(Line, save(db, original)["items"][0]["id"])
    before, old_key = deepcopy(line.data), line.identity_key
    incoming = shipping_payload(derived, product=product)
    assert service.identity_for(original["rows"][0], "360") == service.identity_for(incoming["rows"][0], "360")

    result = save(db, incoming)

    assert result["created_count"] == 0 and result["existing_count"] == 1
    assert result["items"][0]["id"] == line.id and line.identity_key == old_key
    assert line.data == before and line.version == line.revision == 1
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1


@pytest.mark.parametrize("incoming_shipping", ["SPECIAL-1", "76540010069", "7654001 ", 7654001])
def test_missing_old_value_does_not_authorize_manual_or_nonexact_shipping_code(db, incoming_shipping):
    line = db.get(Line, save(db, shipping_payload())["items"][0]["id"])
    before = deepcopy(line.data)
    with pytest.raises(HTTPException) as error:
        save(db, shipping_payload(incoming_shipping))
    assert error.value.status_code == 409 and "shipping_item" in error.value.detail
    assert line.data == before and line.version == 1


@pytest.mark.parametrize("previous,incoming", [("SPECIAL-1", "7654001"), ("7654001", "SPECIAL-1"), (" ", "7654001"), ("7654001", "")])
def test_existing_nonempty_shipping_value_changes_require_explicit_revision(db, previous, incoming):
    line = db.get(Line, save(db, shipping_payload(previous))["items"][0]["id"])
    before = deepcopy(line.data)
    with pytest.raises(HTTPException) as error:
        save(db, shipping_payload(incoming))
    assert error.value.status_code == 409 and "shipping_item" in error.value.detail
    assert line.data == before and line.version == line.revision == 1


@pytest.mark.parametrize("changes", [
    {"quantity": "9999"}, {"requested_ship_date": "2026-10-02"},
    {"po_no": "OTHER-PO"}, {"contract_no": "OTHER-CONTRACT"},
    {"customer_label": "Changed carton label"}, {"order_type": "备料单"},
])
def test_derived_shipping_compatibility_does_not_hide_other_business_changes(db, changes):
    line = db.get(Line, save(db, shipping_payload())["items"][0]["id"])
    before = deepcopy(line.data)
    incoming = shipping_payload("7654001")
    incoming["rows"][0].update(changes)
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409
    assert line.data == before and line.version == line.revision == 1
    assert db.scalar(select(func.count()).select_from(Line)) == 1


@pytest.mark.parametrize("factory,customer", [("huaxing", "360"), ("huakang-a", "green-toys")])
def test_new_shipping_field_compatibility_is_limited_to_huakang_a_360(db, factory, customer):
    line = db.get(Line, save(db, shipping_payload(factory=factory, customer=customer))["items"][0]["id"])
    with pytest.raises(HTTPException) as error:
        save(db, shipping_payload("7654001", factory=factory, customer=customer))
    assert error.value.status_code == 409 and "shipping_item" in error.value.detail
    assert "shipping_item" not in line.data and line.version == 1


def test_two_original_product_suffixes_keep_distinct_identities_with_same_shipping_code(db):
    first = shipping_payload("7654001", product="76540010069")
    second = shipping_payload("7654001", product="76540010070")
    assert service.identity_for(first["rows"][0], "360") != service.identity_for(second["rows"][0], "360")
    ids = {save(db, item)["items"][0]["id"] for item in (first, second)}
    assert len(ids) == 2 and db.scalar(select(func.count()).select_from(Line)) == 2
    assert {save(db, item)["items"][0]["id"] for item in (first, second)} == ids


def test_explicit_shipping_revision_keeps_original_id_and_immutable_version(db):
    line = db.get(Line, save(db, shipping_payload("SPECIAL-1"))["items"][0]["id"])
    old_key = line.identity_key
    original_version = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 1))
    original_data = deepcopy(original_version.data)
    incoming = shipping_payload("7654001")
    result = api.transaction(db, lambda: service.import_preview(db, preview=incoming,
        files=[], source_kind="formal", actor="sales", reason="核对原订单出货货号格式", controls={},
        reconcile_line=line, expected_revision=line.revision))
    assert result["reconciled_count"] == 1 and result["created_count"] == 0
    assert result["items"][0]["id"] == line.id and line.identity_key == old_key
    assert line.data["shipping_item"] == "7654001" and line.product_no == "76540010069"
    assert line.version == 2 and original_version.data == original_data
    assert save(db, incoming)["items"][0]["id"] == line.id
    assert line.version == 2


def test_old_missing_shipping_field_keeps_id_after_database_close_and_reopen(tmp_path):
    url = f"sqlite:///{tmp_path / '360-ledger.sqlite'}"
    first_engine = create_engine(url)
    with first_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
    with Session(first_engine, expire_on_commit=False, autoflush=False) as first:
        line = first.get(Line, save(first, shipping_payload(product="00765430069"))["items"][0]["id"])
        line_id, original_key, before = line.id, line.identity_key, deepcopy(line.data)
        assert save(first, shipping_payload("0076543", product="00765430069"))["items"][0]["id"] == line_id
    first_engine.dispose()

    reopened_engine = create_engine(url)
    try:
        with Session(reopened_engine, expire_on_commit=False, autoflush=False) as reopened:
            result = save(reopened, shipping_payload("0076543", product="00765430069"))
            line = reopened.get(Line, line_id)
            assert result["created_count"] == 0 and result["items"][0]["id"] == line_id
            assert line.identity_key == original_key and line.data == before
            assert line.product_no == "00765430069" and line.version == line.revision == 1
            assert reopened.scalar(select(func.count()).select_from(Version)) == 1
    finally:
        reopened_engine.dispose()
