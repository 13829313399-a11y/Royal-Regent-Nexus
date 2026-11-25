"""Pallet usage statistics and monthly reconciliation export for Shipping Operations."""
from __future__ import annotations

from datetime import date, datetime
import io
import json
import re
from uuid import uuid4

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import or_, select

from app.models.shipping_mail import (
    ShippingGeneratedDoc,
    ShippingLoadingSheet,
    ShippingPalletExclusion,
    ShippingPalletOverride,
    ShippingPalletRecord,
)
from app.services.auth import AuthContext, authorization_decision
from app.services import shipping_loading
from app.services.shipping_mail_service import PERMISSION, SHIPPING_FACTORIES, authorize

FACTORY_LABELS: dict[str, str] = {
    'huaxing': '华兴',
    'huadeng': '华登',
    'huakang-a': '华康 A',
    'huakang-b': '华康 B',
    'huakang-d': '华康 D',
}

SPEC_DEFAULT_PRICES: dict[str, float] = {
    '标准木卡板 (1200×1000)': 65.0,
    '出口熏蒸卡板 (1100×1100)': 75.0,
    '散货周转卡板 (1200×1000)': 55.0,
}


def _spec_for_type(container_type: str, *, is_truck: bool = False) -> tuple[str, float]:
    if is_truck:
        return ('散货周转卡板 (1200×1000)', 55.0)
    upper = (container_type or '').upper()
    if any(token in upper for token in ('40GP', '40ST', '20GP')):
        return ('出口熏蒸卡板 (1100×1100)', 75.0)
    return ('标准木卡板 (1200×1000)', 65.0)


def _num(value: object) -> float:
    if value in (None, '', False):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r'-?\d+(?:\.\d+)?', str(value).strip())
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def _round_qty(value: float) -> int | float:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _json_obj(raw: str | None) -> dict:
    try:
        parsed = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(raw: str | None) -> list:
    try:
        parsed = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _authorized_factories(user: AuthContext) -> list[str]:
    return [
        fid for fid in SHIPPING_FACTORIES
        if authorization_decision(user, PERMISSION['read'], fid)[0]
    ]


def _target_factories(user: AuthContext, factory_id: str) -> tuple[list[str], list[str]]:
    allowed = _authorized_factories(user)
    normalized = (factory_id or 'all').strip().lower()
    if normalized in ('', 'all'):
        if not allowed:
            raise HTTPException(403, '没有船务管理的查看权限')
        return allowed, allowed
    authorize(user, factory_id, 'read')
    return [factory_id], allowed


def _collect_factory_rows(db, factory_id: str) -> tuple[list[dict], int]:
    factory_name = FACTORY_LABELS.get(factory_id, factory_id)
    index = shipping_loading.build_filing_code_index(db, factory_id)

    exclusions = db.scalars(
        select(ShippingPalletExclusion)
        .where(ShippingPalletExclusion.factory_id == factory_id)
    ).all()
    excluded_keys = {(e.source_kind, e.source_id) for e in exclusions}
    suppressed_tasks: set[str] = set()
    suppressed_sos: set[str] = set()
    suppressed_containers: set[str] = set()

    rows: list[dict] = []
    by_task: dict[str, dict] = {}
    by_so: dict[str, dict] = {}
    by_container: dict[str, dict] = {}

    sheets = db.scalars(
        select(ShippingLoadingSheet)
        .where(ShippingLoadingSheet.factory_id == factory_id)
        .order_by(ShippingLoadingSheet.created_at.desc())
    ).all()

    for sheet in sheets:
        header = _json_obj(sheet.header_json)
        lines = _json_list(sheet.lines_json)
        raw_container = str(header.get('containerNo') or '').strip()
        so_no = str(header.get('soNo') or '').strip()
        if ('loading_sheet', sheet.id) in excluded_keys:
            if sheet.task_id:
                suppressed_tasks.add(sheet.task_id)
            if so_no:
                suppressed_sos.add(so_no)
            if raw_container:
                suppressed_containers.add(raw_container)
            continue

        date_str = str(sheet.sheet_date or sheet.created_at or '')[:10]
        container_no = raw_container or (f'{sheet.number}（待补柜号）' if sheet.number else '待补柜号')
        container_type = str(header.get('containerType') or '40HQ').strip() or '40HQ'
        customer = str(
            header.get('brandNote')
            or header.get('consignee')
            or header.get('tradingCompany')
            or ''
        ).strip() or '未标注客户'
        contract_no = str(header.get('contractNo') or '').strip()
        if not contract_no:
            contracts = [str((l or {}).get('contract') or '').strip() for l in lines if isinstance(l, dict)]
            contract_no = ' / '.join(dict.fromkeys(c for c in contracts if c))
        filing_codes = shipping_loading.resolve_filing_codes(
            db, factory_id, header, lines, task_id=sheet.task_id, index=index,
        )
        cartons = sum(_num((l or {}).get('cartons')) for l in lines if isinstance(l, dict))
        pallets = sum(_num((l or {}).get('pallet') or (l or {}).get('boards')) for l in lines if isinstance(l, dict))
        spec, default_price = _spec_for_type(container_type, is_truck=False)

        record = {
            'id': sheet.id,
            'factoryId': factory_id,
            'factoryName': factory_name,
            'date': date_str,
            'month': date_str[:7] if len(date_str) >= 7 else '',
            'customer': customer,
            'containerNo': container_no,
            'hasRealContainerNo': bool(raw_container),
            'containerType': container_type,
            'soNo': so_no,
            'contractNo': contract_no,
            'filingCodes': filing_codes,
            'spec': spec,
            'defaultUnitPrice': default_price,
            'cartons': _round_qty(cartons),
            'pallets': _round_qty(pallets),
            'source': '柜货单',
            'isContainer': True,
            'recordType': 'loading_sheet',
            'editable': False,
            'remark': '',
        }
        rows.append(record)
        if sheet.task_id and sheet.task_id not in by_task:
            by_task[sheet.task_id] = record
        if so_no and so_no not in by_so:
            by_so[so_no] = record
        if raw_container and raw_container not in by_container:
            by_container[raw_container] = record

    docs = db.scalars(
        select(ShippingGeneratedDoc)
        .where(
            ShippingGeneratedDoc.factory_id == factory_id,
            ShippingGeneratedDoc.module.in_(('supplement', 'truck_export')),
        )
        .order_by(ShippingGeneratedDoc.created_at.desc())
    ).all()

    for doc in docs:
        if ('generated_doc', doc.id) in excluded_keys:
            continue
        header = _json_obj(doc.header_json)
        lines = _json_list(doc.lines_json)
        line_dicts = [l for l in lines if isinstance(l, dict)]
        if doc.module == 'supplement':
            pallets = sum(_num(l.get('pallet')) for l in line_dicts)
            cartons = sum(_num(l.get('ctns')) for l in line_dicts)
            raw_container = next((str(l.get('containerNo') or '').strip() for l in line_dicts if str(l.get('containerNo') or '').strip()), '')
            container_type = next((str(l.get('size') or '').strip() for l in line_dicts if str(l.get('size') or '').strip()), '') or '40HQ'
            so_no = next((str(l.get('booking') or '').strip() for l in line_dicts if str(l.get('booking') or '').strip()), '')
            contract_no = str(header.get('invoice') or '').strip() or next(
                (str(l.get('salesConf') or '').strip() for l in line_dicts if str(l.get('salesConf') or '').strip()), '',
            )
            customer = str(
                header.get('customerMarket') or header.get('to') or ''
            ).strip() or '未标注客户'
            date_str = str(header.get('date') or doc.created_at or '')[:10]

            if (
                (doc.task_id and doc.task_id in suppressed_tasks)
                or (so_no and so_no in suppressed_sos)
                or (raw_container and raw_container in suppressed_containers)
            ):
                continue

            existing = (
                (doc.task_id and by_task.get(doc.task_id))
                or (so_no and by_so.get(so_no))
                or (raw_container and by_container.get(raw_container))
                or None
            )
            if existing is not None:
                if pallets > 0:
                    existing['pallets'] = _round_qty(pallets)
                if raw_container and not existing['hasRealContainerNo']:
                    existing['containerNo'] = raw_container
                    existing['hasRealContainerNo'] = True
                if not existing['filingCodes']:
                    existing['filingCodes'] = shipping_loading.resolve_filing_codes(
                        db, factory_id, header, line_dicts, task_id=doc.task_id, index=index,
                    )
                if existing['source'] == '柜货单':
                    existing['source'] = '柜货单 / 补料单'
                continue

            if pallets <= 0 and not raw_container:
                continue

            spec, default_price = _spec_for_type(container_type, is_truck=False)
            filing_codes = shipping_loading.resolve_filing_codes(
                db, factory_id, header, line_dicts, task_id=doc.task_id, index=index,
            )
            rows.append({
                'id': doc.id,
                'factoryId': factory_id,
                'factoryName': factory_name,
                'date': date_str,
                'month': date_str[:7] if len(date_str) >= 7 else '',
                'customer': customer,
                'containerNo': raw_container or so_no or doc.filename,
                'hasRealContainerNo': bool(raw_container),
                'containerType': container_type,
                'soNo': so_no,
                'contractNo': contract_no,
                'filingCodes': filing_codes,
                'spec': spec,
                'defaultUnitPrice': default_price,
                'cartons': _round_qty(cartons),
                'pallets': _round_qty(pallets),
                'source': '补料单',
                'isContainer': True,
                'recordType': 'generated_doc',
                'editable': False,
                'remark': '',
            })
            continue

        # truck_export
        pallets = sum(_num(l.get('boards') or l.get('pallet')) for l in line_dicts)
        if pallets <= 0 and not line_dicts:
            continue
        cartons = sum(_num(l.get('cartons')) for l in line_dicts)
        so_no = str(header.get('bookingNo') or '').strip() or next(
            (str(l.get('so') or '').strip() for l in line_dicts if str(l.get('so') or '').strip()), '',
        )
        contract_no = str(header.get('contractNo') or '').strip() or next(
            (str(l.get('contract') or '').strip() for l in line_dicts if str(l.get('contract') or '').strip()), '',
        )
        customer = str(
            header.get('brandName')
            or next((str(l.get('brand') or '').strip() for l in line_dicts if str(l.get('brand') or '').strip()), '')
            or header.get('tradingHouse')
            or ''
        ).strip() or '未标注客户'
        date_str = str(header.get('sheetDate') or doc.created_at or '')[:10]
        truck_ref = str(header.get('plate') or header.get('vehicle') or doc.filename or '').strip()
        spec, default_price = _spec_for_type(str(header.get('truckType') or ''), is_truck=True)
        filing_codes = shipping_loading.resolve_filing_codes(
            db, factory_id, header, line_dicts, task_id=doc.task_id, index=index,
        )
        rows.append({
            'id': doc.id,
            'factoryId': factory_id,
            'factoryName': factory_name,
            'date': date_str,
            'month': date_str[:7] if len(date_str) >= 7 else '',
            'customer': customer,
            'containerNo': truck_ref,
            'hasRealContainerNo': False,
            'containerType': str(header.get('truckType') or '散货车'),
            'soNo': so_no,
            'contractNo': contract_no,
            'filingCodes': filing_codes,
            'spec': spec,
            'defaultUnitPrice': default_price,
            'cartons': _round_qty(cartons),
            'pallets': _round_qty(pallets),
            'source': '车货单',
            'isContainer': False,
            'recordType': 'generated_doc',
            'editable': False,
            'remark': '',
        })

    manuals = db.scalars(
        select(ShippingPalletRecord)
        .where(ShippingPalletRecord.factory_id == factory_id)
        .order_by(ShippingPalletRecord.ship_date.desc(), ShippingPalletRecord.created_at.desc())
    ).all()
    for rec in manuals:
        spec_val = (rec.spec or '').strip() or '标准木卡板 (1200×1000)'
        unit_price_val = float(rec.unit_price) if rec.unit_price and rec.unit_price > 0 else SPEC_DEFAULT_PRICES.get(spec_val, 65.0)
        ship_date = str(rec.ship_date or '')[:10]
        filing_list = [c.strip() for c in re.split(r'[,，;/、\n]+', rec.filing_codes or '') if c.strip()]
        rows.append({
            'id': rec.id,
            'factoryId': factory_id,
            'factoryName': factory_name,
            'date': ship_date,
            'month': ship_date[:7] if len(ship_date) >= 7 else '',
            'customer': (rec.customer or '').strip() or '未标注客户',
            'containerNo': (rec.container_no or '').strip() or '手动录入',
            'hasRealContainerNo': bool((rec.container_no or '').strip()),
            'containerType': (rec.container_type or '').strip() or '40HQ',
            'soNo': (rec.so_no or '').strip(),
            'contractNo': (rec.contract_no or '').strip(),
            'filingCodes': filing_list,
            'spec': spec_val,
            'defaultUnitPrice': unit_price_val,
            'cartons': _round_qty(float(rec.cartons or 0)),
            'pallets': _round_qty(float(rec.pallets or 0)),
            'source': '手动录入',
            'isContainer': bool(rec.is_container),
            'recordType': 'manual',
            'editable': True,
            'remark': (rec.remark or '').strip(),
        })

    return rows, len(excluded_keys)


def _resolve_period_rows(all_rows: list[dict], *, year: str = '', month: str = '') -> tuple[str, str, list[dict]]:
    today = date.today()
    current_month = today.strftime('%Y-%m')
    raw_year = (year or '').strip()
    raw_month = (month or '').strip()

    if re.fullmatch(r'\d{4}-\d{2}', raw_month):
        return raw_month[:4], raw_month, [r for r in all_rows if r['month'] == raw_month]

    if re.fullmatch(r'\d{4}', raw_year):
        if re.fullmatch(r'\d{1,2}', raw_month) and 1 <= int(raw_month) <= 12:
            ym = f'{raw_year}-{int(raw_month):02d}'
            return raw_year, ym, [r for r in all_rows if r['month'] == ym]
        return raw_year, 'all', [r for r in all_rows if r['date'][:4] == raw_year]

    if raw_year.lower() == 'all' or raw_month.lower() == 'all':
        return 'all', 'all', list(all_rows)

    return str(today.year), current_month, [r for r in all_rows if r['month'] == current_month]


def _matches_search(row: dict, keyword: str) -> bool:
    if not keyword:
        return True
    haystack = ' '.join([
        str(row.get('date') or ''),
        str(row.get('factoryName') or ''),
        str(row.get('customer') or ''),
        str(row.get('containerNo') or ''),
        str(row.get('containerType') or ''),
        str(row.get('soNo') or ''),
        str(row.get('contractNo') or ''),
        ' '.join(row.get('filingCodes') or []),
        str(row.get('spec') or ''),
        str(row.get('source') or ''),
        str(row.get('remark') or ''),
    ]).lower()
    return keyword in haystack


def _apply_override(row: dict, ovr: ShippingPalletOverride | None) -> dict:
    row['originFactoryId'] = row['factoryId']
    row['editable'] = True
    row['estimatedCostOverride'] = None
    row['containerCountOverride'] = None
    if ovr is None:
        return row
    target_fid = (ovr.target_factory_id or '').strip()
    if target_fid:
        row['factoryId'] = target_fid
        row['factoryName'] = FACTORY_LABELS.get(target_fid, target_fid)
    if (ovr.ship_date or '').strip():
        date_val = ovr.ship_date.strip()[:10]
        row['date'] = date_val
        row['month'] = date_val[:7] if len(date_val) >= 7 else ''
    if (ovr.customer or '').strip():
        row['customer'] = ovr.customer.strip()
    if (ovr.container_no or '').strip():
        row['containerNo'] = ovr.container_no.strip()
        row['hasRealContainerNo'] = True
    if (ovr.container_type or '').strip():
        row['containerType'] = ovr.container_type.strip()
    if (ovr.so_no or '').strip():
        row['soNo'] = ovr.so_no.strip()
    if (ovr.contract_no or '').strip():
        row['contractNo'] = ovr.contract_no.strip()
    if (ovr.filing_codes or '').strip():
        row['filingCodes'] = [c.strip() for c in re.split(r'[,，;/、\n]+', ovr.filing_codes) if c.strip()]
    if (ovr.spec or '').strip():
        row['spec'] = ovr.spec.strip()
    if (ovr.remark or '').strip():
        row['remark'] = ovr.remark.strip()
    if ovr.cartons is not None:
        row['cartons'] = _round_qty(float(ovr.cartons))
    if ovr.pallets is not None:
        row['pallets'] = _round_qty(float(ovr.pallets))
    if ovr.unit_price is not None and ovr.unit_price > 0:
        row['defaultUnitPrice'] = round(float(ovr.unit_price), 2)
    if ovr.is_container is not None:
        row['isContainer'] = bool(ovr.is_container)
    if ovr.estimated_cost_override is not None:
        row['estimatedCostOverride'] = round(float(ovr.estimated_cost_override), 2)
    if ovr.container_count_override is not None:
        row['containerCountOverride'] = int(ovr.container_count_override)
    return row


def build_pallet_stats(
    db,
    user: AuthContext,
    *,
    factory_id: str = 'all',
    year: str = '',
    month: str = '',
    customer: str = '',
    unit_price: float | None = None,
    q: str = '',
) -> dict:
    targets, allowed_factories = _target_factories(user, factory_id)
    targets_set = set(targets)
    today = date.today()
    current_month = today.strftime('%Y-%m')
    selected_customer = (customer or '').strip()
    search_text = (q or '').strip()
    search_keyword = search_text.lower()
    override_price = float(unit_price) if unit_price is not None and unit_price > 0 else None

    overrides = db.scalars(
        select(ShippingPalletOverride).where(
            or_(
                ShippingPalletOverride.factory_id.in_(targets),
                ShippingPalletOverride.target_factory_id.in_(targets),
            )
        )
    ).all()
    override_map: dict[tuple[str, str, str], ShippingPalletOverride] = {
        (o.factory_id, o.source_kind, o.source_id): o for o in overrides
    }
    extra_factories = [
        o.factory_id for o in overrides
        if (o.target_factory_id or '') in targets_set and o.factory_id not in targets_set
    ]
    collect_factories = list(dict.fromkeys([*targets, *extra_factories]))

    all_rows: list[dict] = []
    excluded_count = 0
    for fid in collect_factories:
        fid_rows, fid_excluded = _collect_factory_rows(db, fid)
        if fid in targets_set:
            excluded_count += fid_excluded
        for row in fid_rows:
            ovr = override_map.get((row['factoryId'], row['recordType'], row['id']))
            applied = _apply_override(row, ovr)
            if applied['factoryId'] in targets_set:
                all_rows.append(applied)

    available_years = sorted(
        {r['date'][:4] for r in all_rows if len(r['date']) >= 4 and r['date'][:4].isdigit()}
        | {str(today.year + offset) for offset in (1, 0, -1, -2, -3)},
        reverse=True,
    )
    available_months = sorted(
        {r['month'] for r in all_rows if r['month']} | {current_month},
        reverse=True,
    )

    normalized_year, normalized_month, period_rows = _resolve_period_rows(
        all_rows, year=year, month=month,
    )

    available_customers = sorted({r['customer'] for r in period_rows if r['customer']})

    if selected_customer and selected_customer.lower() != 'all':
        customer_rows = [r for r in period_rows if r['customer'] == selected_customer]
        normalized_customer = selected_customer
    else:
        customer_rows = period_rows
        normalized_customer = 'all'

    filtered = [r for r in customer_rows if _matches_search(r, search_keyword)] if search_keyword else customer_rows

    details: list[dict] = []
    group_map: dict[tuple[str, str, str], dict] = {}
    total_pallets = 0.0
    total_cost = 0.0

    for row in filtered:
        price = override_price if override_price is not None else float(row['defaultUnitPrice'])
        pallets = float(row['pallets'] or 0)
        if override_price is None and row.get('estimatedCostOverride') is not None:
            est_cost = round(float(row['estimatedCostOverride']), 2)
        else:
            est_cost = round(pallets * price, 2)
        detail = {
            'id': row['id'],
            'factoryId': row['factoryId'],
            'originFactoryId': row['originFactoryId'],
            'factoryName': row['factoryName'],
            'date': row['date'],
            'customer': row['customer'],
            'containerNo': row['containerNo'],
            'containerType': row['containerType'],
            'soNo': row['soNo'],
            'contractNo': row['contractNo'],
            'filingCodes': row['filingCodes'],
            'spec': row['spec'],
            'cartons': row['cartons'],
            'pallets': row['pallets'],
            'unitPrice': round(price, 2),
            'estimatedCost': est_cost,
            'source': row['source'],
            'isContainer': row['isContainer'],
            'recordType': row['recordType'],
            'editable': row['editable'],
            'remark': row['remark'],
        }
        details.append(detail)
        total_pallets += pallets
        total_cost += est_cost

        container_identity = (
            row['factoryId'],
            row['containerNo'] if (row['containerNo'] or row['soNo']) else row['id'],
            row['soNo'],
        )

        g_key = (row['factoryId'], row['customer'], row['spec'])
        group = group_map.get(g_key)
        if group is None:
            group = {
                'key': f"{row['factoryId']}||{row['customer']}||{row['spec']}",
                'factoryId': row['factoryId'],
                'factoryName': row['factoryName'],
                'customer': row['customer'],
                'spec': row['spec'],
                'unitPrice': round(price, 2),
                'containerCount': 0,
                'totalPallets': 0.0,
                'estimatedCost': 0.0,
                'recordCount': 0,
                '_containers': set(),
                '_has_container_override': False,
                '_explicit_containers': 0,
            }
            group_map[g_key] = group
        group['totalPallets'] += pallets
        group['estimatedCost'] += est_cost
        group['recordCount'] += 1
        if row.get('containerCountOverride') is not None:
            group['_has_container_override'] = True
            group['_explicit_containers'] += int(row['containerCountOverride'])
        elif row['isContainer']:
            group['_containers'].add(container_identity)

    groups: list[dict] = []
    non_overridden_containers: set[tuple[str, str, str]] = set()
    overridden_container_total = 0
    for group in group_map.values():
        c_set = group.pop('_containers')
        has_ovr = group.pop('_has_container_override')
        explicit_cnt = group.pop('_explicit_containers')
        if has_ovr:
            group['containerCount'] = explicit_cnt
            overridden_container_total += explicit_cnt
        else:
            group['containerCount'] = len(c_set)
            non_overridden_containers.update(c_set)
        group['totalPallets'] = _round_qty(group['totalPallets'])
        group['estimatedCost'] = round(group['estimatedCost'], 2)
        groups.append(group)

    total_container_count = len(non_overridden_containers) + overridden_container_total

    groups.sort(key=lambda g: (-float(g['totalPallets']), g['customer'], g['factoryName'], g['spec']))
    details.sort(key=lambda d: (d['date'], d['factoryName'], d['customer'], d['containerNo']), reverse=True)

    return {
        'year': normalized_year,
        'month': normalized_month,
        'factoryId': (factory_id or 'all') if (factory_id or 'all').lower() != 'all' else 'all',
        'customer': normalized_customer,
        'q': search_text,
        'availableFactories': [
            {'id': fid, 'name': FACTORY_LABELS.get(fid, fid)} for fid in allowed_factories
        ],
        'availableCustomers': available_customers,
        'availableYears': available_years,
        'availableMonths': available_months,
        'excludedCount': excluded_count,
        'summary': {
            'totalPallets': _round_qty(total_pallets),
            'totalContainers': total_container_count,
            'estimatedCost': round(total_cost, 2),
            'recordCount': len(details),
            'customerCount': len({d['customer'] for d in details}),
        },
        'groups': groups,
        'details': details,
    }


def export_pallet_reconciliation_xlsx(
    db,
    user: AuthContext,
    *,
    factory_id: str = 'all',
    year: str = '',
    month: str = '',
    customer: str = '',
    unit_price: float | None = None,
    q: str = '',
) -> tuple[str, bytes]:
    stats = build_pallet_stats(
        db, user, factory_id=factory_id, year=year, month=month, customer=customer, unit_price=unit_price, q=q,
    )
    wb = Workbook()
    header_fill = PatternFill(fill_type='solid', fgColor='006559')
    header_font = Font(name='Microsoft YaHei', size=10, bold=True, color='FFFFFF')
    title_font = Font(name='Microsoft YaHei', size=13, bold=True, color='0D1A23')
    body_font = Font(name='Microsoft YaHei', size=10, color='0D1A23')
    bold_font = Font(name='Microsoft YaHei', size=10, bold=True, color='0D1A23')
    thin = Side(style='thin', color='D5E0E2')
    cell_border = Border(top=thin, right=thin, bottom=thin, left=thin)

    # Sheet 1: 汇总
    ws1 = wb.active
    ws1.title = '月度汇总'
    if stats['month'] != 'all':
        title_text = f"卡板月度对账单 · {stats['month']}"
        filename = f"卡板月度对账_{stats['month']}.xlsx"
    elif stats['year'] != 'all':
        title_text = f"卡板年度对账单 · {stats['year']}全年"
        filename = f"卡板年度对账_{stats['year']}全年.xlsx"
    else:
        title_text = '卡板累计对账单 · 全部年份'
        filename = '卡板对账_全部.xlsx'

    factory_label = '全部厂区' if stats['factoryId'] == 'all' else FACTORY_LABELS.get(stats['factoryId'], stats['factoryId'])
    customer_label = '全部客户' if stats['customer'] == 'all' else stats['customer']
    q_part = f"　关键词：{stats['q']}" if stats.get('q') else ''
    ws1['A1'] = title_text
    ws1['A1'].font = title_font
    ws1['A2'] = (
        f"厂区：{factory_label}　客户：{customer_label}{q_part}　"
        f"总用板数：{stats['summary']['totalPallets']} 块　"
        f"总柜数：{stats['summary']['totalContainers']} 柜　"
        f"预估总费用：¥{stats['summary']['estimatedCost']:,.2f}"
    )
    ws1['A2'].font = Font(name='Microsoft YaHei', size=10, color='5A6C74')

    s1_headers = ['厂区', '客户', '卡板规格', '柜数', '用板数（块）', '参考单价（元）', '预估费用（元）']
    ws1.append([])
    ws1.append(s1_headers)
    header_row = 4
    for col_idx in range(1, len(s1_headers) + 1):
        cell = ws1.cell(header_row, col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = cell_border

    for grp in stats['groups']:
        ws1.append([
            grp['factoryName'], grp['customer'], grp['spec'],
            grp['containerCount'], grp['totalPallets'], grp['unitPrice'], grp['estimatedCost'],
        ])

    sum_row_1 = header_row + len(stats['groups']) + 1
    ws1.append([
        '合计', '', '',
        stats['summary']['totalContainers'],
        stats['summary']['totalPallets'],
        '',
        stats['summary']['estimatedCost'],
    ])
    for r in range(header_row + 1, sum_row_1 + 1):
        is_total = r == sum_row_1
        for c in range(1, len(s1_headers) + 1):
            cell = ws1.cell(r, c)
            cell.font = bold_font if is_total else body_font
            cell.border = cell_border
            if c in (4, 5, 6, 7):
                cell.alignment = Alignment(horizontal='right', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')
            if c in (6, 7) and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'
    for idx, w in enumerate((12, 22, 26, 10, 14, 15, 16), start=1):
        ws1.column_dimensions[get_column_letter(idx)].width = w

    # Sheet 2: 柜号明细
    ws2 = wb.create_sheet('柜号明细')
    s2_headers = [
        '出货日期', '厂区', '客户', '柜号 / 车次', '柜型', 'SO号',
        '合同号', '备案货号', '卡板规格', '箱数', '用板数（块）',
        '参考单价（元）', '预估费用（元）', '来源单据', '备注',
    ]
    ws2.append(s2_headers)
    for col_idx in range(1, len(s2_headers) + 1):
        cell = ws2.cell(1, col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = cell_border

    for item in stats['details']:
        ws2.append([
            item['date'], item['factoryName'], item['customer'], item['containerNo'],
            item['containerType'], item['soNo'], item['contractNo'],
            ', '.join(item['filingCodes']), item['spec'], item['cartons'],
            item['pallets'], item['unitPrice'], item['estimatedCost'], item['source'],
            item.get('remark', ''),
        ])

    sum_row_2 = len(stats['details']) + 2
    ws2.append([
        '合计', '', '', f"{stats['summary']['totalContainers']} 柜", '', '', '', '', '',
        _round_qty(sum(float(d['cartons'] or 0) for d in stats['details'])),
        stats['summary']['totalPallets'],
        '',
        stats['summary']['estimatedCost'],
        '', '',
    ])
    for r in range(2, sum_row_2 + 1):
        is_total = r == sum_row_2
        for c in range(1, len(s2_headers) + 1):
            cell = ws2.cell(r, c)
            cell.font = bold_font if is_total else body_font
            cell.border = cell_border
            if c in (10, 11, 12, 13):
                cell.alignment = Alignment(horizontal='right', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')
            if c in (12, 13) and isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.00'
    for idx, w in enumerate((13, 10, 20, 20, 10, 16, 16, 20, 24, 10, 13, 14, 15, 16, 22), start=1):
        ws2.column_dimensions[get_column_letter(idx)].width = w

    buffer = io.BytesIO()
    wb.save(buffer)
    return filename, buffer.getvalue()


def _validate_manual_payload(user: AuthContext, payload: dict, *, default_factory: str = '') -> dict:
    factory_id = str(payload.get('factory_id') or default_factory or '').strip()
    authorize(user, factory_id, 'write')

    ship_date = str(payload.get('ship_date') or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', ship_date):
        raise HTTPException(422, '出货日期格式必须为 YYYY-MM-DD')
    try:
        date.fromisoformat(ship_date)
    except ValueError as exc:
        raise HTTPException(422, '出货日期无效') from exc

    customer = str(payload.get('customer') or '').strip()
    if not customer:
        raise HTTPException(422, '请填写客户名称')

    pallets = _num(payload.get('pallets'))
    if pallets < 0:
        raise HTTPException(422, '用板数不能为负数')
    cartons = _num(payload.get('cartons'))
    if cartons < 0:
        raise HTTPException(422, '箱数不能为负数')

    spec = str(payload.get('spec') or '').strip() or '标准木卡板 (1200×1000)'
    container_type = str(payload.get('container_type') or '').strip() or '40HQ'

    raw_price = payload.get('unit_price')
    if raw_price in (None, ''):
        unit_price = SPEC_DEFAULT_PRICES.get(spec, 65.0)
    else:
        unit_price = float(raw_price)
        if unit_price < 0:
            raise HTTPException(422, '参考单价不能为负数')
        if unit_price == 0:
            unit_price = SPEC_DEFAULT_PRICES.get(spec, 65.0)

    raw_is_container = payload.get('is_container')
    if raw_is_container is None:
        is_container = 0 if ('散货' in spec or '散货' in container_type or '车' in container_type) else 1
    else:
        is_container = 1 if bool(raw_is_container) else 0

    return {
        'factory_id': factory_id,
        'ship_date': ship_date,
        'customer': customer[:120],
        'container_no': str(payload.get('container_no') or '').strip()[:120],
        'container_type': container_type[:40],
        'so_no': str(payload.get('so_no') or '').strip()[:80],
        'contract_no': str(payload.get('contract_no') or '').strip()[:120],
        'filing_codes': str(payload.get('filing_codes') or '').strip()[:300],
        'spec': spec[:120],
        'cartons': cartons,
        'pallets': pallets,
        'unit_price': round(unit_price, 2),
        'is_container': is_container,
        'remark': str(payload.get('remark') or '').strip()[:300],
    }


def _serialize_manual_record(rec: ShippingPalletRecord) -> dict:
    return {
        'id': rec.id,
        'factoryId': rec.factory_id,
        'factoryName': FACTORY_LABELS.get(rec.factory_id, rec.factory_id),
        'shipDate': rec.ship_date,
        'customer': rec.customer,
        'containerNo': rec.container_no,
        'containerType': rec.container_type,
        'soNo': rec.so_no,
        'contractNo': rec.contract_no,
        'filingCodes': [c.strip() for c in re.split(r'[,，;/、\n]+', rec.filing_codes or '') if c.strip()],
        'spec': rec.spec,
        'cartons': _round_qty(rec.cartons),
        'pallets': _round_qty(rec.pallets),
        'unitPrice': round(rec.unit_price, 2),
        'isContainer': bool(rec.is_container),
        'remark': rec.remark,
        'createdAt': rec.created_at,
        'updatedAt': rec.updated_at,
    }


def create_manual_pallet_record(db, user: AuthContext, payload: dict) -> dict:
    clean = _validate_manual_payload(user, payload)
    now = datetime.now().isoformat(timespec='seconds')
    rec = ShippingPalletRecord(
        id=f'pallet-{uuid4().hex[:12]}',
        factory_id=clean['factory_id'],
        ship_date=clean['ship_date'],
        customer=clean['customer'],
        container_no=clean['container_no'],
        container_type=clean['container_type'],
        so_no=clean['so_no'],
        contract_no=clean['contract_no'],
        filing_codes=clean['filing_codes'],
        spec=clean['spec'],
        cartons=clean['cartons'],
        pallets=clean['pallets'],
        unit_price=clean['unit_price'],
        is_container=clean['is_container'],
        remark=clean['remark'],
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _serialize_manual_record(rec)


def _get_or_create_override(
    db,
    origin_factory_id: str,
    source_kind: str,
    source_id: str,
    user_id: str,
    now: str,
) -> ShippingPalletOverride:
    ovr = db.scalar(
        select(ShippingPalletOverride).where(
            ShippingPalletOverride.factory_id == origin_factory_id,
            ShippingPalletOverride.source_kind == source_kind,
            ShippingPalletOverride.source_id == source_id,
        )
    )
    if ovr is None:
        ovr = ShippingPalletOverride(
            id=f'povr-{uuid4().hex[:12]}',
            factory_id=origin_factory_id,
            source_kind=source_kind,
            source_id=source_id,
            updated_by=user_id,
            updated_at=now,
        )
        db.add(ovr)
    else:
        ovr.updated_by = user_id
        ovr.updated_at = now
    return ovr


def _delete_overrides(db, source_kind: str, source_id: str) -> None:
    rows = db.scalars(
        select(ShippingPalletOverride).where(
            ShippingPalletOverride.source_kind == source_kind,
            ShippingPalletOverride.source_id == source_id,
        )
    ).all()
    for row in rows:
        db.delete(row)


def update_manual_pallet_record(db, user: AuthContext, record_id: str, payload: dict) -> dict:
    rec_type = str(payload.get('record_type') or 'manual').strip() or 'manual'
    if rec_type not in ('manual', 'loading_sheet', 'generated_doc'):
        raise HTTPException(422, '无效的记录类型')

    now = datetime.now().isoformat(timespec='seconds')
    if rec_type == 'manual':
        rec = db.get(ShippingPalletRecord, record_id)
        if rec is None:
            raise HTTPException(404, '未找到对应的手动卡板记录')
        authorize(user, rec.factory_id, 'write')
        clean = _validate_manual_payload(user, payload, default_factory=rec.factory_id)
        rec.factory_id = clean['factory_id']
        rec.ship_date = clean['ship_date']
        rec.customer = clean['customer']
        rec.container_no = clean['container_no']
        rec.container_type = clean['container_type']
        rec.so_no = clean['so_no']
        rec.contract_no = clean['contract_no']
        rec.filing_codes = clean['filing_codes']
        rec.spec = clean['spec']
        rec.cartons = clean['cartons']
        rec.pallets = clean['pallets']
        rec.unit_price = clean['unit_price']
        rec.is_container = clean['is_container']
        rec.remark = clean['remark']
        rec.updated_at = now
        _delete_overrides(db, 'manual', record_id)
        db.commit()
        db.refresh(rec)
        return _serialize_manual_record(rec)

    source_row = (
        db.get(ShippingLoadingSheet, record_id)
        if rec_type == 'loading_sheet'
        else db.get(ShippingGeneratedDoc, record_id)
    )
    if source_row is None:
        raise HTTPException(404, '未找到对应的同步出货记录')
    origin_factory_id = source_row.factory_id
    authorize(user, origin_factory_id, 'write')
    clean = _validate_manual_payload(user, payload, default_factory=origin_factory_id)

    ovr = _get_or_create_override(db, origin_factory_id, rec_type, record_id, user.id, now)
    ovr.target_factory_id = clean['factory_id']
    ovr.ship_date = clean['ship_date']
    ovr.customer = clean['customer']
    ovr.container_no = clean['container_no']
    ovr.container_type = clean['container_type']
    ovr.so_no = clean['so_no']
    ovr.contract_no = clean['contract_no']
    ovr.filing_codes = clean['filing_codes']
    ovr.spec = clean['spec']
    ovr.cartons = clean['cartons']
    ovr.pallets = clean['pallets']
    ovr.unit_price = clean['unit_price']
    ovr.is_container = clean['is_container']
    ovr.remark = clean['remark']
    ovr.estimated_cost_override = None
    ovr.container_count_override = None
    db.commit()
    db.refresh(ovr)
    return {
        'id': record_id,
        'factoryId': clean['factory_id'],
        'originFactoryId': origin_factory_id,
        'factoryName': FACTORY_LABELS.get(clean['factory_id'], clean['factory_id']),
        'shipDate': clean['ship_date'],
        'customer': clean['customer'],
        'containerNo': clean['container_no'],
        'containerType': clean['container_type'],
        'soNo': clean['so_no'],
        'contractNo': clean['contract_no'],
        'filingCodes': [c.strip() for c in re.split(r'[,，;/、\n]+', clean['filing_codes']) if c.strip()],
        'spec': clean['spec'],
        'cartons': _round_qty(clean['cartons']),
        'pallets': _round_qty(clean['pallets']),
        'unitPrice': clean['unit_price'],
        'isContainer': bool(clean['is_container']),
        'remark': clean['remark'],
        'updatedAt': ovr.updated_at,
    }


def update_pallet_group(db, user: AuthContext, payload: dict) -> dict:
    items = payload.get('items') or []
    if not items:
        raise HTTPException(422, '缺少待修改的汇总记录明细')

    target_factory_id = str(payload.get('factory_id') or '').strip()
    authorize(user, target_factory_id, 'write')

    customer = str(payload.get('customer') or '').strip()
    if not customer:
        raise HTTPException(422, '请填写客户名称')
    spec = str(payload.get('spec') or '').strip()
    if not spec:
        raise HTTPException(422, '请填写卡板规格')

    raw_containers = _num(payload.get('container_count'))
    if raw_containers < 0:
        raise HTTPException(422, '柜数不能为负数')
    container_count = int(round(raw_containers))

    total_pallets = _num(payload.get('total_pallets'))
    if total_pallets < 0:
        raise HTTPException(422, '用板数不能为负数')

    unit_price = _num(payload.get('unit_price'))
    if unit_price < 0:
        raise HTTPException(422, '参考单价不能为负数')

    cost_overridden = bool(payload.get('cost_overridden'))
    est_cost_val: float | None = None
    if cost_overridden:
        est_cost_val = _num(payload.get('estimated_cost'))
        if est_cost_val < 0:
            raise HTTPException(422, '预估费用不能为负数')
        est_cost_val = round(est_cost_val, 2)

    normalized_items: list[tuple[str, str, str]] = []
    for raw in items:
        rec_id = str(raw.get('id') or '').strip()
        orig_fid = str(
            raw.get('origin_factory_id')
            or raw.get('originFactoryId')
            or raw.get('factory_id')
            or raw.get('factoryId')
            or ''
        ).strip()
        rec_type = str(raw.get('record_type') or raw.get('recordType') or '').strip()
        if not rec_id or not orig_fid or rec_type not in ('manual', 'loading_sheet', 'generated_doc'):
            raise HTTPException(422, '汇总记录缺少有效来源标识')
        authorize(user, orig_fid, 'write')
        normalized_items.append((rec_id, orig_fid, rec_type))

    now = datetime.now().isoformat(timespec='seconds')
    updated = 0
    for idx, (rec_id, orig_fid, rec_type) in enumerate(normalized_items):
        is_primary = idx == 0
        row_pallets = total_pallets if is_primary else 0.0
        row_containers = container_count if is_primary else 0
        row_cost_ovr = est_cost_val if (is_primary and cost_overridden) else (0.0 if cost_overridden else None)

        if rec_type == 'manual':
            rec = db.get(ShippingPalletRecord, rec_id)
            if rec is None:
                continue
            rec.factory_id = target_factory_id
            rec.customer = customer[:120]
            rec.spec = spec[:120]
            rec.pallets = row_pallets
            rec.unit_price = round(unit_price, 2)
            rec.updated_at = now
            if orig_fid != target_factory_id:
                _delete_overrides(db, 'manual', rec_id)
            ovr = _get_or_create_override(db, target_factory_id, 'manual', rec_id, user.id, now)
            ovr.target_factory_id = target_factory_id
            ovr.customer = customer[:120]
            ovr.spec = spec[:120]
            ovr.pallets = row_pallets
            ovr.unit_price = round(unit_price, 2)
            ovr.container_count_override = row_containers
            ovr.estimated_cost_override = row_cost_ovr
            updated += 1
        else:
            ovr = _get_or_create_override(db, orig_fid, rec_type, rec_id, user.id, now)
            ovr.target_factory_id = target_factory_id
            ovr.customer = customer[:120]
            ovr.spec = spec[:120]
            ovr.pallets = row_pallets
            ovr.unit_price = round(unit_price, 2)
            ovr.container_count_override = row_containers
            ovr.estimated_cost_override = row_cost_ovr
            updated += 1

    db.commit()
    return {'updatedCount': updated}


def batch_delete_pallet_records(db, user: AuthContext, items: list[dict]) -> dict:
    if not items:
        raise HTTPException(422, '请先选择要删除的卡板记录')

    normalized: list[tuple[str, str, str]] = []
    for raw in items:
        rec_id = str(raw.get('id') or '').strip()
        orig_fid = str(
            raw.get('origin_factory_id')
            or raw.get('originFactoryId')
            or raw.get('factory_id')
            or raw.get('factoryId')
            or ''
        ).strip()
        curr_fid = str(raw.get('factory_id') or raw.get('factoryId') or orig_fid).strip()
        rec_type = str(raw.get('record_type') or raw.get('recordType') or '').strip()
        if not rec_id or not orig_fid or rec_type not in ('manual', 'loading_sheet', 'generated_doc'):
            raise HTTPException(422, '删除项缺少有效标识或记录类型')
        authorize(user, orig_fid, 'write')
        if curr_fid and curr_fid != orig_fid:
            authorize(user, curr_fid, 'write')
        normalized.append((rec_id, orig_fid, rec_type))

    now = datetime.now().isoformat(timespec='seconds')
    deleted_manual = 0
    excluded_sync = 0
    seen_manual: set[tuple[str, str]] = set()
    seen_exclusions: set[tuple[str, str, str]] = set()

    for rec_id, orig_fid, rec_type in normalized:
        if rec_type == 'manual':
            if (orig_fid, rec_id) in seen_manual:
                continue
            seen_manual.add((orig_fid, rec_id))
            rec = db.get(ShippingPalletRecord, rec_id)
            if rec is not None:
                authorize(user, rec.factory_id, 'write')
                db.delete(rec)
                _delete_overrides(db, 'manual', rec_id)
                deleted_manual += 1
        else:
            key = (orig_fid, rec_type, rec_id)
            if key in seen_exclusions:
                continue
            seen_exclusions.add(key)
            _delete_overrides(db, rec_type, rec_id)
            existing = db.scalar(
                select(ShippingPalletExclusion).where(
                    ShippingPalletExclusion.factory_id == orig_fid,
                    ShippingPalletExclusion.source_kind == rec_type,
                    ShippingPalletExclusion.source_id == rec_id,
                )
            )
            if existing is None:
                db.add(ShippingPalletExclusion(
                    id=f'pex-{uuid4().hex[:12]}',
                    factory_id=orig_fid,
                    source_kind=rec_type,
                    source_id=rec_id,
                    excluded_by=user.id,
                    excluded_at=now,
                ))
                excluded_sync += 1

    db.commit()
    return {
        'deletedManualCount': deleted_manual,
        'excludedSyncCount': excluded_sync,
        'totalRemoved': deleted_manual + excluded_sync,
    }


def restore_excluded_pallet_records(db, user: AuthContext, factory_id: str = 'all') -> dict:
    normalized = (factory_id or 'all').strip().lower()
    if normalized in ('', 'all'):
        targets = [
            fid for fid in SHIPPING_FACTORIES
            if authorization_decision(user, PERMISSION['read'], fid)[0]
            and authorization_decision(user, PERMISSION['write'], fid)[0]
        ]
        if not targets:
            raise HTTPException(403, '没有船务管理的编辑权限')
    else:
        authorize(user, factory_id, 'write')
        targets = [factory_id]

    exclusions = db.scalars(
        select(ShippingPalletExclusion).where(ShippingPalletExclusion.factory_id.in_(targets))
    ).all()
    restored = len(exclusions)
    for row in exclusions:
        db.delete(row)
    db.commit()
    return {'restoredCount': restored}
