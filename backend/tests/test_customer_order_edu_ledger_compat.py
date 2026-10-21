"""EDU product-tail migration must reuse ledger evidence, never silently merge orders."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from io import BytesIO

from fastapi import HTTPException
import openpyxl
import pytest
from sqlalchemy import func, select

from app.api import customer_order_ledger as api
from app.models.customer_order_ledger import (
    OrderLedgerIdentity as Identity, OrderLedgerLine as Line,
    OrderLedgerVersion as Version, OrderLedgerShipment as Shipment,
    OrderLedgerDispatch as Dispatch,
)
from app.schemas.customer_order_ledger import DispatchIn, HistorySelection
from app.services import customer_order_ledger as service
from app.services import customer_order_history as history
from test_customer_order_ledger import db, engine, preview, ship_body


RAW = "F12-BL172-C0030000"
BASE = "F12-BL172-C003"


def edu_preview(*, product=RAW, factory="huaxing", contract="C001", po="PO-0001", qty="10000"):
    result = preview(factory=factory, qty=qty, reference="EDUHX00104")
    result.update(customer_code="edu", customer_name="EDU")
    result["rows"][0].update(product_no=product, contract_no=contract, po_no=po,
                             units_per_carton="16", carton_count="625")
    return result


def old_identity(row):
    return service.digest(["edu-po", *(str(row.get(key) or "").strip().casefold()
                                      for key in ("contract_no", "po_no", "product_no"))])


def seed_legacy(db, payload=None, *, with_alias=True):
    payload = payload or edu_preview()
    row = payload["rows"][0]
    line = Line(id=service.uid(), factory_id=payload["factory_id"], customer_code="edu",
        customer_name="EDU", identity_key=old_identity(row), reference_no=row["reference_no"],
        product_no=row["product_no"], quantity=Decimal(row["quantity"]), shipped_quantity=Decimal(0),
        status="active", version=1, revision=1,
        data={**deepcopy(row), "source_kind": "formal", "import_controls": {}},
        created_at=service.now_text(), updated_at=service.now_text())
    db.add(line)
    db.flush()
    service.record_version(db, line, "旧版本已核对订单", "legacy")
    if with_alias:
        db.add(Identity(factory_id=line.factory_id, customer_code="edu", identity_key=line.identity_key, line_id=line.id))
    db.commit()
    return line


def save(db, payload, **kwargs):
    return api.transaction(db, lambda: service.import_preview(db, preview=payload,
        files=[("EDU.xls", b"EDU source", "formal")], source_kind="formal",
        actor="sales", reason="正式订单核对确认", controls={}, **kwargs))


@pytest.mark.parametrize("with_alias", [False, True])
def test_old_full_product_reimport_reuses_line_versions_and_shipments(db, with_alias):
    line = seed_legacy(db, with_alias=with_alias)
    service.ship(db, line, ship_body(line), "warehouse")
    db.commit()
    before = deepcopy(line.data)
    old_key, old_revision = line.identity_key, line.revision
    incoming = edu_preview(product=BASE)
    incoming["rows"][0].update(source_product_no=RAW, reference_no="EDUHX99999")

    result = save(db, incoming)

    assert result["created_count"] == 0 and result["existing_count"] == 1
    assert result["items"][0]["id"] == line.id
    assert line.data == before and line.identity_key == old_key and line.product_no == RAW
    assert line.version == 1 and line.revision == old_revision and line.shipped_quantity == 3000
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1
    assert db.scalar(select(func.count()).select_from(Shipment)) == 1
    canonical = service.identity_for(incoming["rows"][0], "edu")
    assert db.get(Identity, ("huaxing", "edu", canonical)).line_id == line.id
    again = deepcopy(incoming)
    again["rows"][0].update(product_no="f12-bl172-c0030001", source_product_no="F12-BL172-C0030001")
    assert save(db, again)["items"][0]["id"] == line.id
    assert line.data == before and line.version == 1


def test_canonical_identity_is_edu_only_and_leaves_unknown_layout_intact():
    full, short = edu_preview()["rows"][0], edu_preview(product=BASE)["rows"][0]
    assert service.identity_for(full, "edu") == service.identity_for(short, "edu")
    assert service.identity_for(full, "buzzbee") != service.identity_for(short, "buzzbee")
    assert service.identity_for({**full, "product_no": "OTHER0001"}, "edu") != service.identity_for({**full, "product_no": "OTHER"}, "edu")


@pytest.mark.parametrize("old_pack", ["1/16", "16.0", 16])
def test_new_source_metadata_and_equivalent_outer_pack_do_not_create_false_revisions(db, old_pack):
    prior = edu_preview()
    prior["rows"][0].update(units_per_carton=old_pack, edu_reservation_row="43")
    line = seed_legacy(db, prior)
    before = deepcopy(line.data)
    incoming = edu_preview(product=BASE)
    incoming["rows"][0].update(source_product_no=RAW, source_order_date="2026-10-09", edu_reservation_row="44")
    assert save(db, incoming)["items"][0]["id"] == line.id
    assert line.version == 1 and line.data == before


def test_changed_previously_recorded_source_date_still_requires_reconciliation(db):
    prior = edu_preview()
    prior["rows"][0]["source_order_date"] = "2026-10-09"
    line = seed_legacy(db, prior)
    incoming = edu_preview(product=BASE)
    incoming["rows"][0]["source_order_date"] = "2026-10-10"
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409 and "source_order_date" in error.value.detail
    assert line.version == 1


def test_same_normalized_product_never_links_across_factories(db):
    original = seed_legacy(db)
    result = save(db, edu_preview(product=BASE, factory="huadeng"))
    assert result["created_count"] == 1 and result["items"][0]["id"] != original.id
    assert result["items"][0]["factory_id"] == "huadeng"
    assert db.scalar(select(func.count()).select_from(Line)) == 2
    with pytest.raises(HTTPException) as error:
        save(db, edu_preview(product=BASE, factory="huadeng"), reconcile_line=original,
             expected_revision=original.revision)
    assert error.value.status_code == 400


@pytest.mark.parametrize("canonical_alias", [False, True])
def test_multiple_legacy_candidates_block_even_when_one_has_canonical_alias(db, canonical_alias):
    first = seed_legacy(db)
    second = seed_legacy(db, edu_preview(product="F12-BL172-C0030001"))
    incoming = edu_preview(product=BASE)
    if canonical_alias:
        db.add(Identity(factory_id="huaxing", customer_code="edu",
            identity_key=service.identity_for(incoming["rows"][0], "edu"), line_id=first.id))
        db.commit()
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409 and "多条历史订单" in error.value.detail
    assert db.scalar(select(func.count()).select_from(Line)) == 2
    assert first.version == second.version == 1


@pytest.mark.parametrize("change", [
    {"quantity": "9000"}, {"requested_ship_date": "2026-10-02"},
    {"units_per_carton": "24"}, {"source_product_no": "F12-BL999-C0030000"},
])
def test_compatibility_does_not_hide_real_quantity_date_pack_or_product_changes(db, change):
    line = seed_legacy(db)
    incoming = edu_preview(product=BASE)
    incoming["rows"][0].update(change)
    before = deepcopy(line.data)
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert line.data == before and line.version == 1
    assert db.get(Identity, ("huaxing", "edu", service.identity_for(incoming["rows"][0], "edu"))) is None


@pytest.mark.parametrize("with_alias", [False, True])
def test_formal_reconciliation_preserves_old_alias_shipments_and_immutable_versions(db, with_alias):
    line = seed_legacy(db, with_alias=with_alias)
    old_key, before = line.identity_key, deepcopy(line.data)
    service.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=["warehouse"]), "sales")
    service.ship(db, line, ship_body(line), "warehouse")
    db.commit()
    incoming = edu_preview(product=BASE, contract="FORMAL-C002", po="FORMAL-PO002", qty="9000")
    incoming["rows"][0].update(source_product_no=RAW, units_per_carton="24", carton_count="375")
    result = save(db, incoming, reconcile_line=line, expected_revision=line.revision)
    assert result["reconciled_count"] == 1 and result["items"][0]["id"] == line.id
    assert line.quantity == 9000 and line.shipped_quantity == 3000 and line.version == 2
    assert line.product_no == RAW and line.data["product_no"] == BASE
    assert db.get(Identity, ("huaxing", "edu", old_key)).line_id == line.id
    first_version = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 1))
    assert first_version.data == {**before, "status": "active"}
    assert db.scalar(select(Dispatch).where(Dispatch.version == 2)).snapshot["units_per_carton"] == "24"
    assert save(db, incoming)["items"][0]["id"] == line.id
    old_short = edu_preview(product=BASE)
    assert service.resolve_existing_line(db, "huaxing", "edu", old_short["rows"][0]).id == line.id
    with pytest.raises(HTTPException) as error:
        save(db, old_short)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 2
    assert db.scalar(select(func.count()).select_from(Shipment)) == 1


def test_earlier_formal_reconciliation_is_resolved_through_legacy_version_alias(db):
    line = seed_legacy(db)
    changed = edu_preview(contract="FORMAL-C002", po="FORMAL-PO002")["rows"][0]
    line.data = {**deepcopy(changed), "source_kind": "formal", "import_controls": {}}
    line.identity_key = old_identity(changed)
    line.version += 1
    service.record_version(db, line, "旧版本正式PO关联", "legacy")
    db.add(Identity(factory_id="huaxing", customer_code="edu", identity_key=line.identity_key, line_id=line.id))
    db.commit()
    old_short = edu_preview(product=BASE)
    assert service.resolve_existing_line(db, "huaxing", "edu", old_short["rows"][0]).id == line.id
    with pytest.raises(HTTPException) as error:
        save(db, old_short)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1


def test_formal_reconciliation_cannot_take_another_legacy_identity(db):
    line = seed_legacy(db)
    other = seed_legacy(db, edu_preview(contract="OTHER", po="OTHER-PO"))
    with pytest.raises(HTTPException) as error:
        save(db, edu_preview(product=BASE, contract="OTHER", po="OTHER-PO"),
             reconcile_line=line, expected_revision=line.revision)
    assert error.value.status_code == 409 and "属于另一条" in error.value.detail
    assert line.version == other.version == 1
    assert line.revision == 1


def test_reconcile_canonical_old_row_without_alias_adds_identity_only_once(db):
    line = seed_legacy(db, edu_preview(product=BASE), with_alias=False)
    result = save(db, edu_preview(product=BASE, qty="9000"), reconcile_line=line,
                  expected_revision=line.revision)
    assert result["items"][0]["id"] == line.id and line.version == 2
    assert db.scalar(select(func.count()).select_from(Identity)) == 1


def test_unowned_old_snapshot_does_not_claim_an_unrelated_identity(db):
    line = seed_legacy(db)
    changed = edu_preview(contract="FORMAL-C002", po="FORMAL-PO002")["rows"][0]
    line.data = {**deepcopy(changed), "source_kind": "formal", "import_controls": {}}
    line.version += 1
    service.record_version(db, line, "只有版本内容并非身份归属", "legacy")
    db.commit()
    incoming = edu_preview(product=BASE, contract="FORMAL-C002", po="FORMAL-PO002")
    assert service.resolve_existing_line(db, "huaxing", "edu", incoming["rows"][0]) is None


def test_corrupt_cross_factory_alias_does_not_expose_or_reuse_foreign_line(db):
    foreign = seed_legacy(db, edu_preview(factory="huadeng"))
    incoming = edu_preview(product=BASE)
    db.add(Identity(factory_id="huaxing", customer_code="edu",
        identity_key=service.identity_for(incoming["rows"][0], "edu"), line_id=foreign.id))
    db.commit()
    with pytest.raises(HTTPException) as error:
        save(db, incoming)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1


def history_workbook(product=BASE):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "ITEM表"
    sheet.append([])
    sheet.append([])
    sheet.append(["Contract No.", "SO#/Reference", "P/O#:", "产品编号", "数量", "客要求走货期"])
    sheet.append(["C001", "EDUHX00104", "PO-0001", product, 10000, date(2026, 10, 1)])
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def history_preview(db, content, factory="huaxing"):
    return history.preview(db, content, "EDU历史.xlsx", factory, "edu", "EDU")


def history_confirm(db, parsed, content):
    return api.transaction(db, lambda: history.confirm(db, parsed=parsed, content=content,
        selections=[HistorySelection(id=parsed["rows"][0]["id"], status="active", opening_shipped_quantity="3000")],
        fingerprint=parsed["fingerprint"], cutoff_date=date(2025, 12, 31),
        reason="逐行核对历史期初", actor="sales"))


def test_history_short_product_cannot_bypass_existing_raw_ledger(db):
    line = seed_legacy(db)
    content = history_workbook()
    parsed = history_preview(db, content)
    assert parsed["summary"]["existing"] == 1
    assert any("台账已有" in issue for issue in parsed["rows"][0]["issues"])
    with pytest.raises(HTTPException) as error:
        history_confirm(db, parsed, content)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert line.shipped_quantity == 0 and line.version == 1


def test_history_confirmation_rechecks_a_legacy_order_created_after_preview(db):
    content = history_workbook()
    parsed = history_preview(db, content)
    assert parsed["summary"]["existing"] == 0
    seed_legacy(db)
    with pytest.raises(HTTPException) as error:
        history_confirm(db, parsed, content)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 1


def test_history_same_file_old_raw_retry_reuses_opening_and_adds_alias(db):
    original = history_workbook(RAW)
    parsed = history_preview(db, original)
    parsed["rows"][0]["identity"] = old_identity(parsed["rows"][0]["data"])
    result = history_confirm(db, parsed, original)
    line = db.get(Line, result["items"][0]["id"])
    before, old_key = deepcopy(line.data), line.identity_key
    reparsed = history_preview(db, original)
    assert reparsed["summary"]["existing"] == 1
    retried = history_confirm(db, reparsed, original)
    assert retried["created_count"] == 0 and retried["existing_count"] == 1
    assert line.data == before and line.identity_key == old_key and line.product_no == RAW
    assert line.shipped_quantity == 3000 and line.version == 1
    canonical = service.identity_for(reparsed["rows"][0]["data"], "edu")
    assert canonical != old_key
    assert db.get(Identity, ("huaxing", "edu", canonical)).line_id == line.id
    assert db.scalar(select(func.count()).select_from(Version)) == 1
    assert db.scalar(select(func.count()).select_from(Shipment)) == 0
    replacement = history_workbook(BASE)
    with pytest.raises(HTTPException) as error:
        history_confirm(db, history_preview(db, replacement), replacement)
    assert error.value.status_code == 409  # A changed file cannot replace the original opening.


def test_history_ambiguous_legacy_candidates_block_both_preview_and_stale_confirm(db):
    content = history_workbook()
    stale = history_preview(db, content)
    seed_legacy(db)
    seed_legacy(db, edu_preview(product="F12-BL172-C0030001"))
    parsed = history_preview(db, content)
    assert parsed["summary"]["blocked"] == 1
    assert any("多条历史订单" in issue for issue in parsed["rows"][0]["issues"])
    with pytest.raises(HTTPException) as error:
        history_confirm(db, stale, content)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Line)) == 2


def test_history_compatibility_does_not_cross_factory(db):
    original = seed_legacy(db)
    content = history_workbook()
    parsed = history_preview(db, content, factory="huadeng")
    assert parsed["summary"]["existing"] == 0
    result = history_confirm(db, parsed, content)
    assert result["created_count"] == 1 and result["items"][0]["id"] != original.id
    assert result["items"][0]["factory_id"] == "huadeng"
    assert original.shipped_quantity == 0
