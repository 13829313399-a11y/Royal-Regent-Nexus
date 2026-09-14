"""CSV staging: preserve raw text, explicit column mapping, atomic apply and traceable reversal."""
import csv
import hashlib
import io
import json
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models import uv_finance as m
from app.services import uv_finance as f, uv_printing as core

KINDS = {'products': ('product', ['master_write']), 'machines': ('machine', ['master_write']),
         'production_reports': ('report', ['report', 'quality']), 'expenses': ('expense-create', ['cost_read', 'cost_write']),
         'ink_movements': ('ink-movement-create', ['ink_write', 'cost_write', 'cost_read'])}


def parse_csv(content, filename):
    if not filename.lower().endswith('.csv'):
        f.fail('当前正式导入支持UTF-8 CSV，请先按模板导出；旧Excel标准/核数表尚需专门映射验收', 'file')
    if not content or len(content) > 5 * 1024 * 1024:
        f.fail('文件应为非空且不超过5MB', 'file')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            f.fail('列名为空或重复', 'file')
        rows = []
        for number, row in enumerate(reader, 2):
            if number > 5001:
                f.fail('单批最多5000行，请分批导入', 'file')
            if None in row or any(v is None for v in row.values()):
                f.fail(f'第{number}行列数不一致', 'file')
            rows.append({'source_line': number, 'raw': row})
        if not rows:
            f.fail('文件没有数据行', 'file')
        return rows
    except UnicodeDecodeError:
        f.fail('文件应使用UTF-8编码', 'file')


def upload(db, factory, actor, kind, filename, content):
    if kind not in KINDS:
        f.fail('请选择支持的导入类型', 'kind')
    digest = hashlib.sha256(content).hexdigest()
    core.lock(db, factory)
    old = db.scalar(select(m.UvImportBatch).where(m.UvImportBatch.factory_id == factory,
                    m.UvImportBatch.kind == kind, m.UvImportBatch.sha256 == digest))
    if old:
        return f.serial(old)
    rows = parse_csv(content, filename)
    row = m.UvImportBatch(**f.base(factory, actor, kind=kind, file_name=filename, sha256=digest,
          status='uploaded', rows=rows, errors=[], mapping={}))
    db.add(row)
    db.flush()
    return f.serial(row)


def normalized_rows(batch):
    if not batch.mapping:
        f.fail('请先明确列映射并检查预览', 'mapping')
    action = KINDS[batch.kind][0]
    normalized, errors = [], []
    for row in batch.rows:
        payload = {'factory_id': batch.factory_id, 'operation_id': f'import:{batch.id}:{row["source_line"]}', 'expected_version': 0}
        try:
            for target, column in batch.mapping.items():
                if column not in row['raw']:
                    raise ValueError(f'缺少列 {column}')
                value = row['raw'][column]
                if target in {'quality', 'worker_ids', 'source_allocations', 'evidence_job_ids', 'aliases', 'capabilities'}:
                    value = json.loads(value) if value else ({} if target in {'quality', 'capabilities'} else [])
                elif target in {'reported_qty', 'good_qty', 'defective_qty', 'pending_qty', 'semi_finished_qty'}:
                    value = int(value)
                elif target in {'enabled', 'is_active'}:
                    if value.lower() not in {'true', 'false'}:
                        raise ValueError(f'{target}需true或false')
                    value = value.lower() == 'true'
                elif target.endswith('_id') and not value:
                    value = None
                payload[target] = value
            if action in core.COMMAND_SCHEMAS:
                payload = core.COMMAND_SCHEMAS[action].model_validate(payload).model_dump(mode='json')
            elif action == 'expense-create':
                f.day(payload.get('occurred_on'))
                f.month(payload.get('period'))
                f.decimal(payload.get('amount'), 'amount')
                f.currency(payload.get('currency'))
                f.text(payload.get('evidence'), 'evidence', True)
                if payload.get('category') not in f.CATEGORIES:
                    raise ValueError('费用类别不支持')
            elif action == 'ink-movement-create':
                f.day(payload.get('occurred_on'))
                f.decimal(payload.get('quantity_ml'), 'quantity_ml', positive=True)
            normalized.append({'source_line': row['source_line'], 'payload': payload})
        except (ValueError, TypeError, ValidationError, KeyError) as exc:
            errors.append({'source_line': row['source_line'], 'message': str(exc)[:1000]})
        except f.HTTPException as exc:
            errors.append({'source_line': row['source_line'], 'message': exc.detail})
    return normalized, errors


def validated_preview(db, batch, actor):
    normalized, errors = normalized_rows(batch)
    planned = []
    # Execute the same validators and row locks in a rolled-back savepoint.
    # Earlier valid rows remain visible to later rows within this rehearsal,
    # so duplicate identities and cumulative stock consumption are checked.
    rehearsal = db.begin_nested()
    try:
        for row in normalized:
            trial = db.begin_nested()
            try:
                result = core.execute(db, batch.factory_id, actor, KINDS[batch.kind][0], row['payload'])
                db.flush()
                planned.append({'source_line': row['source_line'], 'planned_entity': result['entity']})
                trial.commit()
            except (f.HTTPException, IntegrityError, OperationalError, ValueError, TypeError, KeyError) as exc:
                trial.rollback()
                message = exc.detail if isinstance(exc, f.HTTPException) else '唯一约束、引用或业务状态校验失败'
                errors.append({'source_line': row['source_line'], 'message': message})
    finally:
        rehearsal.rollback()
    return normalized, errors, planned


def map_batch(db, factory, actor, p):
    f.fields(p, {'target_id', 'mapping'})
    batch = f.find(db, m.UvImportBatch, factory, p.get('target_id'))
    f.check_version(batch, p)
    if batch.status not in {'uploaded', 'previewed'}:
        f.fail('已入账或冲销批次不能改映射', status=409)
    mapping = p.get('mapping')
    if not isinstance(mapping, dict) or not mapping or any(not isinstance(v, str) for v in mapping.values()):
        f.fail('映射需使用目标字段到原始列名的对象', 'mapping')
    if set(mapping) & {'factory_id', 'operation_id', 'expected_version', 'id'}:
        f.fail('映射不能覆盖厂区、幂等键、版本或内部ID', 'mapping')
    batch.mapping = mapping
    _, errors, _ = validated_preview(db, batch, actor)
    batch.errors = errors
    batch.status = 'previewed'
    batch.version += 1
    batch.updated_at = m.now()
    return f.serial(batch)


def apply_batch(db, factory, actor, p):
    f.fields(p, {'target_id'})
    batch = f.find(db, m.UvImportBatch, factory, p.get('target_id'))
    if batch.status == 'applied':
        return f.serial(batch)
    f.check_version(batch, p)
    if batch.status != 'previewed':
        f.fail('请先预览校验；已冲销批次不能重用', status=409)
    rows, errors = normalized_rows(batch)
    if errors:
        f.fail('预览包含错误行，整批未入账', 'rows', 409)
    # Recheck all references, prices and stock in the final transaction.
    # Nothing is acknowledged or committed until every row has succeeded.
    ids = []
    for row in rows:
        result = core.execute(db, factory, actor, KINDS[batch.kind][0], row['payload'])
        ids.append(result['entity']['id'])
    batch.applied_ids = ids
    batch.status = 'applied'
    batch.version += 1
    batch.updated_at = m.now()
    return f.serial(batch)


def reverse_batch(db, factory, actor, p):
    f.fields(p, {'target_id', 'reason'})
    batch = f.find(db, m.UvImportBatch, factory, p.get('target_id'))
    f.check_version(batch, p)
    if batch.status != 'applied':
        f.fail('只有已入账批次可冲销', status=409)
    reason = f.text(p.get('reason'), 'reason', True)
    if batch.kind not in {'expenses', 'ink_movements'}:
        f.fail('该主数据/草稿批次需逐项检查引用并停用或作废，不支持整批删除', status=409)
    for ident in reversed(batch.applied_ids):
        cls = m.UvExpense if batch.kind == 'expenses' else m.UvInkMovement
        original = f.find(db, cls, factory, ident)
        handler = f.reverse_expense if batch.kind == 'expenses' else f.reverse_movement
        handler(db, factory, actor, {'factory_id': factory, 'target_id': ident,
                 'expected_version': original.version, 'reason': reason, 'operation_id': p['operation_id']})
    batch.status = 'reversed'
    batch.version += 1
    batch.updated_at = m.now()
    return f.serial(batch)


core.ACTIONS.update({'import-mapping': map_batch, 'import-apply': apply_batch, 'import-reverse': reverse_batch})
