"""Copy a logical quotation into a new independent, atomic product batch."""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.internal_quote import InternalQuote, InternalQuoteAttachment, InternalQuoteSection
from app.schemas.internal_quote import InternalQuoteCloneRequest
from app.services.internal_quote import (
    _get_quote, _initiator_department, ensure_quote_read, ensure_permission_in_scope,
    validate_quote_business_owner, _check_revision, _find_reference_set, _json_object,
    _create_reference_set, _create_sections, _initial_section_payloads,
    _calculate_and_apply, _apply_uncalculated_state, _add_revision, _add_audit,
    quote_to_out, now_text, SECTION_CODE_ORDER, MANDATORY_SECTION_CODES,
)
from app.services.internal_quote_calculator import FORMULA_VERSION, CalculationInputError, canonical_json
from app.services.internal_quote_document import document_products, product_root, lock_documents
from app.services.transaction_lock import lock_transaction


class DocumentCloneProduct(BaseModel):
    source_quote_id: str | None = Field(default=None, min_length=1, max_length=64)
    revision: int | None = Field(default=None, ge=1)
    product_name: str = Field(min_length=1, max_length=255)
    qty: int = Field(gt=0)
    pricing_components: list[str] = Field(default_factory=list, max_length=50)

    @field_validator('product_name')
    @classmethod
    def name(cls, value):
        if not value.strip():
            raise ValueError('产品名称不能为空')
        return value.strip()

    @field_validator('pricing_components')
    @classmethod
    def components(cls, values):
        values = [value.strip() for value in values]
        if any(not value or len(value) > 64 for value in values) or len({v.casefold() for v in values}) != len(values):
            raise ValueError('配件名称不能为空、重复或超过 64 字')
        return values

    @model_validator(mode='after')
    def source_revision(self):
        if bool(self.source_quote_id) != bool(self.revision):
            raise ValueError('复制来源与版本号必须同时提供')
        return self


class DocumentCloneRequest(InternalQuoteCloneRequest):
    products: list[DocumentCloneProduct] = Field(min_length=1, max_length=20)


def clone_document(db, quote_id, payload, user, request=None):
    try:
        source = _get_quote(db, quote_id)
        selected = [_get_quote(db, row.source_quote_id) for row in payload.products if row.source_quote_id]
        for item in [source, *selected]:
            ensure_quote_read(db, user, item.factory_id)
            department = _initiator_department(user, item.factory_id)
            for permission in ('internal_quote:create', 'internal_quote:clone'):
                ensure_permission_in_scope(db, user, permission, item.factory_id, department)
            if item.factory_id != source.factory_id or item.customer != source.customer:
                raise HTTPException(400, '整单复制仅支持同一报价单内、同厂同客户的产品')
        lock_documents(db, [source, *selected])
        roots = document_products(db, source)
        for identity in sorted({f'{q.factory_id}:{q.batch_id or q.id}' for q in [source, *selected, *roots]}):
            lock_transaction(db, 'internal-quote', identity)
        for root in sorted(roots, key=lambda q: q.id):
            lock_transaction(db, 'internal-quote-family', root.id)
        db.expire_all()
        source = _get_quote(db, quote_id)
        roots = document_products(db, source)
        selected = [_get_quote(db, row.source_quote_id) for row in payload.products if row.source_quote_id]
        by_root = {product_root(db, q).id: q for q in selected}
        if len(selected) != len(by_root) or set(by_root) != {q.id for q in roots}:
            raise HTTPException(409, '请完整选择原报价的每款产品，每款选择一个来源版本；报价清单变化后请重新打开复制窗口')
        # Source product order is part of the document contract; extra blank products follow it.
        source_inputs = {row.source_quote_id: row for row in payload.products if row.source_quote_id}
        ordered = [(by_root[root.id], source_inputs[by_root[root.id].id]) for root in roots]
        ordered += [(None, row) for row in payload.products if not row.source_quote_id]
        for item, row in ordered:
            if item:
                _check_revision(item.header_revision, row.revision, item.product_name)
        department = _initiator_department(user, source.factory_id)
        owner = validate_quote_business_owner(db, payload.business_owner_id, source.factory_id, user.id, module_version='v4')
        timestamp = now_text()
        batch_id = f'IQB-{datetime.now():%Y%m%d}-{uuid4().hex[:12].upper()}'
        ids = [f'IQ-{datetime.now():%Y%m%d}-{uuid4().hex[:10].upper()}' for _ in ordered]
        targets = []
        for position, ((item, row), target_id) in enumerate(zip(ordered, ids, strict=True), 1):
            template = item or source
            reference = _find_reference_set(db, template)
            if reference is None:
                raise HTTPException(409, f'{template.product_name}缺少冻结参考资料，请先补全后复制')
            target = InternalQuote(
                id=target_id, factory_id=source.factory_id, workshop_code=template.workshop_code,
                workshop_name=template.workshop_name, customer=source.customer,
                quote_no=payload.quote_no if position == 1 else f'{payload.quote_no[:123]}-P{position:02d}',
                batch_quote_no=payload.quote_no, batch_id=batch_id, batch_position=position, batch_size=len(ordered),
                baseline_quote_id=ids[0], quote_type=(roots[0].quote_type if len(ordered) == len(roots) else 'series'),
                product_name=row.product_name, qty=row.qty, region_code=template.region_code if item else '',
                version_label=payload.version_label, status='drafting', initiator_department=department,
                business_owner_id=payload.business_owner_id, business_owner_name=owner,
                target_customer_price=payload.target_customer_price if payload.target_customer_price is not None else template.target_customer_price,
                target_date=payload.target_date, remark=payload.remark if payload.remark is not None else template.remark,
                module_version='v4', reference_snapshot_id='', formula_version=FORMULA_VERSION, header_revision=1,
                cloned_from_quote_id=item.id if item else '', created_by=user.id, created_by_name=user.display_name,
                created_at=timestamp, updated_at=timestamp,
            )
            db.add(target); db.flush()
            _create_reference_set(db, target, user, source_type='document_clone', snapshot=_json_object(reference.snapshot_json))
            sections = list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == item.id))) if item else []
            participating = {s.department for s in sections if s.is_required} | set(MANDATORY_SECTION_CODES)
            if item:
                attachments = list(db.scalars(select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == item.id)))
                mapping = {attachment.id: f'IQATT-{uuid4().hex}' for attachment in attachments}
                for attachment in attachments:
                    db.add(InternalQuoteAttachment(id=mapping[attachment.id], quote_id=target.id, factory_id=target.factory_id,
                        department=attachment.department, file_name=attachment.file_name, content_type=attachment.content_type,
                        size_bytes=attachment.size_bytes, sha256=attachment.sha256, content=attachment.content,
                        uploaded_by=user.id, uploaded_by_name=user.display_name, uploaded_at=timestamp))
                def remap(value):
                    if isinstance(value, dict): return {k: remap(v) for k,v in value.items() if k != 'import_batch_id'}
                    if isinstance(value, list): return [remap(v) for v in value]
                    return mapping.get(value, value) if isinstance(value, str) else value
                payloads = {s.department: canonical_json(remap(_json_object(s.payload_json))) for s in sections}
            else:
                payloads = _initial_section_payloads(SimpleNamespace(products=[SimpleNamespace(
                    history_source=None, pricing_components=row.pricing_components)]))
            _create_sections(db, target, user, participating, payloads)
            by_code = {s.department: s for s in db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == target.id))}
            for code in SECTION_CODE_ORDER:
                original = next((s for s in sections if s.department == code), None)
                section = by_code[code]
                if original and original.filled_at and section.is_required:
                    section.filled_by, section.filled_at = user.display_name, timestamp
                    section.revision += 1
                    try:
                        _calculate_and_apply(db, target, section, user)
                    except CalculationInputError as error:
                        _apply_uncalculated_state(db, target, section, error=error)
                    _add_revision(db, target, section, user, reason='document_clone')
            _add_audit(db, target, user, 'clone', detail=item.id if item else source.id,
                       reason='整单复制' if item else '整单复制时新增空白产品', request=request)
            targets.append(target)
        _add_audit(db, source, user, 'clone_source', detail=canonical_json({'batch_id': batch_id, 'quote_ids': ids}), request=request)
        db.commit()
        return quote_to_out(db, targets[0])
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '复制后的报价编号与版本已存在，请更换编号后再试') from None
    except Exception:
        db.rollback()
        raise
