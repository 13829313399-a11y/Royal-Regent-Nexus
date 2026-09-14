"""UV financial routes share the host session and UV atomic command receipts."""
from typing import Annotated, Any
from urllib.parse import urlencode
import csv
import io

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db import get_db
from app.models import uv_finance as m
from app.services import uv_finance as f, uv_printing as core
from app.services import uv_imports as imports
from app.services.auth import AuthContext, get_current_user, authorization_decision

router = APIRouter(prefix='/api/uv-printing', tags=['uv-printing-finance'])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[AuthContext, Depends(get_current_user)]
core.ACTIONS.update(f.ACTIONS)


def authorize(db, user, factory, *actions):
    if factory is None:
        raise HTTPException(422, 'factory_id必填')
    if factory != 'huakang-a':
        raise HTTPException(403, 'UV打印只允许华康A生产部')
    if not settings.uv_printing_enabled:
        raise HTTPException(503, 'UV打印尚未启用')
    for action in {'read', *actions}:
        if not allowed(user, action):
            raise HTTPException(403, '无华康A生产部相应UV权限')


def allowed(user, action):
    return authorization_decision(user, 'uv_printing:' + action, 'huakang-a', 'production')[0]


def envelope(data, coverage='complete', warnings=None):
    return {'meta': {'factory_id': 'huakang-a', 'as_of': m.now(), 'data_mode': 'live', 'coverage': coverage,
                     'warnings': warnings or []}, 'data': data}


def scrub(value, cost):
    if cost:
        return value
    if isinstance(value, list):
        return [scrub(v, cost) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, cost) for k, v in value.items()
                if k not in {'amount', 'unit_cost', 'cost_value', 'stock_value', 'currency', 'result', 'input'}}
    return value


def command(db, user, action, payload, permissions):
    factory = payload.get('factory_id')
    authorize(db, user, factory, *permissions)
    try:
        result = core.execute(db, factory, user.id, action, payload)
        db.commit()
        return envelope(scrub(result, allowed(user, 'cost_read')) if action.startswith('ink-') else result)
    except (IntegrityError, OperationalError):
        db.rollback()
        raise HTTPException(409, '数据重复或并发状态已变化，请刷新核对后重试')
    except (TypeError, ValueError, AttributeError, KeyError):
        db.rollback()
        raise HTTPException(422, {'code': 'uv_invalid_field', 'message': '字段类型不正确或必填字段缺失', 'retryable': False})
    except Exception:
        db.rollback()
        raise


def scope(factory_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
          business_date: str | None = None, date_from: str | None = None, date_to: str | None = None,
          machine_id: str | None = None, product_id: str | None = None, shift: str | None = None,
          status: str | None = None, q: str = Query('', max_length=128),
          supplier: str | None = None, material: str | None = None, color: str | None = None):
    result = dict(factory_id=factory_id, page=page, page_size=page_size, machine_id=machine_id,
                  product_id=product_id, shift=shift, status=status, q=q, supplier=supplier, material=material, color=color)
    if shift not in {None, 'day', 'night'}:
        f.fail('请选择白班/夜班；全天省略shift', 'shift')
    for key, value in [('business_date', business_date), ('date_from', date_from), ('date_to', date_to)]:
        if value is not None:
            result[key] = f.day(value, key)
    if date_from and date_to and date_from > date_to:
        f.fail('开始日不能晚于结束日', 'date_from')
    return result


Scope = Annotated[dict, Depends(scope)]


def filtered(db, cls, query_scope):
    query = select(cls).where(cls.factory_id == query_scope['factory_id'])
    date_col = getattr(cls, 'posted_on', getattr(cls, 'occurred_on', None))
    if date_col is not None:
        for key, op in [('business_date', 'eq'), ('date_from', 'ge'), ('date_to', 'le')]:
            if query_scope.get(key):
                value = query_scope[key]
                query = query.where({'eq': date_col == value, 'ge': date_col >= value, 'le': date_col <= value}[op])
    for key in ('machine_id', 'supplier', 'material', 'color', 'status'):
        if query_scope.get(key) and hasattr(cls, key):
            query = query.where(getattr(cls, key) == query_scope[key])
    if query_scope.get('q'):
        from sqlalchemy import or_
        columns = [getattr(cls, key) for key in ('supplier', 'color', 'purpose', 'source_doc', 'note', 'label', 'file_name') if hasattr(cls, key)]
        if columns:
            query = query.where(or_(*(column.contains(query_scope['q'], autoescape=True) for column in columns)))
    return list(db.scalars(query.order_by(cls.created_at.desc(), cls.id)))


@router.get('/ink-skus')
def skus(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'])
    rows = filtered(db, m.UvInkSku, query_scope)
    return envelope(core.page([f.sku_output(row, allowed(user, 'cost_read')) for row in rows], query_scope), 'complete' if rows else 'no_data')


@router.post('/ink-skus')
def create_sku(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    return command(db, user, 'ink-sku-create', p, ['master_write'])


@router.get('/ink-balances')
def balances(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'])
    rows = [f.balance_output(row) for row in filtered(db, m.UvInkSku, query_scope)]
    return envelope(core.page(rows, query_scope), 'complete' if rows else 'no_data')


@router.get('/ink-movements')
def movements(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'])
    rows = [f.movement_output(db, row, allowed(user, 'cost_read')) for row in filtered(db, m.UvInkMovement, query_scope)]
    return envelope(core.page(rows, query_scope), 'complete' if rows else 'no_data')


@router.post('/ink-movements')
def create_movement(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    permissions = ['ink_write']
    if p.get('unit_cost') is not None or p.get('currency') is not None:
        permissions.append('cost_write')
    return command(db, user, 'ink-movement-create', p, permissions)


@router.post('/ink-movements/{target_id}/reverse')
def reverse_movement(target_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('target_id') not in {None, target_id}:
        f.fail('路径和请求对象不一致', 'target_id')
    return command(db, user, 'ink-movement-reverse', {**p, 'target_id': target_id}, ['ink_write'])


@router.get('/expenses')
def expenses(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'], 'cost_read')
    rows = [f.expense_output(row) for row in filtered(db, m.UvExpense, query_scope)]
    return envelope(core.page(rows, query_scope), 'complete' if rows else 'no_data')


@router.post('/expenses')
def create_expense(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    return command(db, user, 'expense-create', p, ['cost_read', 'cost_write'])


@router.post('/expenses/{target_id}/reverse')
def reverse_expense(target_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('target_id') not in {None, target_id}:
        f.fail('路径和请求对象不一致', 'target_id')
    return command(db, user, 'expense-reverse', {**p, 'target_id': target_id}, ['cost_read', 'cost_write'])


@router.get('/monthly-policies/{period}')
def policy(period: str, factory_id: str, db: Db, user: User):
    authorize(db, user, factory_id, 'cost_read')
    row = f.latest_policy(db, factory_id, f.month(period))
    return envelope(f.serial(row) if row else None, 'complete' if row else 'no_data')


@router.post('/monthly-policies/{period}')
@router.put('/monthly-policies/{period}')
def save_policy(period: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('month') not in {None, period}:
        f.fail('路径和请求月份不一致', 'month')
    return command(db, user, 'monthly-policy-save', {**p, 'month': period}, ['cost_read', 'cost_write'])


@router.post('/pricing/preview')
def preview(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    authorize(db, user, p.get('factory_id'), 'cost_read')
    return envelope(f.pricing(p))


@router.get('/pricing-quotes')
def quotes(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'], 'cost_read')
    rows = [{**f.serial(row), 'created_by_name': row.created_by} for row in filtered(db, m.UvPricingQuote, query_scope)]
    return envelope(core.page(rows, query_scope), 'complete' if rows else 'no_data')


@router.post('/pricing-quotes')
def save_quote(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    return command(db, user, 'pricing-quote-create', p, ['cost_read', 'cost_write'])


@router.post('/pricing-quotes/{quote_id}/adopt')
def adopt_quote(quote_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('quote_id') not in {None, quote_id}:
        f.fail('路径和请求测算不一致', 'quote_id')
    return command(db, user, 'pricing-quote-adopt', {**p, 'quote_id': quote_id}, ['cost_read', 'cost_write'])


EXPORT_PERMISSIONS = {'daily': ['cost_read'], 'monthly': ['cost_read'], 'reports': [], 'ink_movements': [],
                      'payroll': ['payroll_read'], 'expenses': ['cost_read']}


def export_rows(db, user, kind, query_scope):
    if kind not in EXPORT_PERMISSIONS:
        raise HTTPException(404, '未提供该导出类型')
    authorize(db, user, query_scope.get('factory_id'), 'export', *EXPORT_PERMISSIONS[kind])
    from app.api.uv_printing import redact
    if kind == 'reports':
        from app.models.uv_printing import UvReport
        return [redact(core.report_output(db, row), user)
                for row in core.query_rows(db, UvReport, query_scope['factory_id'], query_scope)]
    if kind == 'ink_movements':
        return [f.movement_output(db, row, allowed(user, 'cost_read')) for row in filtered(db, m.UvInkMovement, query_scope)]
    if kind == 'expenses':
        return [f.expense_output(row) for row in filtered(db, m.UvExpense, query_scope)]
    if kind == 'payroll':
        return core.payroll_preview(db, query_scope['factory_id'], query_scope)['lines']
    if kind == 'monthly':
        rows = core.monthly_projection(db, query_scope['factory_id'], query_scope)['months']
    else:
        rows = core.daily_projection(db, query_scope['factory_id'], query_scope)
    if not allowed(user, 'payroll_read'):
        rows = [{key: value for key, value in row.items() if key not in {'payroll_amount', 'payroll_ratio'}} for row in rows]
    return rows


@router.post('/exports/{kind}')
def prepare_export(kind: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    query_scope = p.get('scope', {})
    if not isinstance(query_scope, dict):
        f.fail('导出范围必须为对象', 'scope')
    allowed_keys = {'factory_id', 'business_date', 'date_from', 'date_to', 'machine_id', 'product_id', 'shift', 'status', 'q', 'supplier', 'material', 'color', 'page', 'page_size'}
    if set(query_scope) - allowed_keys or any(v is not None and not isinstance(v, str) for k, v in query_scope.items() if k not in {'page', 'page_size'}):
        f.fail('导出范围包含不支持的字段或类型', 'scope')
    query_scope = {k: v for k, v in query_scope.items() if k not in {'page', 'page_size'}}
    if query_scope.get('shift') not in {None, 'day', 'night'} or len(query_scope.get('q') or '') > 128:
        f.fail('导出筛选无效', 'scope')
    for key in ('business_date', 'date_from', 'date_to'):
        if query_scope.get(key) is not None:
            f.day(query_scope[key], key)
    if query_scope.get('date_from') and query_scope.get('date_to') and query_scope['date_from'] > query_scope['date_to']:
        f.fail('开始日不能晚于结束日', 'date_from')
    if p.get('factory_id') != query_scope.get('factory_id'):
        f.fail('导出作用域不一致', 'factory_id')
    rows = export_rows(db, user, kind, query_scope)
    query = urlencode({k: v for k, v in query_scope.items() if v is not None and k not in {'page', 'page_size'}})
    return envelope(dict(kind=kind, file_name=f'uv-{kind}.csv', generated_at=m.now(), row_count=len(rows),
                         scope_label=query, download_url=f'/api/uv-printing/exports/{kind}?{query}'))


@router.get('/exports/{kind}')
def download_export(kind: str, db: Db, user: User, query_scope: Scope):
    import json
    rows = export_rows(db, user, kind, query_scope)
    keys = sorted({key for row in rows for key in row})
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, keys)
    writer.writeheader()
    def cell(value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        value = '' if value is None else str(value)
        # Text-safe spreadsheet output, including leading-zero identifiers.
        return "'" + value if value[:1] in '=+-@\t\r' or (value.startswith('0') and value.isdigit()) else value
    writer.writerows({key: cell(row.get(key)) for key in keys} for row in rows)
    return Response(buffer.getvalue().encode('utf-8-sig'), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="uv-{kind}.csv"', 'Cache-Control': 'no-store'})


@router.get('/payroll-batches')
def payroll_batches(db: Db, user: User, query_scope: Scope):
    authorize(db, user, query_scope['factory_id'], 'payroll_read')
    return envelope(core.page([f.serial(row) for row in filtered(db, m.UvPayrollBatch, query_scope)], query_scope))


@router.post('/payroll-batches')
def create_payroll(db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    return command(db, user, 'payroll-batch-create', p, ['payroll_read', 'payroll_write'])


@router.post('/payroll-batches/{target_id}/confirm')
def confirm_payroll(target_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('target_id') not in {None, target_id}:
        f.fail('路径和请求批次不一致', 'target_id')
    return command(db, user, 'payroll-batch-confirm', {**p, 'target_id': target_id}, ['payroll_read', 'payroll_write'])


@router.post('/payroll-batches/{target_id}/adjustments')
def adjust_payroll(target_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('target_id') not in {None, target_id}:
        f.fail('路径和请求批次不一致', 'target_id')
    return command(db, user, 'payroll-batch-adjust', {**p, 'target_id': target_id}, ['payroll_read', 'payroll_write'])


@router.post('/periods/{period}/close')
def close_period(period: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
    if p.get('period') not in {None, period}:
        f.fail('路径和请求期间不一致', 'period')
    return command(db, user, 'period-close', {**p, 'period': period}, ['close', 'cost_read', 'cost_write', 'payroll_read'])


@router.post('/imports')
async def upload_import(db: Db, user: User, factory_id: Annotated[str, Form()], kind: Annotated[str, Form()],
                        file: Annotated[UploadFile, File()]):
    if kind not in imports.KINDS:
        f.fail('不支持的导入类型', 'kind')
    authorize(db, user, factory_id, 'import', *imports.KINDS[kind][1])
    content = await file.read(5 * 1024 * 1024 + 1)
    try:
        result = imports.upload(db, factory_id, user.id, kind, file.filename or '', content)
        db.commit()
        return envelope(result)
    except Exception:
        db.rollback()
        raise


def import_access(db, user, factory, target_id):
    authorize(db, user, factory, 'import')
    batch = f.find(db, m.UvImportBatch, factory, target_id)
    authorize(db, user, factory, *imports.KINDS[batch.kind][1])
    return batch


@router.get('/imports/{target_id}/preview')
def import_preview(target_id: str, factory_id: str, db: Db, user: User):
    batch = import_access(db, user, factory_id, target_id)
    output = f.serial(batch)
    if batch.mapping:
        output['normalized_rows'], output['errors'], output['planned_rows'] = imports.validated_preview(db, batch, user.id)
    return envelope(output)


def import_endpoint(action):
    def endpoint(target_id: str, db: Db, user: User, p: Annotated[dict[str, Any], Body()]):
        if p.get('target_id') not in {None, target_id}:
            f.fail('路径和请求批次不一致', 'target_id')
        batch = import_access(db, user, p.get('factory_id'), target_id)
        return command(db, user, 'import-' + action, {**p, 'target_id': target_id}, ['import', *imports.KINDS[batch.kind][1]])
    return endpoint


for _action in ('mapping', 'apply', 'reverse'):
    router.add_api_route('/imports/{target_id}/' + _action, import_endpoint(_action), methods=['POST'], name='uv_import_' + _action)
