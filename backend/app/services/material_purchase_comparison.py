"""Compare reviewed gross-demand evidence, never procurement obligations."""
from fractions import Fraction
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.services import material_purchase as purchase


def fraction(amount):
    return Fraction(int(amount['numerator']), int(amount['denominator']))


def signed_amount(value):
    result = purchase.trial.amount(abs(value))
    if value < 0:
        result['value'] = '-' + result['value']
        result['numerator'] = '-' + result['numerator']
    return result


def compare(before, after):
    # A changed material version, unit or attribute is a removed/added identity,
    # never a guessed replacement or a cross-attribute net quantity.
    old = {purchase.group_key(g): g for g in before['groups']}
    new = {purchase.group_key(g): g for g in after['groups']}
    rows, unchanged = [], 0
    fields = ('material_id', 'material_version', 'code', 'name', 'unit', 'attribute', 'processes', 'base', 'loss', 'gross')
    for key in sorted(old.keys() | new.keys()):
        left, right = old.get(key), new.get(key)
        changes = []
        if left is None: changes.append('ADDED')
        elif right is None: changes.append('REMOVED')
        else:
            if any(fraction(left[f]) != fraction(right[f]) for f in ('base', 'loss', 'gross')): changes.append('QUANTITY')
            if set(left['processes']) != set(right['processes']): changes.append('PROCESS')
            if any(left[f] != right[f] for f in ('code', 'name')): changes.append('DESCRIPTION')
        if not changes:
            unchanged += 1
            continue
        delta = {f: signed_amount((fraction(right[f]) if right else Fraction(0)) -
                                 (fraction(left[f]) if left else Fraction(0))) for f in ('base', 'loss', 'gross')}
        rows.append(dict(source_key=key, changes=changes,
            before={f: left[f] for f in fields} if left else None,
            after={f: right[f] for f in fields} if right else None, delta=delta))
    dates = [dict(process=p, before=before['process_dates'].get(p), after=after['process_dates'].get(p))
             for p in sorted(before['process_dates'].keys() | after['process_dates'].keys())
             if before['process_dates'].get(p) != after['process_dates'].get(p)]
    return dict(status='CURRENT' if before['version'] == after['version'] else 'COMPARED',
        target_version=after['version'], issue=None, rows=rows, dates=dates, unchanged_count=unchanged)


def process_groups(lines, expected):
    """Aggregate frozen occurrence quantities, checking completeness against frozen totals."""
    if not isinstance(lines, list):
        raise ValueError('missing lines')
    groups, totals = {}, {}
    for line in lines:
        process = line['process']
        if not isinstance(process, str) or not process.strip(): raise ValueError('missing process')
        key = purchase.group_key(line)
        amounts = {f: fraction(line[f]) for f in ('base', 'loss', 'gross')}
        if any(v < 0 for v in amounts.values()): raise ValueError('negative source quantity')
        metadata = {f: line[f] for f in ('material_id', 'material_version', 'code', 'name', 'unit', 'attribute')}
        group = groups.setdefault((process, key), dict(metadata, processes=[process], base=Fraction(0), loss=Fraction(0), gross=Fraction(0)))
        total = totals.setdefault(key, dict(processes=set(), base=Fraction(0), loss=Fraction(0), gross=Fraction(0)))
        total['processes'].add(process)
        for field, value in amounts.items():
            group[field] += value
            total[field] += value
    expected_by_key = {purchase.group_key(g): g for g in expected}
    if set(totals) != set(expected_by_key): raise ValueError('incomplete material groups')
    for key, total in totals.items():
        basis = expected_by_key[key]
        if total['processes'] != set(basis['processes']) or any(total[f] != fraction(basis[f]) for f in ('base', 'loss', 'gross')):
            raise ValueError('occurrences do not reconcile to frozen totals')
    result = {}
    for (process, _), group in groups.items():
        result.setdefault(process, []).append(group | {f: purchase.trial.amount(group[f]) for f in ('base', 'loss', 'gross')})
    return result


def compare_processes(before_lines, after_lines, before_totals, after_totals):
    try:
        old = process_groups(before_lines, before_totals)
        new = process_groups(after_lines, after_totals)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return dict(available=False, issue='原版或当前需求缺少完整的工序用量依据，请工程／业务核对。', rows=[], unchanged_count=None)
    rows, unchanged = [], 0
    for process in sorted(old.keys() | new.keys()):
        difference = compare(dict(version=0, groups=old.get(process, []), process_dates={}),
                             dict(version=1, groups=new.get(process, []), process_dates={}))
        rows.extend(dict(row, process=process) for row in difference['rows'])
        unchanged += difference['unchanged_count']
    return dict(available=True, issue=None, rows=rows, unchanged_count=unchanged)


def latest_comparison(db, doc):
    unavailable = dict(status='UNAVAILABLE', target_version=None, rows=[], dates=[], unchanged_count=None)
    row = db.get(purchase.MaterialPlan, doc['data']['demand_id'])
    if row is None or row.factory_id != purchase.FACTORY:
        return dict(unavailable, issue='暂无可比较的本厂已自审需求依据。')
    saved = purchase.workflow.latest(db, row)
    if saved['status'] != purchase.workflow.REVIEWED:
        # Neither private drafts nor unreviewed versions may be projected here.
        return dict(unavailable, issue='当前需求尚未重新自审，待业务完成后再核对差异。')
    original = db.scalar(select(purchase.MaterialPlanEvent).where(
        purchase.MaterialPlanEvent.factory_id == purchase.FACTORY,
        purchase.MaterialPlanEvent.entity_id == row.id,
        purchase.MaterialPlanEvent.version == doc['data']['demand_version']))
    if original is None:
        return dict(unavailable, issue='原需求依据缺失，暂不能比较。')
    original_saved = json.loads(original.result_json)
    original_order = original_saved['inputs'].get('order') or {}
    current_order = saved['inputs'].get('order') or {}
    if not original_order.get('line_id') or original_order.get('line_id') != current_order.get('line_id'):
        return dict(unavailable, issue='需求关联订单已更换，请分别核对，不能作为同一订单变更比较。')
    try:
        current = purchase.source(db, row.id, row.version)
    except HTTPException as error:
        if error.status_code not in (404, 409, 422, 503): raise
        return dict(unavailable, issue=error.detail)
    result = compare(doc['source'], current)
    result['process_comparison'] = compare_processes(original_saved['result'].get('lines'), saved['result'].get('lines'),
                                                     doc['source']['groups'], current['groups'])
    return result
