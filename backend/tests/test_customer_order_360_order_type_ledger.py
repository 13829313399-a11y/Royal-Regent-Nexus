"""360 defaults must preserve old ledger evidence and explicit revision ownership."""
from copy import deepcopy

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.api import customer_order_ledger as api
from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerVersion as Version
from app.services import customer_order_ledger as service
from test_customer_order_ledger import db, engine
from test_customer_order_360_ledger_compat import payload, save


def typed_payload(order_type, *, source_lineage=False):
    result = payload(corrected=True)
    row = result["rows"][0]
    if order_type is not None:
        row["order_type"] = order_type
    if source_lineage:
        row["lineage"].update(
            order_type="华康A 360 业务规则 · 新 PURCHASE ORDER RELEASE 记为正单",
            source_order_type="360-release.pdf · RL Order Type: DI Order",
        )
    return result


def test_existing_formal_order_reimport_ignores_new_source_lineage_without_rewriting_it(db):
    original = typed_payload("正单")
    line = db.get(Line, save(db, original)["items"][0]["id"])
    before = deepcopy(line.data)
    incoming = typed_payload("正单", source_lineage=True)
    assert "source_order_type" not in incoming["rows"][0]

    result = save(db, incoming)

    assert result["created_count"] == 0 and result["existing_count"] == 1
    assert result["items"][0]["id"] == line.id
    assert line.data == before and line.version == line.revision == 1
    assert "source_order_type" not in line.data["lineage"]
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1


@pytest.mark.parametrize("old_type", ["DI Order", "", None])
def test_old_di_or_unknown_type_reimport_requires_revision_on_original_id(db, old_type):
    line = db.get(Line, save(db, typed_payload(old_type))["items"][0]["id"])
    before = deepcopy(line.data)
    original_version = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 1))
    original_version_data = deepcopy(original_version.data)
    incoming = typed_payload("正单", source_lineage=True)
    assert service.resolve_existing_line(db, "huakang-a", "360", incoming["rows"][0]).id == line.id

    with pytest.raises(HTTPException) as error:
        save(db, incoming)

    assert error.value.status_code == 409
    assert "order_type" in error.value.detail and "关联正式 PO" in error.value.detail
    assert line.data == before and line.version == line.revision == 1
    assert original_version.data == original_version_data
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 1


@pytest.mark.parametrize("old_type", ["DI Order", "", None])
def test_explicit_type_revision_preserves_id_original_version_and_history(db, old_type):
    original = typed_payload(old_type)
    original["rows"][0].update(
        history_migration={"cutoff_date": "2025-12-31", "opening_shipped_quantity": "0"},
        history_fields={"原订单类型": old_type or ""},
    )
    line = db.get(Line, save(db, original)["items"][0]["id"])
    before = deepcopy(line.data)
    old_key = line.identity_key
    original_version = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 1))
    original_version_data = deepcopy(original_version.data)
    incoming = typed_payload("正单", source_lineage=True)
    reason = "按业务确认修订订单类型为正单"

    result = api.transaction(db, lambda: service.import_preview(db, preview=incoming,
        files=[], source_kind="formal", actor="sales", reason=reason, controls={},
        reconcile_line=line, expected_revision=line.revision))

    assert result["created_count"] == 0 and result["reconciled_count"] == 1
    assert result["items"][0]["id"] == line.id and line.identity_key == old_key
    assert line.version == line.revision == 2 and line.data["order_type"] == "正单"
    assert original_version.data == original_version_data
    assert original_version.data.get("order_type") == old_type
    for key in ("history_migration", "history_fields"):
        assert line.data[key] == before[key]
    assert line.data["lineage"]["source_order_type"].endswith("RL Order Type: DI Order")
    assert "source_order_type" not in line.data
    revision = db.scalar(select(Version).where(Version.line_id == line.id, Version.version == 2))
    assert revision.data["order_type"] == "正单" and revision.reason == reason
    assert save(db, incoming)["items"][0]["id"] == line.id
    assert line.version == 2
    assert db.scalar(select(func.count()).select_from(Line)) == 1
    assert db.scalar(select(func.count()).select_from(Version)) == 2
