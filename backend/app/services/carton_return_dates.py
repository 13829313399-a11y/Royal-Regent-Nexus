"""Immutable supplier return dates, independent of stock posting chronology."""
import json
import hashlib
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonAuditEvent, CartonInventoryMovement
from app.services.carton_ledger_time import ledger_time

EVENT = "RETURN_DATE_RECORDED"
CORRECTION_EVENT = "RETURN_DATE_CORRECTED"


def is_return(movement):
    return movement.source_type == "ORDER_RETURN" or (movement.movement_type == "OUTBOUND" and movement.issue_kind == "RETURN")


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def evidence(db, factory):
    """Fold the immutable version chain without rewriting its initial record."""
    result = {}
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type.in_([EVENT, CORRECTION_EVENT])).order_by(CartonAuditEvent.sequence)):
        detail = json.loads(event.detail_json)
        prior = result.get(event.entity_id)
        revision = 1 if prior is None else prior["revision"] + 1
        if event.event_type == CORRECTION_EVENT and (prior is None
            or detail.get("previous_event_id") != prior["event_id"]
            or detail.get("before_fingerprint") != prior["fingerprint"]
            or detail.get("before_date") != prior["return_date"]
            or detail.get("revision") != revision):
            raise HTTPException(409, "退货日期版本证据不完整，请核实原记录及更正历史")
        current = {"return_date": detail["return_date"], "revision": revision, "event_id": event.id}
        current["fingerprint"] = _fingerprint([factory, event.entity_id, current])
        result[event.entity_id] = current
    return result


def dates(db, factory):
    return {key: value["return_date"] for key, value in evidence(db, factory).items()}


def state(db, movement, *, records=None):
    records = evidence(db, movement.factory_id) if records is None else records
    current = records.get(movement.id)
    posting_date = ledger_time(movement.occurred_at).date().isoformat()
    if current:
        return {**current, "date_basis": "RETURN_ACTUAL", "posting_date": posting_date}
    original = {key: getattr(movement, key) for key in ("id", "factory_id", "source_type", "source_id",
        "source_line_id", "occurred_at", "unit", "currency")}
    original["quantity"] = format(Decimal(movement.quantity).normalize(), "f")
    return {"return_date": None, "date_basis": "RETURN_POSTING", "posting_date": posting_date,
            "revision": 0, "event_id": None, "fingerprint": _fingerprint(original)}


def history(db, movement):
    return [{"id": event.id, "event_type": event.event_type, "created_at": event.created_at,
             "actor_name": event.actor_name, **{key: value for key, value in json.loads(event.detail_json).items()
                if key not in {"fingerprint", "response"}}}
            for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == movement.factory_id,
                CartonAuditEvent.entity_id == movement.id, CartonAuditEvent.event_type.in_([EVENT, CORRECTION_EVENT]))
                .order_by(CartonAuditEvent.sequence))]


def require_date(value):
    from app.services import carton_procurement as core
    if not value:
        raise HTTPException(422, "请填写实际退货交接日期；库存仍按本次录入时间记账")
    try:
        day = date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "实际退货日期格式无效") from exc
    if day > ledger_time(core.now_text()).date().isoformat():
        raise HTTPException(422, "实际退货日期不能晚于今天")
    return day


def info(movement, evidence):
    if not is_return(movement) and not (movement.movement_type == "REVERSAL" and movement.issue_kind == "RETURN"):
        return {}
    day = evidence.get(movement.reversal_of_movement_id or movement.id)
    return {"return_date": day, "return_date_basis": "RETURN_ACTUAL" if day else "RETURN_POSTING",
            "return_posting_date": ledger_time(movement.occurred_at).date().isoformat()}


def record(db, user, movement, day, *, reason="", verified=False):
    from app.services import carton_procurement as core
    core._audit(db, user, movement.factory_id, EVENT, "carton_inventory_movement", movement.id,
                {"return_date": day, "posting_date": ledger_time(movement.occurred_at).date().isoformat(),
                 "occurred_at": movement.occurred_at, "reason": reason, "verified_legacy": verified})
    db.flush()


def correct(db, movement_id, payload, user):
    from app.services import carton_procurement as core, carton_special_requests as special
    from app.services.carton_supplier_settlement import return_supplier, ensure_open
    factory = core.require_carton_factory(payload.factory_id)
    user = special.locked_actor(db, user, factory)
    if not all(special.allowed(user, factory, permission) for permission in ("closing_manage", "order_adjust")):
        raise HTTPException(403, "更正退货日期须具备本厂主管月结与调整权限")
    movement = db.get(CartonInventoryMovement, movement_id)
    if movement is None or movement.factory_id != factory or not is_return(movement):
        raise HTTPException(404, "退货库存流水不存在")
    core.ensure_customer_operation(db, user, factory, movement.customer_code)
    digest, saved = special.replay(db, user, payload, "RETURN_DATE_CORRECTION", movement.id)
    if saved:
        return saved
    current = state(db, movement)
    if current["revision"] == 0:
        raise HTTPException(409, "历史退货尚未核实实际日期，请先核实原日期依据")
    if (current["revision"] != payload.expected_evidence_revision
        or current["fingerprint"] != payload.expected_evidence_fingerprint
        or db.scalar(select(CartonInventoryMovement.id).where(CartonInventoryMovement.factory_id == factory,
            CartonInventoryMovement.reversal_of_movement_id == movement.id))):
        raise HTTPException(409, "退货日期版本或来源状态已变化，请刷新后重新核对")
    if len(payload.reason.strip()) < 4:
        raise HTTPException(422, "请填写退货日期更正依据，至少四字")
    day = require_date(payload.return_date)
    if day == current["return_date"]:
        raise HTTPException(422, "更正日期与当前实际退货日期相同，无需重复更正")
    supplier = return_supplier(db, movement)
    if not supplier:
        raise HTTPException(409, "无法确定退货供应商，请先核实原收料来源")
    for period in sorted({day[:7], current["return_date"][:7]}):
        ensure_open(db, factory, supplier, period)
    event = core._audit(db, user, factory, CORRECTION_EVENT, "carton_inventory_movement", movement.id,
        {"before_date": current["return_date"], "before_revision": current["revision"],
         "before_fingerprint": current["fingerprint"], "previous_event_id": current["event_id"],
         "return_date": day, "revision": current["revision"] + 1, "reason": payload.reason.strip(),
         "request_id": payload.request_id, "fingerprint": digest})
    event.id = special.replay_id(user, payload)
    db.flush()
    result = {"movement_id": movement.id, "return_date": day, "posting_date": current["posting_date"],
              "date_basis": "RETURN_ACTUAL", "date_evidence": state(db, movement)}
    detail = json.loads(event.detail_json); detail["response"] = result
    event.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    db.commit()
    return result
