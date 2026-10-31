"""Sales schedule handoff; creates schedule evidence, never purchase orders."""
from hashlib import sha256
from io import BytesIO
import json
import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.models.carton_procurement import CartonCustomer, CartonAuditEvent
from app.services import carton_procurement as carton, carton_schedule_coverage as coverage
from app.services.business_authz import ensure_permission_for_departments, has_permission_for_departments
from app.services.customer_order_jobs import run_order_job, order_request_started_at

logger = logging.getLogger(__name__)


class AlreadySynchronized(Exception):
    def __init__(self, batch_id):
        self.batch_id = batch_id


def authorize_sales(db, user, factory):
    # Normal sales PO operators may export without maintaining the order ledger.
    # Neither authority grants general warehouse import/order permissions.
    departments = ("sales-business",)
    permission = next((code for code in ("customer_order:write", "customer_order:export")
        if has_permission_for_departments(user, code, factory, departments)), "customer_order:write")
    ensure_permission_for_departments(db, user, permission, factory, departments)


def resolve_customer(db, factory, code, name):
    """Only exact same-factory codes/names; conflicting matches require repair."""
    key = lambda value: " ".join(value.split()).casefold()
    matches = [row for row in db.scalars(select(CartonCustomer).where(
        CartonCustomer.factory_id == factory, CartonCustomer.status == "ACTIVE"))
        if key(row.customer_code) == key(code) or key(row.customer_name) == key(name)]
    if len(matches) != 1:
        raise HTTPException(422, "纸箱仓库客户未建立或对应不唯一，请由纸箱主管核对同厂区客户资料后重试同步")
    return matches[0]


def parse_business_schedule(filename, content):
    # Decryption, Excel expansion and parsing stay inside the bounded worker.
    from app.services.customer_order_buzzbee import _decrypt_schedule
    from app.services.carton_procurement_imports import parse_carton_file
    if Path(filename).suffix.lower() == ".xlsx":
        content, _ = _decrypt_schedule(content)
    parsed = parse_carton_file("WEEKLY_SCHEDULE", filename, content)
    rows = parsed.get("rows", [])
    if not rows or any(row.get("template") != "unified-item" for row in rows):
        raise ValueError("自动同步需要可识别合同、货号的统一 ITEM 排期；请使用业务统一排期文件")
    return parsed


async def synchronize(db, user, factory, customer_code, customer_name, filename, content, source_kind, refresh_actor):
    received_at = order_request_started_at()
    factory = carton.require_carton_factory(factory)
    authorize_sales(db, user, factory)
    resolve_customer(db, factory, customer_code, customer_name)
    parsed = await run_order_job(parse_business_schedule, filename, content, db=db)
    from app.services.carton_procurement_imports import SCHEDULE_IMPORT_PARSER_VERSION
    semantic_sha256 = sha256(json.dumps([SCHEDULE_IMPORT_PARSER_VERSION, parsed],
        ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    parsed["business_source"] = dict(system="CUSTOMER_ORDER_CENTER", customer_code=customer_code,
        source_kind=source_kind, received_at=received_at, semantic_sha256=semantic_sha256)
    profile = {}

    def authorize(db, original, locked_factory, _):
        from app.services.carton_special_requests import locked_actor
        locked_actor(db, original, locked_factory)
        actor = refresh_actor()  # Original session, current identity and explicit denies under lock.
        authorize_sales(db, actor, locked_factory)
        customer = resolve_customer(db, locked_factory, customer_code, customer_name)
        # Choose the warehouse master again under the factory lock, after CPU work.
        profile.update(customer_code=customer.customer_code, source_system="CUSTOMER_ORDER_CENTER",
            business_customer_code=customer_code)
        active = [entry for entry in coverage.batches(db, locked_factory)
            if entry["batch"].status != "REJECTED" and coverage.customer_of(entry["summary"]) == customer.customer_code]
        same = [entry for entry in active if entry["summary"].get("business_source", {}).get("semantic_sha256") == semantic_sha256]
        if same:
            if same[0]["batch"].id != active[0]["batch"].id:
                raise HTTPException(409, "这份排期之后已有更新版本，已保留仓库当前排期；请核对最新排期后重试")
            # A later identical request still establishes the latest accepted
            # source intent. Retain an append-only watermark so an older slow
            # request cannot overwrite it after its duplicate response succeeds.
            carton._audit(db, actor, locked_factory, "BUSINESS_SCHEDULE_SYNCED", "carton_import_batch",
                same[0]["batch"].id, dict(customer_code=customer.customer_code, received_at=received_at,
                    semantic_sha256=semantic_sha256))
            raise AlreadySynchronized(same[0]["batch"].id)
        accepted_times = [entry["summary"].get("business_source", {}).get("received_at", "") for entry in active]
        active_ids = [entry["batch"].id for entry in active]
        if active_ids:
            for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == locked_factory,
                CartonAuditEvent.event_type == "BUSINESS_SCHEDULE_SYNCED",
                CartonAuditEvent.entity_type == "carton_import_batch", CartonAuditEvent.entity_id.in_(active_ids))):
                detail = json.loads(event.detail_json)
                if detail.get("customer_code") == customer.customer_code:
                    accepted_times.append(detail.get("received_at", ""))
        if any(stamp > received_at for stamp in accepted_times):
            raise HTTPException(409, "已有更新的业务排期同步完成，本次旧请求未覆盖仓库排期")
        # No full-scope claim is made by a normal business upload. Existing full
        # declarations remain authoritative; absence never cancels purchases.
        if any(entry["summary"].get("schedule_coverage") for entry in active):
            profile.update(scope_mode="INCREMENTAL", as_of_date=carton.business_today())
        return actor

    try:
        batch = carton.create_import_batch(db, factory, "WEEKLY_SCHEDULE",
            UploadFile(file=BytesIO(content), filename=filename), content, user,
            import_profile=profile, parsed_source=parsed, authorize_import=authorize)
    except AlreadySynchronized as existing:
        db.commit()
        return dict(batch_id=existing.batch_id, duplicate=True, message="这份排期已同步，无需重复导入")
    except BaseException:
        db.rollback()
        raise
    return dict(batch_id=batch.id, duplicate=batch.duplicate,
        message="排期已自动同步到纸箱仓库" if not batch.duplicate else "这份排期已同步，无需重复导入")


async def sync_report(db, user, request, preview, filename, content, source_kind):
    """Await the handoff before success; a failed handoff never hides the export."""
    from app.api.customer_order import CUSTOMER_NAMES
    from app.services.auth import get_current_user
    try:
        result = await synchronize(db, user, preview["factory_id"], preview["customer_code"],
            CUSTOMER_NAMES[preview["customer_code"]], filename, content, source_kind,
            refresh_actor=lambda: get_current_user(request, db))
        return {"status": "SUCCESS", **result}
    except HTTPException as error:
        db.rollback()
        return {"status": "ERROR", "message": str(error.detail)}
    except Exception:
        db.rollback()
        logger.exception("Business schedule handoff failed")
        return {"status": "ERROR", "message": "仓库同步暂未完成，请稍后重试同步"}
