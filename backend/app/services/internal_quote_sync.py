"""Explicit preview-and-apply synchronization within one alternative family."""
from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.internal_quote import InternalQuote, InternalQuoteAlternative, InternalQuoteAttachment
from app.schemas.internal_quote_alternatives import AlternativeCopyRequest
from app.services.auth import ensure_permission_in_scope, now_text
from app.services.internal_quote import (
    _get_quote, _get_section, _json_object, _check_revision, _initiator_department,
    _save_section_in_transaction, _derive_quote_status, _add_audit, quote_to_out,
    ensure_quote_read, ensure_section_permission, SECTION_CODE_ORDER, MUTABLE_SECTION_STATUSES,
    _without_import_batch_ids,
)
from app.services.internal_quote_alternatives import _family, _identity, copy_alternative
from app.services.internal_quote_calculator import content_hash, canonical_json
from app.services.internal_quote_release import _changes
from app.services.transaction_lock import lock_transaction

# A category is replaced as a unit; the preview includes removals. Packaging is never selected implicitly.
BLOCKS = {
    'engineering.hardware': ('engineering', '五金', 'materials', 'hardware'),
    'engineering.auxiliary': ('engineering', '辅助材料 / 外购件', 'materials', 'auxiliary'),
    'engineering.molds': ('engineering', '工程模具', 'molds', None),
    'molding': ('molding', '注塑 / 吹塑资料', None, None),
    'assembly.production': ('assembly', '组装工序（保留包装工序及人工基数）', 'groups', 'assembly'),
    'assembly.packaging': ('assembly', '包装工序（保留组装工序及人工基数）', 'groups', 'packaging'),
    'painting': ('painting', '喷油资料', None, None),
    'electronic': ('electronic', '电子资料', None, None),
    'slush': ('slush', '搪胶资料', None, None),
    'sewing': ('sewing', '车缝资料', None, None),
    'hair': ('hair', '植发资料', None, None),
    'sales.packaging': ('sales', '包装材料', 'packaging_materials', None),
    'sales.cartons': ('sales', '纸箱与平卡（保留彩盒尺寸及纸价系数）', 'cartons', None),
    'sales.color_box': ('sales', '彩盒尺寸', 'color_box_size_in', None),
}


def sync_options(db, quote_id, user):
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    result = []
    for key, (code, label, _, _) in BLOCKS.items():
        section = _get_section(db, quote_id, code)
        if not section.is_required:
            continue
        try:
            ensure_section_permission(db, user, quote.factory_id, code, 'edit')
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        result.append({'key': key, 'label': label, 'department': section.department_name})
    return result


def _merge(before, source, block):
    source = _without_import_batch_ids(source)
    _, _, field, category = BLOCKS[block]
    result = deepcopy(before)
    if field is None:
        # Customer-facing supplements stay with their own scheme.
        result = deepcopy(source)
        for key in set(result) | set(before):
            if key.startswith(('customer_', 'dickie', 'disney', 'caixing', 'buzzbee')):
                if key in before:
                    result[key] = deepcopy(before[key])
                else:
                    result.pop(key, None)
    elif category:
        def selected(row):
            return row.get('category', 'assembly' if field == 'groups' else 'auxiliary') == category
        result[field] = [deepcopy(row) for row in before.get(field, []) if not selected(row)] + [deepcopy(row) for row in source.get(field, []) if selected(row)]
    else:
        result[field] = deepcopy(source.get(field, {} if field == 'color_box_size_in' else []))
        if block == 'engineering.molds':
            old_rows = before.get('molds', [])
            for row in result[field]:
                matches = [old for old in old_rows if row.get('mold_no') and old.get('mold_no') == row['mold_no']]
                for key in list(row):
                    if key.startswith(('dickie', 'disney', 'caixing')):
                        row.pop(key)
                if len(matches) == 1:
                    row.update({key: deepcopy(value) for key, value in matches[0].items() if key.startswith(('dickie', 'disney', 'caixing'))})
        if block == 'sales.color_box' and 'color_box_size_unit' in source:
            result['color_box_size_unit'] = source['color_box_size_unit']
    return _preserve_local(result, before)


def _local_key(key):
    return key in {'markup_override', 'pricing_component_id', 'markup', 'markup_x', 'exchange_rate', 'profit_multiplier', 'profit_rate_percent'} or key.startswith(('customer_', 'dickie', 'disney', 'caixing', 'buzzbee'))


def _has_local(value):
    if isinstance(value, dict):
        return any((_local_key(key) and child not in (None, '', 0, False, [], {})) or _has_local(child) for key, child in value.items())
    return isinstance(value, list) and any(_has_local(child) for child in value)


def _preserve_local(value, previous):
    """Scheme-owned multipliers and customer supplements never travel with cost inputs."""
    if value == previous:
        return deepcopy(value)
    if isinstance(value, dict):
        old = previous if isinstance(previous, dict) else {}
        result = {key: _preserve_local(child, old.get(key)) for key, child in value.items() if not _local_key(key)}
        result.update({key: deepcopy(child) for key, child in old.items() if _local_key(key)})
        return result
    if isinstance(value, list):
        old = previous if isinstance(previous, list) else []
        def identity(row):
            if not isinstance(row, dict): return None
            return (row.get('category', ''), row.get('mold_no') or row.get('item') or row.get('name') or row.get('doll_name'))
        used = set()
        exact = {}
        # Retained/unselected rows reserve their own matches before changed rows are considered.
        for index, row in enumerate(value):
            match = next((i for i, candidate in enumerate(old) if i not in used and candidate == row), None)
            if match is not None:
                exact[index] = match
                used.add(match)
        result = []
        for index, row in enumerate(value):
            if index in exact:
                result.append(deepcopy(row))
                continue
            key = identity(row)
            matches = [i for i, candidate in enumerate(old) if i not in used and key is not None and key[1] and identity(candidate) == key]
            incoming = sum(1 for i, candidate in enumerate(value) if i not in exact and identity(candidate) == key)
            if (len(matches) > 1 or incoming > 1) and any(_has_local(old[i]) for i in matches):
                raise HTTPException(409, '同名明细含独立倍率或报客补录，无法唯一对应，请逐版修改')
            match = matches[0] if len(matches) == 1 and incoming == 1 else None
            if match is not None: used.add(match)
            result.append(_preserve_local(row, old[match] if match is not None else None))
        return result
    return deepcopy(value)


def _attachment_equivalents(db, source_id, target_id):
    source = list(db.scalars(select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == source_id)))
    target = list(db.scalars(select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == target_id).order_by(InternalQuoteAttachment.id)))
    return {row.id: match.id for row in source if (match := next((candidate for candidate in target
            if candidate.department == row.department and candidate.sha256 == row.sha256), None))}


def _remap_refs(value, mapping):
    if isinstance(value, dict): return {key: _remap_refs(child, mapping) for key, child in value.items()}
    if isinstance(value, list): return [_remap_refs(child, mapping) for child in value]
    return mapping.get(value, value) if isinstance(value, str) else value


def _locked_plan(db, quote_id, payload, user):
    ids = [target.quote_id for target in payload.targets]
    if len(set(ids)) != len(ids) or quote_id in ids or len(set(payload.blocks)) != len(payload.blocks):
        raise HTTPException(400, '请勿重复选择来源、目标或同步类别')
    if not payload.reason.strip() or any(block not in BLOCKS for block in payload.blocks):
        raise HTTPException(400, '请选择有效资料类别并填写同步说明')
    # Same lock namespace/order as ordinary quote writes; lock all quotes before the family.
    identities = []
    for identity in [quote_id, *ids]:
        quote = _get_quote(db, identity)
        ensure_quote_read(db, user, quote.factory_id)
        identities.append(f'{quote.factory_id}:{quote.batch_id or quote.id}')
    for identity in sorted(set(identities)):
        lock_transaction(db, 'internal-quote', identity)
    source = _get_quote(db, quote_id)
    lock_transaction(db, 'internal-quote-family', _identity(db, source))
    family = _family(db, source)
    if not family:
        raise HTTPException(409, '请先复制一个独立方案')
    _check_revision(family.revision, payload.family_revision, '方案列表')
    _check_revision(source.header_revision, payload.revision, '来源报价')
    if source.module_version != 'v4' or source.status == 'archived' or db.get(InternalQuoteAlternative, source.id).archived:
        raise HTTPException(409, '来源须为未归档的新流程报价')
    codes = [code for code in SECTION_CODE_ORDER if any(BLOCKS[block][0] == code for block in payload.blocks)]
    source_payloads = {}
    for code in codes:
        ensure_section_permission(db, user, source.factory_id, code, 'edit')
        section = _get_section(db, source.id, code)
        if not section.is_required or not section.filled_at or section.calculation_status != 'valid' or section.dependency_status != 'current':
            raise HTTPException(409, f'{section.department_name}来源资料须先完成保存和有效核算')
        source_payloads[code] = _json_object(section.payload_json)
    plans = []
    for selection in payload.targets:
        target = _get_quote(db, selection.quote_id)
        entry = db.get(InternalQuoteAlternative, target.id)
        if not entry or entry.family_id != family.id or target.factory_id != source.factory_id or target.customer != source.customer:
            raise HTTPException(400, '只能同步同一产品、客户及厂区内的方案')
        if entry.archived or target.status == 'archived' or target.module_version != 'v4':
            raise HTTPException(409, '目标须为未归档的新流程方案')
        _check_revision(target.header_revision, selection.revision, '目标报价')
        if target.final_release_status == 'issued' and not selection.create_version:
            raise HTTPException(409, '已输出方案须选择复制新版本，原版不可覆盖')
        if selection.create_version:
            department = _initiator_department(user, target.factory_id)
            for permission in ('internal_quote:clone', 'internal_quote:create'):
                ensure_permission_in_scope(db, user, permission, target.factory_id, department)
        elif target.status not in ('drafting', 'rejected'):
            raise HTTPException(409, '目标当前不可编辑，请选择复制新版本')
        next_payloads = {}
        for code in codes:
            ensure_section_permission(db, user, target.factory_id, code, 'edit')
            section = _get_section(db, target.id, code)
            if not section.is_required or (not selection.create_version and section.status not in MUTABLE_SECTION_STATUSES):
                raise HTTPException(409, f'目标 {target.version_label} 的{section.department_name}未参与或不可编辑')
            next_payloads[code] = _json_object(section.payload_json)
        for block in payload.blocks:
            code = BLOCKS[block][0]
            next_payloads[code] = _merge(next_payloads[code], source_payloads[code], block)
        next_payloads = _remap_refs(next_payloads, _attachment_equivalents(db, source.id, target.id))
        # Component IDs belong to each quotation. Never guess cross-scheme component mapping.
        if source_payloads and (_json_object(_get_section(db, source.id, 'sales').payload_json).get('pricing_mode') == 'component'
                or _json_object(_get_section(db, target.id, 'sales').payload_json).get('pricing_mode') == 'component'):
            raise HTTPException(409, '含独立组件倍率的报价暂不支持批量同步，请逐版编辑')
        before = quote_to_out(db, target).model_dump(mode='json')
        after = deepcopy(before)
        for section in after['sections']:
            if section['department'] in next_payloads:
                section['payload'] = next_payloads[section['department']]
        changes = [{ 'section_code': code, 'section_name': _get_section(db, target.id, code).department_name,
                     'payload_changes': [change.model_dump() for change in _changes(_json_object(_get_section(db, target.id, code).payload_json), data)],
                     'before_total_hkd': '0', 'after_total_hkd': '0', 'delta_hkd': '0' }
                   for code, data in next_payloads.items()]
        plans.append({'quote_id': target.id, 'version_label': target.version_label, 'create_version': selection.create_version,
                      'before': before, 'after': after, 'sections': changes, 'changed': any(row['payload_changes'] for row in changes)})
    token = content_hash({'source': source.id, 'revision': source.header_revision, 'family': family.revision,
                          'request': payload.model_dump(exclude={'preview_token'}), 'plans': plans})
    return source, family, plans, token


def preview_sync(db, quote_id, payload, user):
    _, _, plans, token = _locked_plan(db, quote_id, payload, user)
    return {'preview_token': token, 'targets': plans}


def apply_sync(db, quote_id, payload, user, request=None):
    try:
        source, family, plans, token = _locked_plan(db, quote_id, payload, user)
        if not payload.preview_token or payload.preview_token != token:
            raise HTTPException(409, '预览已失效，请重新预览后确认同步')
        source_attachments = list(db.scalars(select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == source.id)))
        results = []
        for plan in plans:
            if not plan['changed']:
                results.append({'quote_id': plan['quote_id'], 'version_label': plan['version_label'], 'changed': False})
                continue
            target = _get_quote(db, plan['quote_id'])
            if plan['create_version']:
                copied = copy_alternative(db, target.id, AlternativeCopyRequest(revision=target.header_revision,
                    family_revision=family.revision, kind='version', change_note=f'批量同步：{payload.reason}'), user, request, commit=False)
                target = _get_quote(db, copied.id)
            # Start from the new version's own payload (its attachment IDs have already been remapped).
            attachment_map = _attachment_equivalents(db, source.id, target.id)
            def remap(value):
                if isinstance(value, dict): return {key: remap(child) for key, child in value.items()}
                if isinstance(value, list): return [remap(child) for child in value]
                if not isinstance(value, str): return value
                if value in attachment_map: return attachment_map[value]
                original = next((row for row in source_attachments if row.id == value), None)
                if original is None: return value
                new_id = f'IQATT-{uuid4().hex}'
                db.add(InternalQuoteAttachment(id=new_id, quote_id=target.id, factory_id=target.factory_id,
                    department=original.department, file_name=original.file_name, content_type=original.content_type,
                    size_bytes=original.size_bytes, sha256=original.sha256, content=original.content,
                    uploaded_by=user.id, uploaded_by_name=user.display_name, uploaded_at=now_text()))
                attachment_map[value] = new_id
                return new_id
            for code in SECTION_CODE_ORDER:
                blocks = [block for block in payload.blocks if BLOCKS[block][0] == code]
                if not blocks: continue
                section = _get_section(db, target.id, code)
                data = _json_object(section.payload_json)
                for block in blocks:
                    data = _merge(data, _json_object(_get_section(db, source.id, code).payload_json), block)
                data = _remap_refs(data, attachment_map)
                if data == _json_object(section.payload_json): continue
                _save_section_in_transaction(db, target, section, remap(data), payload.reason, user, request)
            _derive_quote_status(db, target)
            _add_audit(db, target, user, 'alternative_sync', detail=canonical_json({'source_quote_id': source.id, 'blocks': payload.blocks,
                'source_revision': source.header_revision, 'preview_token': token}), reason=payload.reason, request=request)
            results.append({'quote_id': target.id, 'version_label': target.version_label, 'changed': True})
        if any(row['changed'] for row in results): family.revision += 1
        db.commit()
        return {'targets': results}
    except Exception:
        db.rollback()
        raise
