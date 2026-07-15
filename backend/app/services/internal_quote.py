from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteAuditLog,
    InternalQuoteExportFile,
    InternalQuoteSection,
)
from app.schemas.internal_quote import (
    InternalQuoteAuditOut,
    InternalQuoteCreateRequest,
    InternalQuoteDetailOut,
    InternalQuoteReviewRequest,
    InternalQuoteSectionCalculationOut,
    InternalQuoteSectionOut,
    InternalQuoteSectionPayload,
    InternalQuoteSectionUpdateRequest,
    InternalQuoteSummaryOut,
    InternalQuoteWorkshopOut,
)
from app.services.auth import AuthContext, add_auth_audit
from app.services.internal_quote_calculator import (
    calculate_section,
    default_reference_snapshot,
    money,
)


WORKSHOPS_BY_FACTORY: dict[str, tuple[tuple[str, str], ...]] = {
    "huaxing": (("huaxing-workshop", "华兴"),),
    "huakang-a": (("a-workshop", "A车间"),),
    "huakang-b": (("b-workshop", "B车间"),),
    "huadeng": (("huadeng-workshop", "华登车间"),),
}

INTERNAL_QUOTE_DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("sales", "业务部"),
    ("engineering", "工程部"),
    ("electronic", "电子部"),
    ("molding", "啤机部"),
    ("painting", "喷油部"),
    ("slush", "搪胶"),
    ("sewing", "车缝"),
    ("assembly", "装配部"),
)

DEFAULT_SECTION_ROWS: dict[str, tuple[tuple[str, str], ...]] = {
    "sales": (("业务费用", "运输及杂项"),),
    "engineering": (("模具", "模具分摊"), ("包装", "包装材料")),
    "electronic": (("电子料", "电子零件"),),
    "molding": (("注塑", "原料及啤价"), ("吹气", "吹气加工")),
    "painting": (("二次加工", "喷油/移印"),),
    "slush": (("搪胶", "搪胶加工"),),
    "sewing": (("车缝", "物料及人工"),),
    "assembly": (("装配", "组装/包装人工"),),
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def list_workshops(factory_id: str) -> list[InternalQuoteWorkshopOut]:
    rows = WORKSHOPS_BY_FACTORY.get(factory_id)
    if rows is None:
        raise HTTPException(status_code=400, detail="该厂区尚未配置内部报价车间")
    return [InternalQuoteWorkshopOut(code=code, name=name) for code, name in rows]


def workshop_name(factory_id: str, workshop_code: str) -> str:
    for code, name in WORKSHOPS_BY_FACTORY.get(factory_id, ()):  # pragma: no branch - tiny catalog
        if code == workshop_code:
            return name
    raise HTTPException(status_code=400, detail="所选车间不属于当前厂区")


def default_payload(department: str) -> InternalQuoteSectionPayload:
    rows = [
        {
            "id": f"line-{uuid4().hex[:10]}",
            "category": category,
            "item_name": item_name,
            "specification": "",
            "quantity": 0,
            "unit_price_hkd": 0,
            "amount_hkd": 0,
            "note": "",
            "fields": default_line_fields(department, category),
        }
        for category, item_name in DEFAULT_SECTION_ROWS.get(department, ())
    ]
    parameters: dict[str, float] = {}
    if department == "electronic":
        parameters = {
            "bonding_cost_rmb": 0,
            "smt_cost_rmb": 0,
            "labor_cost_rmb": 0,
            "test_repair_rmb": 0,
            "packing_shipping_rmb": 0,
            "profit_pct": 0,
            "tax_diff_rmb": 0,
        }
    elif department == "sewing":
        parameters = {"labor_hkd": 0}
    return InternalQuoteSectionPayload(
        rows=rows,
        parameters=parameters,
        reference_snapshot=default_reference_snapshot(),
    )


def default_line_fields(department: str, category: str) -> dict[str, float | str]:
    if department == "engineering" and category == "模具":
        return {"mode": "mold", "mold_price_rmb": 0, "amortization_qty": 1}
    if department == "electronic":
        return {"unit_price_rmb": 0}
    if department == "molding" and category == "注塑":
        return {
            "mode": "injection", "material": "", "material_grade": "",
            "weight_g": 0, "loss_pct": 3, "material_price_hkd_lb": 0,
            "machine_model": "", "shot_price_hkd": 0, "sets": 1, "target": 1,
        }
    if department == "molding" and category == "吹气":
        return {
            "mode": "blow", "weight_g": 0, "material_price_hkd_lb": 0,
            "blow_labor_hkd": 0, "flash_hkd": 0, "profit_multiplier": 1,
        }
    if department in {"painting", "slush"}:
        return {"mode": "operation"}
    if department == "sewing":
        return {"usage": 0, "material_price_hkd": 0, "markup": 1}
    if department == "assembly":
        return {
            "mode": "process", "base_rate_hkd": 310, "people_count": 0,
            "team_count": 1, "production_qty": 1,
        }
    return {}


def parse_payload(raw: str) -> InternalQuoteSectionPayload:
    try:
        return InternalQuoteSectionPayload.model_validate_json(raw or "{}")
    except ValueError:
        return InternalQuoteSectionPayload()


def parse_calculation(
    raw: str,
    payload: InternalQuoteSectionPayload,
    department: str,
) -> InternalQuoteSectionCalculationOut:
    try:
        return InternalQuoteSectionCalculationOut.model_validate_json(raw or "{}")
    except ValueError:
        return calculate_section(department, payload)[1]


def add_quote_audit(
    db: Session,
    quote_id: str,
    current_user: AuthContext,
    action: str,
    *,
    department: str = "",
    detail: str = "",
) -> None:
    db.add(
        InternalQuoteAuditLog(
            id=f"IQA-{uuid4().hex[:18].upper()}",
            quote_id=quote_id,
            department=department,
            actor_id=current_user.id,
            actor_name=current_user.display_name or current_user.username,
            action=action,
            detail=detail,
            created_at=now_text(),
        )
    )


def section_to_out(section: InternalQuoteSection) -> InternalQuoteSectionOut:
    payload = parse_payload(section.payload_json)
    calculation = parse_calculation(section.calculation_json, payload, section.department)
    return InternalQuoteSectionOut(
        id=section.id,
        quote_id=section.quote_id,
        department=section.department,
        department_name=section.department_name,
        status=section.status,
        payload=payload,
        calculation=calculation,
        revision=section.revision,
        filled_by=section.filled_by,
        filled_at=section.filled_at,
        submitted_by=section.submitted_by,
        submitted_at=section.submitted_at,
        reviewed_by=section.reviewed_by,
        reviewed_at=section.reviewed_at,
        review_comment=section.review_comment,
        updated_at=section.updated_at,
    )


def audit_to_out(row: InternalQuoteAuditLog) -> InternalQuoteAuditOut:
    return InternalQuoteAuditOut(
        id=row.id,
        quote_id=row.quote_id,
        department=row.department,
        actor_id=row.actor_id,
        actor_name=row.actor_name,
        action=row.action,
        detail=row.detail,
        created_at=row.created_at,
    )


def quote_sections(db: Session, quote_id: str) -> list[InternalQuoteSection]:
    department_order = {code: index for index, (code, _) in enumerate(INTERNAL_QUOTE_DEPARTMENTS)}
    sections = list(db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote_id)
    ).all())
    return sorted(sections, key=lambda item: department_order.get(item.department, 999))


def quote_summary(db: Session, quote: InternalQuote) -> InternalQuoteSummaryOut:
    sections = quote_sections(db, quote.id)
    outputs = [section_to_out(section) for section in sections]
    return InternalQuoteSummaryOut(
        id=quote.id,
        factory_id=quote.factory_id,
        workshop_code=quote.workshop_code,
        workshop_name=quote.workshop_name,
        quote_no=quote.quote_no,
        product_name=quote.product_name,
        customer=quote.customer,
        qty=quote.qty,
        version_label=quote.version_label,
        status=quote.status,
        approved_count=sum(1 for section in sections if section.status == "approved"),
        total_sections=len(sections),
        total_hkd=money(sum(section.calculation.total_hkd for section in outputs)),
        created_by=quote.created_by,
        created_by_name=quote.created_by_name,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def get_quote_or_404(db: Session, quote_id: str) -> InternalQuote:
    quote = db.get(InternalQuote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="内部报价单不存在")
    return quote


def create_quote(
    db: Session,
    payload: InternalQuoteCreateRequest,
    current_user: AuthContext,
) -> InternalQuoteDetailOut:
    now = now_text()
    quote = InternalQuote(
        id=f"IQD-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
        factory_id=payload.factory_id,
        workshop_code=payload.workshop_code,
        workshop_name=workshop_name(payload.factory_id, payload.workshop_code),
        quote_no=payload.quote_no,
        product_name=payload.product_name,
        customer=payload.customer,
        qty=payload.qty,
        version_label=payload.version_label,
        status="drafting",
        created_by=current_user.id,
        created_by_name=current_user.display_name or current_user.username,
        created_at=now,
        updated_at=now,
    )
    db.add(quote)
    for department, department_name in INTERNAL_QUOTE_DEPARTMENTS:
        normalized_payload, calculation = calculate_section(department, default_payload(department))
        db.add(
            InternalQuoteSection(
                id=f"IQS-{uuid4().hex[:20].upper()}",
                quote_id=quote.id,
                department=department,
                department_name=department_name,
                status="draft",
                payload_json=normalized_payload.model_dump_json(),
                calculation_json=calculation.model_dump_json(),
                revision=1,
                updated_at=now,
            )
        )
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "create",
        department="sales",
        detail=f"{quote.workshop_name} · {quote.quote_no} · {quote.version_label}",
    )
    add_auth_audit(
        db,
        "internal_quote_created",
        username=current_user.username,
        user_id=current_user.id,
        detail=f"厂区={quote.factory_id};车间={quote.workshop_name};报价={quote.id}",
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该车间的报价单号和版本已存在") from None
    return get_quote_detail(db, quote.id)


def list_quotes(
    db: Session,
    factory_id: str,
    *,
    workshop_code: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
) -> list[InternalQuoteSummaryOut]:
    statement = select(InternalQuote).where(InternalQuote.factory_id == factory_id)
    if workshop_code:
        workshop_name(factory_id, workshop_code)
        statement = statement.where(InternalQuote.workshop_code == workshop_code)
    if status:
        statement = statement.where(InternalQuote.status == status)
    if keyword:
        token = f"%{keyword.strip()}%"
        statement = statement.where(
            InternalQuote.quote_no.ilike(token)
            | InternalQuote.product_name.ilike(token)
            | InternalQuote.customer.ilike(token)
        )
    statement = statement.order_by(InternalQuote.updated_at.desc(), InternalQuote.created_at.desc())
    return [quote_summary(db, quote) for quote in db.scalars(statement).all()]


def get_quote_detail(db: Session, quote_id: str) -> InternalQuoteDetailOut:
    quote = get_quote_or_404(db, quote_id)
    summary = quote_summary(db, quote)
    sections = [section_to_out(section) for section in quote_sections(db, quote.id)]
    audit_logs = [
        audit_to_out(row)
        for row in db.scalars(
            select(InternalQuoteAuditLog)
            .where(InternalQuoteAuditLog.quote_id == quote.id)
            .order_by(InternalQuoteAuditLog.created_at.desc(), InternalQuoteAuditLog.id.desc())
        ).all()
    ]
    return InternalQuoteDetailOut(**summary.model_dump(), sections=sections, audit_logs=audit_logs)


def update_quote_status_from_sections(db: Session, quote: InternalQuote) -> None:
    sections = quote_sections(db, quote.id)
    if sections and all(section.status == "approved" for section in sections):
        quote.status = "fully_approved"
    elif quote.status in {"fully_approved", "exported"}:
        quote.status = "reopened"
    else:
        quote.status = "drafting"
    quote.updated_at = now_text()


def update_section(
    db: Session,
    quote: InternalQuote,
    department: str,
    payload: InternalQuoteSectionUpdateRequest,
    current_user: AuthContext,
) -> InternalQuoteDetailOut:
    section = db.scalar(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department == department,
        )
    )
    if section is None:
        raise HTTPException(status_code=404, detail="报价分段不存在")
    if section.revision != payload.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "报价分段已被其他人更新，请刷新后重试",
                "current_revision": section.revision,
                "updated_at": section.updated_at,
                "filled_by": section.filled_by,
            },
        )
    if section.status == "approved":
        raise HTTPException(status_code=409, detail="该分段已审核通过，请先由主管重开")
    if section.status == "pending_review":
        raise HTTPException(status_code=409, detail="该分段正在审核中，不能修改")

    stored_payload = parse_payload(section.payload_json)
    authoritative_payload = payload.payload.model_copy(update={
        "reference_snapshot": stored_payload.reference_snapshot or default_reference_snapshot(),
    })
    normalized_payload, calculation = calculate_section(department, authoritative_payload)
    now = now_text()
    actor_name = current_user.display_name or current_user.username
    section.payload_json = normalized_payload.model_dump_json()
    section.calculation_json = calculation.model_dump_json()
    section.revision += 1
    section.filled_by = actor_name
    section.filled_at = now
    section.updated_at = now
    if payload.submit:
        section.status = "pending_review"
        section.submitted_by = actor_name
        section.submitted_by_id = current_user.id
        section.submitted_at = now
        section.review_comment = ""
        action = "submit"
    else:
        section.status = "draft"
        action = "save_draft"

    update_quote_status_from_sections(db, quote)
    add_quote_audit(
        db,
        quote.id,
        current_user,
        action,
        department=department,
        detail=f"版本 {section.revision} · HK${calculation.total_hkd:.2f}",
    )
    db.commit()
    return get_quote_detail(db, quote.id)


def review_section(
    db: Session,
    quote: InternalQuote,
    department: str,
    payload: InternalQuoteReviewRequest,
    current_user: AuthContext,
) -> InternalQuoteDetailOut:
    section = db.scalar(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department == department,
        )
    )
    if section is None:
        raise HTTPException(status_code=404, detail="报价分段不存在")
    if payload.action in {"reject", "reopen"} and not payload.comment:
        raise HTTPException(status_code=400, detail="退回或重开必须填写原因")
    if payload.action in {"approve", "reject"} and section.status != "pending_review":
        raise HTTPException(status_code=409, detail="只有待审核分段可以审批")
    if payload.action in {"approve", "reject"} and section.submitted_by_id == current_user.id:
        raise HTTPException(status_code=409, detail="提交人与审核人不能为同一账号")
    if payload.action == "reopen" and section.status != "approved":
        raise HTTPException(status_code=409, detail="只有已通过分段可以重开")

    now = now_text()
    actor_name = current_user.display_name or current_user.username
    if payload.action == "approve":
        section.status = "approved"
    elif payload.action == "reject":
        section.status = "rejected"
    else:
        section.status = "draft"
        section.revision += 1
        export_files = db.scalars(select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.quote_id == quote.id,
            InternalQuoteExportFile.status == "current",
        )).all()
        for export_file in export_files:
            export_file.status = "superseded"
            export_file.superseded_at = now
    section.reviewed_by = actor_name
    section.reviewed_at = now
    section.review_comment = payload.comment
    section.updated_at = now
    update_quote_status_from_sections(db, quote)
    add_quote_audit(
        db,
        quote.id,
        current_user,
        payload.action,
        department=department,
        detail=payload.comment,
    )
    add_auth_audit(
        db,
        f"internal_quote_{payload.action}",
        username=current_user.username,
        user_id=current_user.id,
        detail=f"报价={quote.id};分段={department};车间={quote.workshop_name}",
    )
    db.commit()
    return get_quote_detail(db, quote.id)


def mark_quote_exported(db: Session, quote: InternalQuote, current_user: AuthContext) -> None:
    if quote.status not in {"fully_approved", "exported"}:
        raise HTTPException(status_code=409, detail="全部八个分段审核通过后才可导出")
    quote.status = "exported"
    quote.updated_at = now_text()
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "export",
        department="sales",
        detail=f"{quote.quote_no} · {quote.version_label}",
    )
    db.commit()
