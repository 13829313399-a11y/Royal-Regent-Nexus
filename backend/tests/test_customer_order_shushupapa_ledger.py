"""Quantity amendments invalidate current Shushupapa USD explanations only."""
from copy import deepcopy

import pytest
from sqlalchemy import select

from app.models.customer_order_ledger import OrderLedgerDispatch as Dispatch, OrderLedgerVersion as Version
from app.schemas.customer_order_ledger import AmendIn, DispatchIn
from app.services import customer_order_ledger as service
from test_customer_order_ledger import db, engine, ingest, preview


def payload(factory="huaxing", customer="shushupapa", price="3.25"):
    result = preview(factory=factory, qty="180", reference="SYNTH-SHUSHU-1")
    result.update(customer_code=customer, customer_name="Synthetic Customer")
    row = result["rows"][0]
    row.update(
        unit_price_hkd="", amount_hkd="", unit_price_usd=price, amount_usd="585",
        price_details_text="PO 单价 USD 3.25；金额 USD 585；HKD 待核对汇率后填写",
        carton_count="15", customer_q="2026-09-24",
    )
    row["lineage"].update(
        unit_price_usd="synthetic-po.pdf · 第 1 页 · USD 3.25",
        amount_usd="当前数量 × PO 美元单价，四舍五入到美分；原 PO 数字金额 USD 585",
    )
    return result


def amend(db, line, quantity="240", ship_date="2026-10-01"):
    service.amend(db, line, AmendIn(
        expected_revision=line.revision, quantity=quantity,
        requested_ship_date=ship_date, note="", reason="客户提供合成修订要求",
    ), "synthetic-reviewer")
    db.commit()


def version(db, line, number):
    return db.scalar(select(Version).where(Version.line_id == line.id, Version.version == number))


def test_quantity_amend_invalidates_usd_explanation_preserving_old_version_and_dispatch(db):
    line = ingest(db, payload())
    original_data = deepcopy(line.data)
    original_version = deepcopy(version(db, line, 1).data)
    service.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=["pmc"]), "synthetic-reviewer")
    db.commit()
    old_dispatch = db.scalar(select(Dispatch).where(Dispatch.line_id == line.id, Dispatch.version == 1))
    original_snapshot = deepcopy(old_dispatch.snapshot)

    amend(db, line)

    assert line.version == 2 and line.data["quantity"] == "240"
    assert line.data["unit_price_usd"] == "3.25"
    assert line.data["amount_usd"] == line.data["carton_count"] == ""
    assert line.data["price_details_text"] == "原 PO 单价 USD 3.25；数量已调整，美元金额待新 PO 核对"
    assert line.data["lineage"]["amount_usd"] == "订单台账数量已调整，美元金额已清空，待新 PO 核对"
    assert line.data["lineage"]["unit_price_usd"] == original_data["lineage"]["unit_price_usd"]
    assert version(db, line, 2).data["price_details_text"] == line.data["price_details_text"]
    assert version(db, line, 2).data["lineage"]["amount_usd"] == line.data["lineage"]["amount_usd"]
    assert version(db, line, 1).data == original_version
    assert old_dispatch.snapshot == original_snapshot
    assert original_data["amount_usd"] == "585" and "金额 USD 585" in original_data["price_details_text"]
    for dispatch in db.scalars(select(Dispatch).where(Dispatch.line_id == line.id)):
        assert "amount_usd" not in dispatch.snapshot and "price_details_text" not in dispatch.snapshot


def test_date_only_amend_keeps_usd_amount_and_explanation(db):
    line = ingest(db, payload())
    original = deepcopy(line.data)

    amend(db, line, quantity="180", ship_date="2026-10-08")

    for field in ("unit_price_usd", "amount_usd", "price_details_text"):
        assert line.data[field] == original[field]
    assert line.data["lineage"]["amount_usd"] == original["lineage"]["amount_usd"]
    assert line.data["customer_q"] == ""


@pytest.mark.parametrize("factory,customer", [("huaxing", "maxx"), ("huakang-a", "shushupapa")])
def test_usd_explanation_cleanup_is_limited_to_huaxing_shushupapa(db, factory, customer):
    line = ingest(db, payload(factory=factory, customer=customer))
    original = deepcopy(line.data)

    amend(db, line)

    assert line.data["amount_usd"] == ""
    assert line.data["price_details_text"] == original["price_details_text"]
    assert line.data["lineage"]["amount_usd"] == original["lineage"]["amount_usd"]


@pytest.mark.parametrize("price,prefix", [("0", "原 PO 单价 USD 0；"), (None, "")])
def test_quantity_amend_retains_zero_or_unknown_unit_price_without_guessing(db, price, prefix):
    line = ingest(db, payload(price=price))

    amend(db, line)

    assert line.data["unit_price_usd"] == price
    assert line.data["amount_usd"] == ""
    assert line.data["price_details_text"] == prefix + "数量已调整，美元金额待新 PO 核对"
