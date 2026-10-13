"""Order-scoped draft and published preplans, under the cutting factory lock."""
from copy import deepcopy
from datetime import UTC, datetime, date, timedelta
from zoneinfo import ZoneInfo
from app.models.cutting_ops import CuttingMaster
from app.services.cutting_schemas import WorkCalendar
from app.services import cutting_ops as c, cutting_orders as orders
from app.services.cutting_planning_schemas import SavePlan, PlanTask


def basis(data):
    bom = data.get('bom')
    return dict(issue_date_rule='adjustable_preparation_v4', dispatch_id=data['dispatch_id'], bom_id=bom['id'] if bom else None,
                bom_version=bom['version'] if bom else None, target_sets=data.get('target_sets'),
                requisition=data.get('requisition'), batches=data.get('batches', []))


def stale(plan, data):
    return bool(plan and (plan['basis'] != basis(data) or data.get('purchase_reconciliation_required')))


def resource_changed(db, plan):
    if not plan:
        return False
    for task in plan['tasks']:
        resource = db.get(CuttingMaster, task['resource_id'])
        if not resource or resource.factory_id != c.FACTORY or resource.version != task['resource_version'] or c.view(db, resource)['status'] != 'active':
            return True
    return False


def summary(db, data, needs_receipt=False):
    planning = data.get('planning', {})
    references_invalid = False
    if data.get('bom') and planning:
        for requirement in data['bom']['data']['requirements']:
            material = db.get(CuttingMaster, requirement['material_id'])
            if not material or c.view(db, material)['status'] != 'active':
                references_invalid = True
                break
    published = planning.get('published')
    draft = planning.get('draft')
    result = dict(published_stale=bool(published and (needs_receipt or references_invalid or stale(published, data) or resource_changed(db, published))),
                draft_stale=bool(draft and (needs_receipt or references_invalid or stale(draft, data) or resource_changed(db, draft))),
                published_version=published['version'] if published else None,
                draft_version=draft['version'] if draft else None)
    current = draft or published
    planned = sum(t.get('planned_sets', sum(d['sets'] for d in t['days'])) for t in current['tasks']) if current else 0
    states = []
    if not planned: states.append('unplanned')
    if planned and planned < (data.get('target_sets') or 0): states.append('partial')
    if published and not result['published_stale']: states.append('published')
    if published and not result['published_stale'] and any(t.get('actual_review_pending', True) for t in published['tasks']): states.append('pending_actual')
    if result['published_stale'] or result['draft_stale']: states.append('review')
    result['states'] = states
    return result


# Confirmed fallback: Monday through Saturday; readiness day itself is excluded.
DEFAULT_WEEKDAYS = [1, 2, 3, 4, 5, 6]


def working(day, calendar):
    exception = next((e for e in calendar.exceptions if e.day == day), None)
    return exception.working if exception else day.isoweekday() in calendar.weekdays


def first_supply(ready_date, calendar, preparation_workdays=3):
    day, count = ready_date, 0
    # At least one workday per week; each rest exception can remove at most one.
    search_days = 7 * (max(1, preparation_workdays) + len(calendar.exceptions) + 1)
    # Zero permits the ready day when working; otherwise use the next workday.
    if preparation_workdays == 0:
        for _ in range(search_days):
            if working(day, calendar):
                return day
            day += timedelta(days=1)
        c.require(False, '日历内无足够工作日，请核对', 422)
    # Positive intervals exclude readiness itself; three is only the default.
    for _ in range(search_days):
        day += timedelta(days=1)
        count += int(working(day, calendar))
        if count == preparation_workdays:
            return day
    c.require(False, '日历内无足够工作日，请核对', 422)


def evaluate_dates(task, ref, mandatory):
    configured = ref['data'].get('calendar')
    calendar = WorkCalendar.model_validate(configured) if configured else WorkCalendar(
        weekdays=DEFAULT_WEEKDAYS, basis='未配置资源日历，默认周一至周六工作、周日休息', exceptions=[])
    # Only current-cutting-required material estimates participate in advance scheduling.
    ready = {r.row: r.expected_date for r in task.materials if r.expected_date and r.row in mandatory}
    estimated_dates = list(ready.values())
    if task.prerequisite_date:
        estimated_dates.append(task.prerequisite_date)
    estimated_ready = max(estimated_dates) if estimated_dates and mandatory <= set(ready) and (not task.prerequisite_required or task.prerequisite_date) else None
    estimated_supply = first_supply(estimated_ready, calendar, task.preparation_workdays) if estimated_ready else None
    # Actual verification never substitutes purchase promises or planned prerequisite dates.
    actual_dates = [task.actual_issue_date] if task.actual_issue_date else []
    if task.actual_prerequisite_date:
        actual_dates.append(task.actual_prerequisite_date)
    actual_complete = bool(task.actual_issue_date) and (not task.prerequisite_required or bool(task.actual_prerequisite_date))
    actual_ready = max(actual_dates) if actual_dates and actual_complete else None
    actual_supply = first_supply(actual_ready, calendar, task.preparation_workdays) if actual_ready else None
    earliest = actual_supply if task.date_basis == 'actual' else estimated_supply
    if task.days:
        c.require(earliest is not None,
            '提前预排须补齐当前必需料预计日期；实际核定须补齐实际领料及前置工序凭据', 422)
        for day in task.days:
            c.require(day.day >= earliest, '日计划供数早于当前准备周期推算日，请核对或调整供数准备工作日', 422)
            c.require(working(day.day, calendar), '日计划日期为休息日，请核对资源日历', 422)
    return dict(earliest_supply_date=earliest.isoformat() if earliest else None,
                estimated_readiness_date=estimated_ready.isoformat() if estimated_ready else None,
                estimated_supply_date=estimated_supply.isoformat() if estimated_supply else None,
                actual_readiness_date=actual_ready.isoformat() if actual_ready else None,
                actual_supply_date=actual_supply.isoformat() if actual_supply else None,
                readiness_date=(actual_ready if task.date_basis == 'actual' else estimated_ready).isoformat() if earliest else None,
                calendar=calendar.model_dump(mode='json'),
                calendar_source='resource' if configured else 'default_workweek',
                readiness_kind='actual_review' if task.date_basis == 'actual' else 'advance_estimate',
                actual_review_pending=task.date_basis != 'actual' or actual_ready is None)


def business_today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


def previous_plan(data):
    planning = data.get('planning', {})
    return planning.get('draft') or planning.get('published') or {}


def validate_removals(data, body):
    previous = {t['task_id']: t for t in previous_plan(data).get('tasks', [])}
    new_ids = {t.task_id for t in body.tasks}
    removed = set(previous) - new_ids
    published_removed = {t['task_id'] for t in (data.get('planning', {}).get('published') or {}).get('tasks', [])} - new_ids
    c.require(set(body.removed_task_reasons) <= removed | published_removed, '取消任务依据只能对应本次移除的原任务', 422)
    reasons = removal_reasons(data, body)
    for task_id in removed:
        old = previous[task_id]
        required = old.get('prerequisite_required') or old.get('prerequisite_date') or old.get('actual_prerequisite_date')
        c.require(not required or reasons.get(task_id), '移除有前置工序要求的原任务须填写取消依据；更换执行方请保留原任务', 422)
    validate_published_removals(data.get('planning', {}), dict(tasks=[t.model_dump(mode='json') for t in body.tasks], removed_task_reasons=reasons))


def removal_reasons(data, body):
    reasons = dict(previous_plan(data).get('removed_task_reasons', {})) if data.get('planning', {}).get('draft') else {}
    reasons.update(body.removed_task_reasons)
    new_ids = {t.task_id for t in body.tasks}
    for old in previous_plan(data).get('tasks', []):
        if old['task_id'] not in new_ids and len(old.get('prerequisite_change_reason', '').strip()) >= 4:
            reasons.setdefault(old['task_id'], old['prerequisite_change_reason'])
    for task_id in new_ids: reasons.pop(task_id, None)
    return reasons


def validate_published_removals(planning, draft):
    remaining = {t['task_id'] for t in draft['tasks']}
    for old in (planning.get('published') or {}).get('tasks', []):
        required = old.get('prerequisite_required') or old.get('prerequisite_date') or old.get('actual_prerequisite_date')
        if required and old['task_id'] not in remaining:
            reason = draft.get('removed_task_reasons', {}).get(old['task_id'], '')
            c.require(len(reason.strip()) >= 4, '原发布计划的前置任务已被移除，须重新保存草稿并补齐取消依据', 422)


def validate_tasks(db, data, tasks):
    c.require(data.get('bom'), '请先由工程关联已发布 BOM')
    c.require(not data.get('purchase_reconciliation_required'), '旧采购需求待核对，暂不能编制新计划')
    c.require(sum(t.target_sets for t in tasks) <= data['target_sets'], '任务分配合计超过工程确认的订单目标套数', 422)
    c.validate_references(db, data['bom']['data'], publishing=True)
    requirements = data['bom']['data']['requirements']
    mandatory = {i for i, r in enumerate(requirements) if r['required_for_cutting']}
    result = []
    previous = {t['task_id']: t for t in previous_plan(data).get('tasks', [])}
    published = {t['task_id']: t for t in (data.get('planning', {}).get('published') or {}).get('tasks', [])}
    for task in tasks:
        old = previous.get(task.task_id)
        prior = published.get(task.task_id)
        old_required = any(t and (t.get('prerequisite_required') or t.get('prerequisite_date') or t.get('actual_prerequisite_date')) for t in (old, prior))
        c.require(not old_required or task.prerequisite_required or len(task.prerequisite_change_reason) >= 4,
                  '取消原任务前置工序要求须明确填写核对依据，不可仅清空日期', 422)
        executor_changed = any(t and t['resource_id'] != task.resource_id for t in (old, prior))
        c.require(not executor_changed or not (task.actual_issue_date or task.actual_prerequisite_date) or len(task.resource_change_basis) >= 4,
                  '更换执行方后的实际凭据须填写复核依据（至少4字）', 422)
        c.require(task.actual_prerequisite_date is None or task.actual_prerequisite_date <= business_today(), '前置工序实际就绪日期不能晚于今天（上海时间）', 422)
        c.require(task.actual_issue_date is None or task.actual_issue_date <= business_today(), '实际领料日期不能晚于今天（上海时间）', 422)
        resource = c.master(db, task.resource_id)
        c.require(resource.kind == 'resource', '执行方必须来自本厂／外发裁剪资源', 422)
        ref = c.view(db, resource)
        c.require(ref['version'] == task.resource_version and ref['status'] == 'active', '执行方或日历已变更，请重新选择当前有效版本')
        rows = {m.row for m in task.materials}
        c.require(rows <= set(range(len(requirements))), '计划引用的物料行不属于当前 BOM', 422)
        if task.days and task.date_basis == 'estimated':
            requisition = data.get('requisition')
            c.require(requisition, '请先由工程提交当前物料需求，再依据采购交期预排', 422)
            for row in mandatory:
                demand = next(r for r in requisition['lines'] if r['row'] == row)
                if demand.get('purchase_mode') == 'no_purchase':
                    continue
                replies = [b for b in data.get('batches', []) if b['row'] == row]
                c.require(replies, '当前裁剪必需采购料尚无交期回复，请先由采购回复', 422)
                expected = next((r.expected_date for r in task.materials if r.row == row), None)
                c.require(expected is not None and expected >= min(date.fromisoformat(b['expected_date']) for b in replies),
                          '必需料预计就绪日不得早于采购最早回复日；数量支持范围需核对依据', 422)
        if task.days:
            c.require(task.readiness_basis, '请填写该批次物料日期及数量支持依据；不采购不等于可用库存', 422)
        record = task.model_dump(mode='json')
        record['resource'] = ref
        record.update(evaluate_dates(task, ref, mandatory))
        record['planned_sets'] = sum(d.sets for d in task.days)
        record['unplanned_sets'] = task.target_sets - record['planned_sets']
        record['first_supply_date'] = min((d.day.isoformat() for d in task.days), default=None)
        record['completion_date'] = max((d.day.isoformat() for d in task.days), default=None) if record['unplanned_sets'] == 0 else None
        result.append(record)
    return result


def save(db, user, line_id, body):
    order, data = orders.writable(db, line_id, body.expected_version)
    adjusting = bool(data.get('planning', {}).get('published'))
    c.require(not adjusting or body._reason_entered, '调整已发布计划须填写调整原因', 422)
    validate_removals(data, body)
    tasks = validate_tasks(db, data, body.tasks)
    removed_reasons = removal_reasons(data, body)
    plan = dict(version=order.version+1, basis=basis(data), tasks=tasks,
                allocated_sets=sum(t['target_sets'] for t in tasks),
                unallocated_sets=data['target_sets']-sum(t['target_sets'] for t in tasks),
                actor_id=user.id, created_at=datetime.now(UTC).isoformat(), reason=body.reason,
                adjustment_reason=body.reason if adjusting else None, removed_task_reasons=removed_reasons)
    data.setdefault('planning', {})['draft'] = plan
    return orders.append(db, user, order, data, body.reason)


def publish(db, user, line_id, body):
    order, data = orders.writable(db, line_id, body.expected_version)
    planning = data.get('planning', {})
    draft = planning.get('draft')
    c.require(draft and draft['version'] == body.draft_version, '请先保存并核对当前计划草稿')
    validate_published_removals(planning, draft)
    adjusting = bool(planning.get('published'))
    adjustment_reason = body.reason if body._reason_entered else (draft.get('adjustment_reason') or '').strip()
    c.require(not adjusting or adjustment_reason, '调整已发布计划须填写调整原因', 422)
    publication_reason = adjustment_reason if adjusting else body.reason
    c.require(not stale(draft, data), '订单、BOM 或采购交期已变更，请核对并重新保存计划草稿')
    # Revalidate resources at publication; never rewrite historical resource/calendar evidence.
    inputs = [{k: v for k, v in task.items() if k in PlanTask.model_fields} for task in draft['tasks']]
    checked = SavePlan.model_validate(dict(body.model_dump(exclude={'draft_version'}), tasks=inputs))
    validate_tasks(db, data, checked.tasks)
    c.require(any(t['days'] for t in draft['tasks']), '至少编制一个任务的日计划后再发布', 422)
    publication = deepcopy(draft)
    publication.update(version=order.version+1, actor_id=user.id, created_at=datetime.now(UTC).isoformat(),
                       reason=publication_reason, adjustment_reason=adjustment_reason if adjusting else None)
    planning['published'] = publication
    if not planning.get('baseline'):
        planning['baseline'] = deepcopy(publication)
    planning['draft'] = None
    return orders.append(db, user, order, data, publication_reason)
