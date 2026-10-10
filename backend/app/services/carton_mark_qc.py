"""Factory-scoped QC evidence. Originals and events are append-only."""
import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.carton_mark import CartonMarkDocument, CartonMarkTemplate, CartonMarkQcRecord, CartonMarkQcPhoto, CartonMarkQcEvent
from app.models.carton_procurement import CartonAuditEvent
from app.schemas.carton_mark import CartonMarkAutoCheckResponse
from app.schemas.carton_mark_qc import QcRecordOut, QcPhotoOut, QcEventOut, QcAction
from app.services.auth import authorization_decision
from app.services.carton_mark import build_carton_mark_auto_check, build_carton_mark_batch_auto_check
from app.services.carton_mark_library import CARTON_MARK_READ_DEPARTMENTS, _now_text
from app.services.carton_procurement import require_carton_factory

logger = logging.getLogger(__name__)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def scope(user, factory, permission="carton_mark:read"):
    factory = require_carton_factory(factory)
    departments = CARTON_MARK_READ_DEPARTMENTS if permission == "carton_mark:read" else ("qc", "qa")
    if not any(authorization_decision(user, permission, factory, department)[0] for department in departments):
        raise HTTPException(403, "没有当前厂区箱唛 QC 操作权限")
    return factory


@dataclass(frozen=True)
class PhotoInput:
    side: str
    name: str
    content: bytes
    content_type: str


def record(db, factory, identifier):
    value = db.scalar(select(CartonMarkQcRecord).where(CartonMarkQcRecord.id == identifier, CartonMarkQcRecord.factory_id == factory))
    if value is None:
        raise HTTPException(404, "未找到当前厂区 QC 留档")
    return value


def events(db, identifier):
    return list(db.scalars(select(CartonMarkQcEvent).where(CartonMarkQcEvent.record_id == identifier).order_by(CartonMarkQcEvent.revision)))


def photos(db, identifier):
    return list(db.scalars(select(CartonMarkQcPhoto).where(CartonMarkQcPhoto.record_id == identifier).order_by(CartonMarkQcPhoto.side)))


def output(db, value):
    history = events(db, value.id)
    latest = history[-1]
    return QcRecordOut(id=value.id, factory_id=value.factory_id, template_id=value.template_id,
        template_version=value.template_version, template_snapshot=json.loads(value.template_snapshot_json),
        customer_name=value.customer_name, po=value.po, item=value.item, contract_number=value.contract_number,
        corrects_record_id=value.corrects_record_id, note=value.note, created_by_name=value.created_by_name,
        created_at=value.created_at, revision=latest.revision, status=latest.status,
        photos=[QcPhotoOut(id=p.id, side=p.side, file_name=p.file_name, size_bytes=p.size_bytes, sha256=p.sha256) for p in photos(db, value.id)],
        events=[QcEventOut(revision=e.revision, kind=e.kind, status=e.status,
            result=CartonMarkAutoCheckResponse.model_validate_json(e.result_json) if e.result_json else None,
            error=e.error, note=e.note, actor_name=e.actor_name, created_at=e.created_at) for e in history])


def list_records(db, factory, limit, offset, contract, item):
    query = select(CartonMarkQcRecord).where(CartonMarkQcRecord.factory_id == factory)
    if contract:
        query = query.where(CartonMarkQcRecord.contract_number == contract)
    if item:
        query = query.where(CartonMarkQcRecord.item == item)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    values = db.scalars(query.order_by(CartonMarkQcRecord.created_at.desc(), CartonMarkQcRecord.id).offset(offset).limit(limit))
    return dict(items=[output(db, v) for v in values], total=total, limit=limit, offset=offset)


def template_source(db, factory, identifier, ready=True):
    template = db.scalar(select(CartonMarkTemplate).where(CartonMarkTemplate.id == identifier, CartonMarkTemplate.factory_id == factory))
    if template is None:
        raise HTTPException(404, "未找到本厂箱唛资料版本")
    if ready and (template.is_archived or not (template.check_status == "核对通过" or template.manual_released_at)):
        raise HTTPException(409, "资料尚未确认或已归档，请重新选择 QC 可用版本")
    doc = db.scalar(select(CartonMarkDocument).where(CartonMarkDocument.template_id == identifier,
        CartonMarkDocument.factory_id == factory, CartonMarkDocument.kind == "print_pdf"))
    if doc is None or digest(doc.content) != template.pdf_sha256 or doc.sha256 != template.pdf_sha256:
        raise HTTPException(409, "资料原件完整性校验失败，请联系管理员")
    snapshot = {key: getattr(template, key) for key in ("id", "version", "customer_name", "po", "item", "contract_number",
        "business_key_sha256", "pdf_sha256", "check_status", "manual_release_reason", "manual_released_by_name", "manual_released_at")}
    snapshot["pdf_file_name"] = doc.file_name
    review = json.loads(template.check_result_json)
    snapshot.update({key: review.get(key, default) for key, default in (
        ("review_method", "excel_pdf"), ("review_note", ""), ("source_assets", []), ("confirmed_checks", []))})
    return snapshot, bytes(doc.content), doc.file_name


def original_pdf(db, value):
    _, content, name = template_source(db, value.factory_id, value.template_id, ready=False)
    if digest(content) != value.pdf_sha256:
        raise HTTPException(409, "历史资料原件完整性校验失败")
    return content, name


def submission_hash(template_id, mode, note, parent, inputs):
    return digest(json_text([template_id, mode, note, parent,
        [(p.side, p.name, digest(p.content)) for p in inputs]]).encode())


def replay(db, user, factory, request_id, request_hash):
    values = list(db.scalars(select(CartonMarkQcRecord).where(CartonMarkQcRecord.factory_id == factory,
        CartonMarkQcRecord.created_by == user.id, CartonMarkQcRecord.request_id == request_id).order_by(CartonMarkQcRecord.slot)))
    if values and any(v.request_hash != request_hash for v in values):
        raise HTTPException(409, "提交编号已用于其他内容，请刷新后重新提交")
    return [output(db, v) for v in values] if values else None


def validate_correction(db, factory, parent_id, snapshot, note):
    if not parent_id:
        return
    parent = record(db, factory, parent_id)
    if events(db, parent.id)[-1].status != "发现异常":
        raise HTTPException(409, "仅异常记录可提交整改照片")
    if json.loads(parent.template_snapshot_json)["business_key_sha256"] != snapshot["business_key_sha256"]:
        raise HTTPException(422, "整改照片必须属于原记录的客户、合同及货号")
    if len(note.strip()) < 5:
        raise HTTPException(422, "请填写至少 5 字的整改说明")


def compute(pdf, snapshot, inputs, mode):
    """Use the existing algorithm, always leave its result for human review."""
    if manual_images(snapshot):
        return [(None, "") for _ in (inputs if mode == "batch" else [None])]
    try:
        metadata = dict(customer_name=snapshot["customer_name"], po=snapshot["po"], item=snapshot["item"])
        if mode == "batch" or len(inputs) == 1:
            result = build_carton_mark_batch_auto_check(pdf_bytes=pdf,
                front_images=[(p.name, p.content) for p in inputs if p.side == "front"],
                side_images=[(p.name, p.content) for p in inputs if p.side == "side"], **metadata)
            # Batch algorithm reports front images then side images, preserving indices.
            return [(entry.result.model_dump(), "") for entry in result.items]
        result = build_carton_mark_auto_check(pdf_bytes=pdf,
            front_image_bytes=next((p.content for p in inputs if p.side == "front"), None),
            side_image_bytes=next((p.content for p in inputs if p.side == "side"), None), **metadata)
        return [(result.model_dump(), "")]
    except Exception:
        logger.exception("QC automatic check failed; original photos will be retained for manual review")
        return [(None, "自动核对未完成，原照片已留档，请人工检查或重新自动核对") for _ in (inputs if mode == "batch" else [None])]


def manual_images(snapshot):
    sources = snapshot.get("source_assets", [])
    return snapshot.get("review_method") == "manual_sources" and bool(sources) and all(row.get("kind") == "image" for row in sources)


def append_event(db, user, value, revision, kind, status, request_id, request_hash, result=None, error="", note=""):
    event = CartonMarkQcEvent(id=f"CMQE-{uuid4().hex}", record_id=value.id, factory_id=value.factory_id,
        revision=revision, kind=kind, status=status, result_json=json_text(result) if result else "",
        error=error, note=note, actor_id=user.id, actor_name=user.display_name, created_at=_now_text(),
        request_id=request_id, request_hash=request_hash)
    db.add(event)
    db.add(CartonAuditEvent(id=f"CAE-{uuid4().hex}", factory_id=value.factory_id, event_type=f"CARTON_MARK_QC_{kind}",
        entity_type="carton_mark_qc_record", entity_id=value.id, detail_json=json_text({"revision": revision,
        "template_id": value.template_id, "template_version": value.template_version, "status": status}),
        actor_user_id=user.id, actor_name=user.display_name, created_at=event.created_at))


def persist_submission(db, user, factory, template_id, request_id, request_hash, mode, note, parent, inputs, snapshot, results):
    values = []
    groups = [[p] for p in inputs] if mode == "batch" else [inputs]
    if len(groups) != len(results):
        raise HTTPException(500, "自动核对结果数量不一致，未保存留档")
    for slot, group in enumerate(groups):
        value = CartonMarkQcRecord(id=f"CMQ-{uuid4().hex}", factory_id=factory, template_id=template_id,
            template_version=snapshot["version"], template_snapshot_json=json_text(snapshot),
            customer_name=snapshot["customer_name"], po=snapshot["po"], item=snapshot["item"], contract_number=snapshot["contract_number"],
            pdf_sha256=snapshot["pdf_sha256"], request_id=request_id, request_hash=request_hash, slot=slot,
            corrects_record_id=parent, note=note, created_by=user.id, created_by_name=user.display_name, created_at=_now_text())
        db.add(value)
        db.flush()
        for p in group:
            db.add(CartonMarkQcPhoto(id=f"CMQP-{uuid4().hex}", record_id=value.id, factory_id=factory, side=p.side,
                file_name=p.name, content_type=p.content_type, size_bytes=len(p.content), sha256=digest(p.content), content=p.content))
        append_event(db, user, value, 1, "REVIEW" if manual_images(snapshot) else "AUTO_CHECK", "待复核", request_id, request_hash, *results[slot], note=note)
        values.append(value)
    db.commit()
    return [output(db, v) for v in values]


def action_replay(db, user, value, payload):
    request_hash = digest(json_text(payload.model_dump(exclude={"request_id"})).encode())
    existing = db.scalar(select(CartonMarkQcEvent).where(CartonMarkQcEvent.record_id == value.id,
        CartonMarkQcEvent.actor_id == user.id, CartonMarkQcEvent.request_id == payload.request_id))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "操作编号已用于其他内容")
        return request_hash, output(db, value)
    latest = events(db, value.id)[-1]
    if latest.revision != payload.expected_revision or latest.status == "已作废":
        raise HTTPException(409, "记录已变化或已作废，请刷新后复核")
    if payload.action in {"发现异常", "作废"} and len(payload.note.strip()) < 5:
        raise HTTPException(422, "请填写至少 5 字的异常或作废原因")
    return request_hash, None
