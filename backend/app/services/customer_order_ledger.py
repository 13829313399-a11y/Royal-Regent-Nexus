"""Order ledger operations. Existing PO parsers and workbook writers are reused unchanged."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.customer_order_ledger import (
    OrderLedgerLine as Line, OrderLedgerVersion as Version,
    OrderLedgerSource as Source, OrderLedgerLineSource as LineSource,
    OrderLedgerDispatch as Dispatch, OrderLedgerShipment as Shipment,
    OrderLedgerShipmentReversal as Reversal,
    OrderLedgerIdentity as Identity,
)
from app.services.auth import now_text

RECIPIENTS = {"pmc": ("pmc-warehouse",), "warehouse": ("pmc-warehouse", "warehouse"), "injection": ("production", "molding")}
PUBLIC_FIELDS = (
    "po_no", "contract_no", "product_name_zh", "product_name_en", "quantity",
    "requested_ship_date", "packaging", "units_per_carton", "carton_count",
    "standard", "customer_q", "line_q", "country", "note",
    "manual", "label", "customer_label", "carton_mark", "fabric_label", "date_code",
    "barcode", "parent_product_no", "port", "printing_requirement", "contact",
    "merchandiser", "customer_release_no", "recheck_notice",
)


def uid() -> str:
    return uuid4().hex


def actor_name(user) -> str:
    return f"{user.display_name or user.username} ({user.id})"


def json_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def digest(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def identity_for(row: dict, customer: str) -> str:
    product = str(row.get("product_no") or "").strip().casefold()
    if customer == "edu":
        # EDUHX is allocated from a user's workbook; it is a display reference, not a PO identity.
        contract, po = (str(row.get(key) or "").strip().casefold() for key in ("contract_no", "po_no"))
        if not contract and not po:
            raise HTTPException(400, "EDU 保存订单需要客户合同号或客户 PO，不能仅使用底表续编号")
        return digest(["edu-po", contract, po, product])
    reference = str(row.get("reference_no") or row.get("contract_no") or row.get("po_no") or "").strip().casefold()
    return digest([reference, product])


def number(value, *, optional=False) -> Decimal | None:
    if optional and (value is None or str(value).strip() == ""):
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
        if not result.is_finite() or result <= 0 or result >= Decimal("100000000000000") or result.as_tuple().exponent < -4:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "数量必须大于 0，最多保留 4 位小数，且小于 100 万亿")


def decimal_text(value) -> str:
    return "" if value is None else format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def get_line(db: Session, factory_id: str, line_id: str) -> Line:
    line = db.scalar(select(Line).where(Line.id == line_id, Line.factory_id == factory_id))
    if not line:
        raise HTTPException(404, "当前厂区中没有此订单")
    return line


def lock_line(db: Session, line: Line, expected: int) -> None:
    result = db.execute(update(Line).where(Line.id == line.id, Line.revision == expected).values(
        revision=Line.revision + 1, updated_at=now_text(),
    ), execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        raise HTTPException(409, "订单已被其他操作更新，请刷新后重试")
    db.refresh(line)


def line_out(db: Session, line: Line) -> dict:
    versions = db.scalars(select(Dispatch.version).where(Dispatch.line_id == line.id)).all()
    remaining = None if line.quantity is None else line.quantity - line.shipped_quantity
    return {
        "id": line.id, "factory_id": line.factory_id, "customer_code": line.customer_code,
        "customer_name": line.customer_name, "reference_no": line.reference_no,
        "product_no": line.product_no, "quantity": decimal_text(line.quantity),
        "shipped_quantity": decimal_text(line.shipped_quantity),
        "remaining_quantity": "0" if line.status == "cancelled" else decimal_text(remaining),
        "status": line.status, "version": line.version, "revision": line.revision,
        "dispatch_status": "unsent" if not versions else "sent" if line.version in versions else "changed",
        "data": line.data, "created_at": line.created_at, "updated_at": line.updated_at,
    }


def record_version(db: Session, line: Line, reason: str, actor: str) -> None:
    db.add(Version(id=uid(), line_id=line.id, version=line.version, data={
        **deepcopy(line.data), "status": line.status,
    }, reason=reason, actor=actor, created_at=now_text()))


def dispatch_out(item: Dispatch) -> dict:
    return {key: getattr(item, key) for key in (
        "id", "line_id", "factory_id", "recipient", "version", "snapshot", "actor",
        "created_at", "received_at", "received_by",
    )} | {"status": "received" if item.received_at else "sent"}


def publish(db: Session, line: Line, recipients, actor: str, reason="") -> None:
    for recipient in set(recipients):
        existing = db.scalar(select(Dispatch.id).where(Dispatch.line_id == line.id, Dispatch.version == line.version, Dispatch.recipient == recipient))
        if existing:
            continue
        # Downstream sees an explicit operational whitelist, never a whole PO/price payload.
        snapshot = {key: line.data.get(key, "") for key in PUBLIC_FIELDS}
        snapshot.update(factory_id=line.factory_id, customer_code=line.customer_code,
            customer_name=line.customer_name, reference_no=line.reference_no, product_no=line.product_no,
            quantity=decimal_text(line.quantity), status=line.status, version=line.version, change_reason=reason,
            shipped_quantity=decimal_text(line.shipped_quantity),
            remaining_quantity="0" if line.status == "cancelled" else decimal_text(None if line.quantity is None else line.quantity - line.shipped_quantity),
            history_cutoff_date=line.data.get("history_migration", {}).get("cutoff_date", ""))
        db.add(Dispatch(id=uid(), line_id=line.id, factory_id=line.factory_id, recipient=recipient,
            version=line.version, snapshot=json_copy(snapshot), actor=actor, created_at=now_text(), received_at="", received_by=""))


def _existing_recipients(db: Session, line: Line):
    return db.scalars(select(Dispatch.recipient).where(Dispatch.line_id == line.id).distinct()).all()


def import_preview(db: Session, *, preview: dict, files: list[tuple[str, bytes, str]], source_kind: str,
                   actor: str, reason: str, controls: dict, reconcile_line: Line | None = None, expected_revision: int | None = None) -> dict:
    factory = preview["factory_id"]
    customer = preview["customer_code"]
    details = [row for row in preview["rows"] if row.get("row_role") != "parent"]
    if reconcile_line:
        if len(details) != 1 or reconcile_line.factory_id != factory or reconcile_line.customer_code != customer:
            raise HTTPException(400, "关联已有订单必须是同厂区、同客户的一条订单明细")
        if expected_revision is None or len(reason.strip()) < 4:
            raise HTTPException(400, "请刷新已有订单，并填写至少 4 个字的关联核对原因")
        lock_line(db, reconcile_line, expected_revision)
        if reconcile_line.status != "active":
            raise HTTPException(409, "已取消订单不能关联新的 PO")
    sources = []
    for name, content, kind in files:
        file_hash = sha256(content).hexdigest()
        source = db.scalar(select(Source).where(Source.factory_id == factory, Source.customer_code == customer,
            Source.sha256 == file_hash, Source.kind == kind))
        if source is None:
            source = Source(id=uid(), factory_id=factory, customer_code=customer, sha256=file_hash,
                file_name=name.replace("\\", "/").split("/")[-1][:255], kind=kind, content=content)
            db.add(source)
            db.flush()
        sources.append(source)
    created = 0
    lines = []
    seen = set()
    for row in preview["rows"]:
        if row.get("row_role") == "parent":
            continue
        reference = str(row.get("reference_no") or row.get("contract_no") or row.get("po_no") or "").strip()
        product = str(row.get("product_no") or "").strip()
        if not reference or not product:
            raise HTTPException(400, "保存订单需要订单参考号和产品编号；请先在预览中核对")
        identity = identity_for(row, customer)
        # Keep every public customer extension and original lineage, without parser working objects.
        data = json_copy({key: value for key, value in row.items() if not key.startswith("_")})
        data.update(source_kind=source_kind, import_controls=controls)
        qty = number(row.get("quantity"), optional=True)
        alias = db.get(Identity, (factory, customer, identity))
        line = db.get(Line, alias.line_id) if alias else db.scalar(select(Line).where(Line.factory_id == factory, Line.customer_code == customer, Line.identity_key == identity))
        if reconcile_line:
            if product.casefold() != reconcile_line.product_no.casefold():
                raise HTTPException(409, "正式 PO 货号与已有订单不一致，不能关联")
            if line and line.id != reconcile_line.id:
                raise HTTPException(409, "此 PO 已属于另一条订单，不能合并或覆盖")
            if qty is None or qty < reconcile_line.shipped_quantity:
                raise HTTPException(409, "正式 PO 数量缺失或小于已走货数量")
            line = reconcile_line
            # Historical opening evidence remains authoritative when a later formal PO supplies new fields.
            for key in ("history_migration", "history_fields", "history_review"):
                if key in line.data:
                    data[key] = deepcopy(line.data[key])
            line.reference_no = reference
            line.identity_key = identity
            line.quantity = qty
            line.data = data
            line.version += 1
            record_version(db, line, reason, actor)
            publish(db, line, _existing_recipients(db, line), actor, reason)
        elif line:
            if line.quantity != qty or str(line.data.get("requested_ship_date", "")) != str(data.get("requested_ship_date", "")) or str(line.data.get("po_no", "")) != str(data.get("po_no", "")):
                raise HTTPException(409, f"{reference} / {product} 已存在且订单字段不同，请到台账核对并变更，不能重复建单")
            # A formal PO may have new prices/requirements. Never silently replace the earlier contract.
            changed_fields = [key for key in data if key not in {"id", "status", "status_label", "issues", "lineage", "source_po_file_name", "received_date", "input_template", "target_template", "item_sheet_name", "source_kind", "import_controls"}
                              and not (customer == "edu" and key in {"reference_no", "production_no"})
                              and data.get(key) != line.data.get(key)]
            if changed_fields:
                raise HTTPException(409, f"{reference} / {product} 已有订单的客户字段存在差异，请核对后关联正式 PO：{', '.join(changed_fields[:6])}")
        else:
            line = Line(id=uid(), factory_id=factory, customer_code=customer,
                customer_name=str(preview.get("customer_name") or customer), identity_key=identity,
                reference_no=reference, product_no=product, quantity=qty, shipped_quantity=Decimal(0),
                status="active", version=1, revision=1, data=data, created_at=now_text(), updated_at=now_text())
            db.add(line)
            db.flush()
            record_version(db, line, reason or "核对 PO 后保存订单", actor)
            created += 1
        if alias is None:
            db.add(Identity(factory_id=factory, customer_code=customer, identity_key=identity, line_id=line.id))
        for source in sources:
            if db.get(LineSource, (line.id, source.id)) is None:
                db.add(LineSource(line_id=line.id, source_id=source.id))
        db.flush()
        if line.id not in seen:
            lines.append(line)
            seen.add(line.id)
    if not lines:
        raise HTTPException(400, "当前批次没有可保存的订单明细")
    db.flush()
    return {"items": [line_out(db, line) for line in lines], "created_count": created,
            "existing_count": len(lines) - created, "reconciled_count": 1 if reconcile_line else 0}


def amend(db: Session, line: Line, body, actor: str) -> None:
    lock_line(db, line, body.expected_revision)
    if line.status != "active":
        raise HTTPException(409, "已取消订单不能修改")
    qty = number(body.quantity)
    if qty < line.shipped_quantity:
        raise HTTPException(409, "订单数量不能小于已确认走货数量")
    data = deepcopy(line.data)
    notices = []
    if qty != line.quantity:
        for key in ("carton_count", "cartons", "amount_hkd", "amount_usd", "amount", "total_amount", "total_cartons"):
            if key in data:
                data[key] = ""
        notices.append("数量已调整，原箱数、金额等派生数据已清空，请按新 PO 核对。")
    if body.requested_ship_date != str(data.get("requested_ship_date") or ""):
        for key in ("line_q", "customer_q", "date_code", "inspection_date", "planned_inspection_date", "fcd_date"):
            if key in data:
                data[key] = ""
        notices.append("交期已调整，相关验货日期、FCD 和日期码已清空待复核；请以客户资料重新核对。")
    if notices:
        data["recheck_notice"] = " ".join(dict.fromkeys([str(data.get("recheck_notice") or ""), *notices])).strip()
    data.setdefault("lineage", {}).update(quantity=f"订单台账人工变更 · {actor} · {body.reason}", requested_ship_date=f"订单台账人工变更 · {actor} · {body.reason}")
    line.quantity = qty
    line.data = {**data, "quantity": decimal_text(qty), "requested_ship_date": body.requested_ship_date, "note": body.note}
    line.version += 1
    record_version(db, line, body.reason, actor)
    publish(db, line, _existing_recipients(db, line), actor, body.reason)
    db.flush()


def cancel(db: Session, line: Line, body, actor: str) -> None:
    lock_line(db, line, body.expected_revision)
    if line.status == "cancelled":
        raise HTTPException(409, "订单已经取消")
    line.status = "cancelled"
    line.version += 1
    record_version(db, line, body.reason, actor)
    publish(db, line, _existing_recipients(db, line), actor, body.reason)
    db.flush()


def dispatch(db: Session, line: Line, body, actor: str) -> None:
    lock_line(db, line, body.expected_revision)
    if line.status != "active":
        raise HTTPException(409, "已取消订单不能新发送")
    if line.quantity is None or line.quantity <= 0 or not line.data.get("requested_ship_date"):
        raise HTTPException(400, "发送订单前请补齐有效数量和走货期")
    publish(db, line, body.recipients, actor)
    db.flush()


def ship(db: Session, line: Line, body, actor: str) -> None:
    qty = number(body.quantity)
    request_hash = digest([line.id, decimal_text(qty), body.ship_date.isoformat(), body.document_no, body.note])
    existing = db.scalar(select(Shipment).where(Shipment.factory_id == line.factory_id, Shipment.idempotency_key == body.idempotency_key))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "本次提交标识已用于不同的走货内容，请重新核对")
        return
    lock_line(db, line, body.expected_revision)
    if line.status != "active":
        raise HTTPException(409, "已取消订单不能确认新的走货")
    if body.ship_date > datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise HTTPException(400, "实际走货日期不能晚于今天")
    cutoff = line.data.get("history_migration", {}).get("cutoff_date")
    if cutoff and body.ship_date.isoformat() <= cutoff:
        raise HTTPException(400, "该日期已包含在历史期初范围内，请更正期初数量，不能重复登记走货")
    if line.quantity is None or line.shipped_quantity + qty > line.quantity:
        raise HTTPException(409, "走货数量超过订单剩余数量，请核对订单或出货单")
    # A reused document for this line must be corrected through reversal, not double-posted.
    same_document = db.scalar(select(Shipment.id).where(Shipment.line_id == line.id,
        Shipment.document_no == body.document_no, ~Shipment.id.in_(select(Reversal.shipment_id))))
    if same_document:
        raise HTTPException(409, "此订单明细已有相同出货单号，请核对或先更正原走货记录")
    line.shipped_quantity += qty
    db.add(Shipment(id=uid(), line_id=line.id, factory_id=line.factory_id, idempotency_key=body.idempotency_key,
        request_hash=request_hash, quantity=qty, ship_date=body.ship_date.isoformat(), document_no=body.document_no,
        note=body.note, actor=actor, created_at=now_text()))
    db.flush()


def reverse_shipment(db: Session, line: Line, shipment: Shipment, body, actor: str) -> None:
    if db.get(Reversal, shipment.id):
        return
    lock_line(db, line, body.expected_revision)
    line.shipped_quantity -= shipment.quantity
    db.add(Reversal(shipment_id=shipment.id, reason=body.reason, actor=actor, created_at=now_text()))
    db.flush()


def detail(db: Session, line: Line) -> dict:
    versions = db.scalars(select(Version).where(Version.line_id == line.id).order_by(Version.version.desc())).all()
    dispatches = db.scalars(select(Dispatch).where(Dispatch.line_id == line.id).order_by(Dispatch.created_at.desc())).all()
    shipments = db.scalars(select(Shipment).where(Shipment.line_id == line.id).order_by(Shipment.created_at.desc())).all()
    sources = db.scalars(select(Source).join(LineSource).where(LineSource.line_id == line.id)).all()
    reversals = {item.shipment_id: item for item in db.scalars(select(Reversal).join(Shipment).where(Shipment.line_id == line.id)).all()}
    return {
        "line": line_out(db, line),
        "versions": [{key: getattr(item, key) for key in ("version", "data", "reason", "actor", "created_at")} for item in versions],
        "dispatches": [dispatch_out(item) for item in dispatches],
        "shipments": [{**{key: getattr(item, key) for key in ("id", "ship_date", "document_no", "note", "actor", "created_at")},
            "quantity": decimal_text(item.quantity), "reversed": item.id in reversals,
            "reversal_reason": reversals[item.id].reason if item.id in reversals else "",
            "reversal_actor": reversals[item.id].actor if item.id in reversals else "",
            "reversal_at": reversals[item.id].created_at if item.id in reversals else "",
        } for item in shipments],
        "sources": [{"id": item.id, "file_name": item.file_name, "kind": item.kind} for item in sources],
    }
