"""Factory count thresholds and immutable posting evidence; no quantity writes."""
import json
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_master import CartonMasterRecord
from app.models.carton_procurement import CartonException
from app.services.auth import authorization_decision
from app.services.carton_inventory_valuation import cost_key


def allowed(user, permission, factory):
    return any(authorization_decision(user, permission, factory, dept)[0]
               for dept in ("carton", "pmc-warehouse"))


def require(user, permission, factory):
    if not allowed(user, permission, factory):
        raise HTTPException(403, "当前账号缺少本厂区的" + (
            "主管调整权限" if permission.endswith(":order_adjust") else "盘点操作或规则管理权限"))


def policy(db, factory):
    row = db.scalar(select(CartonMasterRecord).where(
        CartonMasterRecord.factory_id == factory, CartonMasterRecord.kind == "STOCKTAKE_RULE",
        CartonMasterRecord.identity == "default"))
    return {"factory_id": factory, "revision": row.revision if row else 0,
            **(json.loads(row.data_json) if row else {"amount_threshold": "500", "ratio_threshold": "0.05"})}


def update_policy(db, payload, user, refresh_user):
    from app.services.identity_policy import lock_mutation
    from app.services.carton_stocktake import _lock
    from app.services import carton_procurement as ledger
    lock_mutation(db)
    _lock(db, payload.factory_id)
    user = refresh_user()
    for code in ("carton_procurement:order_adjust", "carton_procurement:master_manage"):
        require(user, code, payload.factory_id)
    before = policy(db, payload.factory_id)
    if before["revision"] != payload.expected_revision:
        raise HTTPException(409, "盘点规则已更新，请刷新后重试")
    row = db.scalar(select(CartonMasterRecord).where(
        CartonMasterRecord.factory_id == payload.factory_id, CartonMasterRecord.kind == "STOCKTAKE_RULE",
        CartonMasterRecord.identity == "default"))
    if row is None:
        row = CartonMasterRecord(id=f"STR-{uuid4().hex}", factory_id=payload.factory_id,
                                 kind="STOCKTAKE_RULE", identity="default")
        db.add(row)
    row.revision = before["revision"] + 1
    row.data_json = json.dumps({"amount_threshold": str(payload.amount_threshold),
                               "ratio_threshold": str(payload.ratio_threshold)})
    row.updated_at = ledger.now_text()
    ledger._audit(db, user, payload.factory_id, "STOCKTAKE_POLICY_UPDATED", "carton_stocktake_policy", row.id,
                  {"before": before, "after": json.loads(row.data_json), "revision": row.revision,
                   "reason": payload.reason})
    db.commit()
    return policy(db, payload.factory_id)


def assess(lines, references, valuation, rules):
    total = Decimal(0)
    evidence, triggers = [], set()
    for line in lines:
        diff = line.difference
        if diff is None:
            continue
        reference = references[line.reference_movement_id]
        key = cost_key(reference)
        carrying = valuation.balances.get(key)
        known = bool(carrying and carrying.quantity > 0 and key not in valuation.unpriced_pools
                     and not any(cost_key(row) == key for row, _ in valuation.errors))
        amount = (abs(diff) * carrying.amount / carrying.quantity) if known else (Decimal(0) if diff == 0 else None)
        ratio = abs(diff) / line.count_book_quantity if line.count_book_quantity > 0 else (Decimal(0) if diff == 0 else None)
        if diff:
            if key[-1] != "CNY": triggers.add("非人民币差异需主管核对")
            elif amount is None: triggers.add("差异成本尚未确定")
            else: total += amount
            if ratio is None or ratio >= Decimal(rules["ratio_threshold"]):
                triggers.add("仓位数量差异达到门槛")
        evidence.append({"id": line.id, "difference": str(diff), "book_quantity": str(line.count_book_quantity),
                         "amount": None if amount is None else str(amount), "currency": key[-1],
                         "ratio": None if ratio is None else str(ratio)})
    if total >= Decimal(rules["amount_threshold"]): triggers.add("差异绝对金额合计达到门槛")
    return {"policy": rules, "requires_supervisor": bool(triggers), "triggers": sorted(triggers),
            "absolute_amount_cny": str(total), "has_difference": any(line.difference for line in lines),
            "complete": all(line.difference is not None for line in lines), "lines": evidence}


def flag_differences(db, doc, lines, user, assessment):
    """All nonzero differences remain visible until an explicit supervisor disposition."""
    for line in lines:
        if not line.difference:
            continue
        snapshot = json.loads(line.snapshot_json)
        identifier = f"CEX-{uuid4().hex}"
        db.add(CartonException(id=identifier, exception_no=identifier, factory_id=doc.factory_id,
            source_type="STOCKTAKE", source_id=doc.id, category="STOCKTAKE_REVIEW",
            severity="HIGH" if assessment["requires_supervisor"] else "LOW",
            **{name: snapshot.get(name, "") for name in ("customer_code", "customer_name", "contract_no", "item_no")},
            title="盘点差异待复核" if assessment["requires_supervisor"] else "盘点差异待抽查",
            description=f"盘点单 {doc.id}；仓位 {snapshot['latest_location']}；差异 {line.difference}；原因：{line.reason}",
            status="OPEN", revision=1, created_by=user.id, created_by_name=user.display_name,
            updated_by=user.id, updated_by_name=user.display_name, created_at=doc.reviewed_at, updated_at=doc.reviewed_at))
