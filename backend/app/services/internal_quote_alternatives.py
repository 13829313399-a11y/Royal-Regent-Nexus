"""Independent alternatives and immutable issued versions of one product."""
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.internal_quote import (
    InternalQuote, InternalQuoteAlternative, InternalQuoteFamily, InternalQuoteAttachment,
    InternalQuoteSection,
)
from app.services.auth import now_text, ensure_permission_in_scope, has_permission_in_scope
from app.services.internal_quote_document import deletion_reason
from app.services.transaction_lock import lock_transaction
from app.services.internal_quote import (
    quote_write, _get_quote, ensure_quote_read, ensure_quote_permission, _initiator_department,
    _check_revision, _json_object, _find_reference_set, _create_reference_set, _create_sections,
    _calculate_and_apply, _add_revision, _add_audit, _without_import_batch_ids,
    quote_to_out, SECTION_CODE_ORDER, ensure_quote_formula_current,
    _cost_context, _rr2_cost_summary,
)
from app.services.internal_quote_calculator import FORMULA_VERSION, canonical_json, content_hash


def _identity(db, quote):
    row = db.get(InternalQuoteAlternative, quote.id)
    return row.family_id if row else quote.id


def _family(db, quote, *, create=False):
    identity = _identity(db, quote)
    family = db.get(InternalQuoteFamily, identity)
    if family is None and create:
        family = InternalQuoteFamily(id=identity, factory_id=quote.factory_id, revision=0, selected_quote_id="")
        db.add(family)
        db.flush()
        db.add(InternalQuoteAlternative(quote_id=quote.id, family_id=identity,
            scenario_id="A", scenario_name="原方案", version_number=1,
            source_quote_id="", change_note="", issued_at=(quote.final_reviewed_at or quote.updated_at) if quote.status == "exported" else "",
            reported_at="", archived=False))
        db.flush()
    return family


def _write_family(db, quote, expected=None):
    lock_transaction(db, "internal-quote-family", _identity(db, quote))
    family = _family(db, quote, create=True)
    if expected is not None:
        _check_revision(family.revision, expected, "方案列表")
    return family


def list_alternatives(db, quote_id, user):
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    family = _family(db, quote)
    entries = list(db.scalars(select(InternalQuoteAlternative).where(
        InternalQuoteAlternative.family_id == family.id)).all()) if family else []
    if not entries:
        entries = [InternalQuoteAlternative(quote_id=quote.id, family_id=quote.id,
            scenario_id="A", scenario_name="原方案", version_number=1, source_quote_id="",
            change_note="", issued_at=quote.final_reviewed_at if quote.status == "exported" else "",
            reported_at="", archived=False)]
    items = []
    for row in sorted(entries, key=lambda row: (row.scenario_id, row.version_number)):
        item = _get_quote(db, row.quote_id)
        if item.factory_id != quote.factory_id:
            raise HTTPException(409, "方案厂区不一致")
        items.append({key: getattr(row, key) for key in (
            "quote_id", "scenario_id", "scenario_name", "version_number", "source_quote_id",
            "change_note", "issued_at", "reported_at", "archived") } | {
            "version_label": item.version_label, "status": item.status, "created_at": item.created_at,
            "quote_no": item.quote_no, "product_name": item.product_name, "customer": item.customer,
            "quantity": item.qty,
            "delete_block_reason": deletion_reason(db, item),
            "can_delete": not deletion_reason(db, item) and (item.created_by == user.id or has_permission_in_scope(user, "internal_quote:archive", item.factory_id, "sales-business")),
        })
    return {"family_id": family.id if family else quote.id, "revision": family.revision if family else 0,
            "selected_quote_id": family.selected_quote_id if family else "", "items": items}


def _manage(db, quote, user):
    ensure_quote_permission(db, user, "internal_quote:sales_edit", quote.factory_id, ("sales-business",))


@quote_write
def copy_alternative(db, quote_id, payload, user, request=None, *, commit=True):
    source = _get_quote(db, quote_id)
    ensure_quote_read(db, user, source.factory_id)
    department = _initiator_department(user, source.factory_id)
    ensure_permission_in_scope(db, user, "internal_quote:clone", source.factory_id, department)
    ensure_permission_in_scope(db, user, "internal_quote:create", source.factory_id, department)
    _check_revision(source.header_revision, payload.revision, "来源报价")
    if not payload.change_note.strip() or (payload.kind == "scenario" and not payload.name.strip()):
        raise HTTPException(400, "请填写方案名称和修改说明")
    family = _write_family(db, source, payload.family_revision)
    source_entry = db.get(InternalQuoteAlternative, source.id)
    entries = list(db.scalars(select(InternalQuoteAlternative).where(InternalQuoteAlternative.family_id == family.id)))
    if payload.kind == "scenario":
        if any(row.scenario_name.casefold() == payload.name.casefold() for row in entries):
            raise HTTPException(409, "已有同名方案，请使用不同名称或复制为新版本")
        def ordinal(identity):
            return ord(identity) - 64 if len(identity) == 1 else int(identity[1:])
        next_number = max(ordinal(row.scenario_id) for row in entries) + 1
        scenario = chr(64 + next_number) if next_number <= 26 else f"S{next_number}"
        name, version = payload.name, 1
    else:
        scenario, name = source_entry.scenario_id, source_entry.scenario_name
        version = max(row.version_number for row in entries if row.scenario_id == scenario) + 1
    # Older separately created quotations can already occupy a version label.
    label = f"{scenario}-V{version}"
    while db.scalar(select(InternalQuote.id).where(InternalQuote.factory_id == source.factory_id,
            InternalQuote.workshop_code == source.workshop_code, InternalQuote.quote_no == source.quote_no,
            InternalQuote.version_label == label)):
        version += 1
        label = f"{scenario}-V{version}"
    target_id = f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:10].upper()}"
    values = {key: getattr(source, key) for key in (
        "factory_id", "workshop_code", "workshop_name", "quote_no", "product_name", "region_code",
        "customer", "qty", "business_owner_id", "business_owner_name", "target_customer_price", "target_date", "remark")}
    target = InternalQuote(**values, id=target_id, quote_type="single", batch_id=target_id,
        batch_quote_no=source.quote_no, batch_position=1, batch_size=1, baseline_quote_id=target_id,
        version_label=label, status="drafting", initiator_department=department, module_version="v4",
        formula_version=FORMULA_VERSION, reference_snapshot_id="", header_revision=1,
        cloned_from_quote_id=source.id, created_by=user.id, created_by_name=user.display_name,
        created_at=now_text(), updated_at=now_text())
    db.add(target)
    db.flush()
    reference = _find_reference_set(db, source)
    if reference is None:
        raise HTTPException(409, "来源报价缺少料价及汇率快照，请先补全来源资料")
    _create_reference_set(db, target, user, source_type="alternative_copy", snapshot=_json_object(reference.snapshot_json))
    attachments = list(db.scalars(select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == source.id)))
    id_map = {row.id: f"IQATT-{uuid4().hex}" for row in attachments}
    for row in attachments:
        db.add(InternalQuoteAttachment(id=id_map[row.id], quote_id=target.id, factory_id=target.factory_id,
            department=row.department, file_name=row.file_name, content_type=row.content_type,
            size_bytes=row.size_bytes, sha256=row.sha256, content=row.content,
            uploaded_by=user.id, uploaded_by_name=user.display_name, uploaded_at=now_text()))
    def remap(value):
        if isinstance(value, dict):
            return {key: remap(child) for key, child in value.items()}
        if isinstance(value, list):
            return [remap(child) for child in value]
        return id_map.get(value, value) if isinstance(value, str) else value
    sections = list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == source.id)))
    payloads = {row.department: canonical_json(remap(_without_import_batch_ids(_json_object(row.payload_json)))) for row in sections}
    _create_sections(db, target, user, {row.department for row in sections if row.is_required}, payloads)
    by_code = {row.department: row for row in db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == target.id))}
    for code in SECTION_CODE_ORDER:
        section = by_code[code]
        if section.is_required and _json_object(section.payload_json):
            section.revision += 1
            section.filled_by, section.filled_at = user.display_name, now_text()
            _calculate_and_apply(db, target, section, user)
            _add_revision(db, target, section, user, reason="alternative_copy")
    db.add(InternalQuoteAlternative(quote_id=target.id, family_id=family.id, scenario_id=scenario,
        scenario_name=name, version_number=version, source_quote_id=source.id, change_note=payload.change_note,
        issued_at="", reported_at="", archived=False))
    family.revision += 1
    _add_audit(db, target, user, "alternative_copy", detail=canonical_json({
        "source_quote_id": source.id, "family_id": family.id, "kind": payload.kind,
        "scenario_name": name, "change_note": payload.change_note}), request=request)
    if commit:
        db.commit()
    else:
        db.flush()
    return quote_to_out(db, target)


@quote_write
def select_alternative(db, quote_id, payload, user, request=None):
    quote = _get_quote(db, quote_id)
    _manage(db, quote, user)
    family = _write_family(db, quote, payload.family_revision)
    if not payload.reason.strip():
        raise HTTPException(400, "请填写采用或取消采用说明")
    if payload.selected_quote_id:
        target = db.get(InternalQuoteAlternative, payload.selected_quote_id)
        if not target or target.family_id != family.id or target.archived:
            raise HTTPException(400, "请选择本产品未归档的方案版本")
        candidate = _get_quote(db, target.quote_id)
        if candidate.status != "exported":
            raise HTTPException(409, "只能标记已正式输出的版本为客户采用")
    before = family.selected_quote_id
    family.selected_quote_id = payload.selected_quote_id
    family.revision += 1
    _add_audit(db, quote, user, "alternative_selected", detail=canonical_json({
        "before": before, "after": family.selected_quote_id, "reason": payload.reason}), request=request)
    db.commit()
    return list_alternatives(db, quote_id, user)


@quote_write
def archive_alternative(db, quote_id, payload, user, request=None):
    quote = _get_quote(db, quote_id)
    _manage(db, quote, user)
    family = _write_family(db, quote, payload.family_revision)
    if not payload.reason.strip():
        raise HTTPException(400, "请填写归档或恢复说明")
    if payload.archived and family.selected_quote_id == quote.id:
        raise HTTPException(409, "客户采用的版本请先取消采用，再归档")
    entry = db.get(InternalQuoteAlternative, quote.id)
    entry.archived = payload.archived
    family.revision += 1
    _add_audit(db, quote, user, "alternative_archive", detail=canonical_json({
        "archived": payload.archived, "reason": payload.reason}), request=request)
    db.commit()
    return list_alternatives(db, quote_id, user)


@quote_write
def report_alternative(db, quote_id, payload, user, request=None):
    quote = _get_quote(db, quote_id)
    _manage(db, quote, user)
    _check_revision(quote.header_revision, payload.revision, "报价版本")
    if quote.status != "exported":
        raise HTTPException(409, "请先正式输出再标记已报客")
    family = _write_family(db, quote)
    entry = db.get(InternalQuoteAlternative, quote.id)
    if entry.archived:
        raise HTTPException(409, "已归档版本请先恢复")
    if not entry.reported_at:
        entry.reported_at = now_text()
        family.revision += 1
        _add_audit(db, quote, user, "alternative_reported", detail=entry.reported_at, request=request)
    db.commit()
    return list_alternatives(db, quote_id, user)


@quote_write
def issue_alternative(db, quote_id, payload, user, request=None, *, commit=True):
    from app.services.internal_quote_artifacts import _ensure_export_permission, create_controlled_export
    quote = _get_quote(db, quote_id)
    _ensure_export_permission(db, quote, user)
    if quote.module_version != "v4":
        raise HTTPException(409, "历史报价请复制为新版本后直接输出，原审核记录继续保留")
    # A retry returns the exact already-issued bytes, even after formula/layout upgrades.
    if quote.final_release_status == "issued":
        return create_controlled_export(db, quote_id, user, request, commit=commit)
    _check_revision(quote.header_revision, payload.revision, "报价版本")
    if quote.status not in {"drafting", "rejected", "ready_for_final_review"}:
        raise HTTPException(409, "当前报价不可直接输出")
    family = _write_family(db, quote)
    entry = db.get(InternalQuoteAlternative, quote.id)
    if entry.archived:
        raise HTTPException(409, "请先恢复已归档方案")
    sections = list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)))
    required = [row for row in sections if row.is_required]
    problems = [row.department_name for row in required if not row.filled_at
        or not _json_object(row.payload_json) or row.calculation_status != "valid"
        or row.dependency_status != "current" or row.status not in {"draft", "rejected"}]
    if not required or problems:
        raise HTTPException(409, "以下部门须完成填写、保存及有效计算：" + "、".join(problems))
    ensure_quote_formula_current(quote, sections)
    cost_context = _cost_context(db, quote)
    reference = _find_reference_set(db, quote)
    if reference is None:
        raise HTTPException(409, "报价缺少料价及汇率快照")
    summary = _rr2_cost_summary(sections, cost_context, _json_object(reference.snapshot_json), quote.qty, factory_id=quote.factory_id)
    quote.header_revision += 1
    quote.final_release_revision += 1
    quote.final_release_status = "issued"
    quote.status = "exported"
    quote.updated_at = now_text()
    entry.issued_at = quote.updated_at
    family.revision += 1
    for section in required:
        section.status = "sealed"
        section.revision += 1
        _add_revision(db, quote, section, user, reason="direct_issue")
    manifest = {"schema_version": "internal-quote-direct-issue-v1", "quote_id": quote.id,
        "issued_by": user.id, "issued_by_name": user.display_name, "issued_at": entry.issued_at,
        "header_revision": quote.header_revision, "formula_version": quote.formula_version,
        "reference_snapshot_id": quote.reference_snapshot_id,
        "cost_context": {key: str(value) for key, value in cost_context.items()},
        "rr2_cost_summary": summary,
        "section_revisions": {row.department: row.revision for row in sections}}
    manifest["manifest_sha256"] = content_hash(manifest)
    quote.final_submission_manifest_json = canonical_json(manifest)
    _add_audit(db, quote, user, "direct_issue", detail=canonical_json({key: manifest[key] for key in (
        "schema_version", "quote_id", "issued_by", "issued_at", "header_revision", "manifest_sha256")}), request=request)
    db.flush()
    # The exporter commits the issue, immutable workbook and handoff in one transaction.
    return create_controlled_export(db, quote_id, user, request, commit=commit)
