from decimal import Decimal

from app.services import carton_monthly_settlement as monthly


def row(kind="RECEIPT", amount="100.00", issues=None, document_no="DN-1", item_no="ITEM-1"):
    return {"kind": kind, "amount": amount, "document_no": document_no, "item_no": item_no, "issues": issues or []}


def test_totals_require_every_price_to_be_known():
    assert monthly._sum([row("RECEIPT", "1.10"), row("RECEIPT", "2.20")]) == Decimal("3.30")
    assert monthly._sum([row("RECEIPT", "1.10"), row("RECEIPT", None)]) is None
    assert monthly._sum([]) == Decimal("0")


def test_blocking_issues_explain_each_reason_a_month_cannot_lock():
    rows = [
        row("RECEIPT", "100.00"),
        row("RECEIPT", None, ["入库单价待核实"], document_no="DN-2", item_no="ITEM-2"),
        row("RETURN", None, document_no="RT-1", item_no="ITEM-3"),
        row("RECEIPT", "50.00", ["收料与有效入库流水不一致"], document_no="DN-3", item_no="ITEM-4"),
    ]
    issues = monthly.blocking_issues(rows, ["退货 RT-9 无法确定唯一供应商"], [{"document_no": "DN-OLD"}])
    joined = "\n".join(issues)
    assert "1 行送货单缺价" in joined and "DN-2" in joined
    assert "1 笔退货还没有供应商贷项价格" in joined and "RT-1" in joined
    assert "收料与有效入库流水不一致" in joined
    assert "未核实实际验收日期" in joined and "DN-OLD" in joined
    assert "无法确定唯一供应商" in joined
    assert len(issues) == len(set(issues))


def test_blocking_issues_is_empty_for_a_clean_priced_month():
    assert monthly.blocking_issues([row("RECEIPT", "10.00"), row("RETURN", "2.00")], [], []) == []


def test_entity_id_is_scoped_by_supplier_period_and_currency():
    assert monthly.entity_id("SUP-1", "2026-10", "CNY") == "SUP-1:2026-10:CNY"


def event(kind, detail=None, at="2026-11-01T10:00:00+08:00", actor="系统管理员"):
    return {"type": kind, "detail": detail or {}, "at": at, "actor": actor}


def test_supplier_must_confirm_between_submit_and_lock():
    submitted = monthly.derive_state([event(monthly.SUBMIT_EVENT, {"fingerprint": "f1", "totals": {"net": "10.00"}})])
    assert submitted["status"] == "SUBMITTED" and submitted["fingerprint"] == "f1"
    confirmed = monthly.derive_state([event(monthly.SUBMIT_EVENT, {"fingerprint": "f1"}),
                                      event(monthly.CONFIRM_EVENT, actor="东康")])
    assert confirmed["status"] == "CONFIRMED" and confirmed["confirmed_by"] == "东康"
    locked = monthly.derive_state([event(monthly.SUBMIT_EVENT, {"fingerprint": "f1"}),
                                   event(monthly.CONFIRM_EVENT, actor="东康"),
                                   event(monthly.LOCK_EVENT, {"totals": {"net": "10.00"}})])
    assert locked["status"] == "LOCKED" and locked["totals"] == {"net": "10.00"}


def test_dispute_clears_confirmation_and_unlock_returns_to_open():
    disputed = monthly.derive_state([event(monthly.SUBMIT_EVENT, {"fingerprint": "f1"}),
                                     event(monthly.CONFIRM_EVENT, actor="东康"),
                                     event(monthly.DISPUTE_EVENT, {"reason": "退货金额不对"}, actor="东康")])
    assert disputed["status"] == "DISPUTED" and disputed["confirmed_at"] is None
    assert disputed["disputed_reason"] == "退货金额不对"
    reopened = monthly.derive_state([event(monthly.SUBMIT_EVENT, {"fingerprint": "f1"}),
                                     event(monthly.LOCK_EVENT, {"totals": {"net": "10.00"}}),
                                     event(monthly.UNLOCK_EVENT, {"reason": "供应商补价"}, actor="主管")])
    assert reopened["status"] == "OPEN" and reopened["fingerprint"] == "" and reopened["locked_at"] is None


def test_stale_only_compares_a_submitted_fingerprint():
    assert monthly.is_stale({"fingerprint": "f1"}, "f2") is True
    assert monthly.is_stale({"fingerprint": "f1"}, "f1") is False
    assert monthly.is_stale({"fingerprint": ""}, "f2") is False
