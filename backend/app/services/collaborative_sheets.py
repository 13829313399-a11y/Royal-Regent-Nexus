"""Factory-local, explicit ACL collaboration with transactionally fenced writes."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import load_only

from app.models.auth import AuthUser, EmployeeProfile
from app.models.collaborative_sheets import CollaborativeSheet as Task, CollaborativeSheetEvent as Event, CollaborativeSheetSubmission as Submission
from app.services.auth import ALLOWED_FACTORY_IDS, ALLOWED_DEPARTMENTS
from app.services.identity_resolver import identity_columns
from app.services.document_tools import storage
from app.services import collaborative_sheet_files as files


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid():
    return str(uuid4())


def scope(user, factory_id):
    if factory_id not in ALLOWED_FACTORY_IDS:
        raise HTTPException(422, "请选择具体厂区")
    if not user.account_available or not user.profile or user.profile.confirmation_status != "confirmed" or user.profile.primary_factory_id != factory_id:
        raise HTTPException(403, "协同填表仅限已确认的本厂账号，不能跨厂区共享")


def _eligible_accounts(db, factory_id, grants=None):
    """Resolve current server identities; roles/history never manufacture members."""
    # Match auth's runtime identity resolution: a V2 transfer/expiry can change
    # the primary factory and department without rewriting legacy profile fields.
    current_factory, current_department, _ = identity_columns()
    query = select(AuthUser.id, AuthUser.display_name, AuthUser.username, current_department.label("primary_department")).join(
        EmployeeProfile, AuthUser.id == EmployeeProfile.user_id).where(
        AuthUser.status == "active", EmployeeProfile.employment_status != "left", current_factory == factory_id,
        EmployeeProfile.confirmation_status == "confirmed")
    if grants is not None:
        users = {g["principal_id"] for g in grants if g["principal_type"] == "user"}
        departments = {g["principal_id"] for g in grants if g["principal_type"] == "department"}
        if not users and not departments:
            return []
        query = query.where(or_(AuthUser.id.in_(users), current_department.in_(departments)))
    rows = [{"id": row.id, "display_name": row.display_name or row.username, "department": row.primary_department}
            for row in db.execute(query)]
    return sorted(rows, key=lambda row: (row["display_name"].casefold(), row["id"]))


def recipients(db, user, factory_id):
    scope(user, factory_id)
    rows = _eligible_accounts(db, factory_id)
    return {"users": rows, "departments": [{"id": d, "name": d} for d in sorted({r["department"] for r in rows} & ALLOWED_DEPARTMENTS)]}


def matching_grants(task, user):
    return [g for g in task.grants if (g["principal_type"] == "user" and g["principal_id"] == user.id)
            or (g["principal_type"] == "department" and user.profile and g["principal_id"] == user.profile.primary_department)]


def accessible(task, user):
    return task.owner_user_id == user.id or (task.status != "draft" and bool(matching_grants(task, user)))


def get_task(db, user, factory_id, task_id, owner=False, lightweight=False):
    scope(user, factory_id)
    query = select(Task).where(Task.id == task_id, Task.factory_id == factory_id)
    if lightweight:
        query = query.options(load_only(Task.id, Task.factory_id, Task.owner_user_id, Task.status, Task.revision, Task.grants, raiseload=True))
    task = db.scalar(query)
    if task is None or not accessible(task, user):
        raise HTTPException(404, "填表任务不存在或未向您共享")
    if owner and task.owner_user_id != user.id:
        raise HTTPException(403, "仅发起人可以执行此操作")
    return task


def summary(task, user):
    return {k: getattr(task, k) for k in ("id", "factory_id", "owner_user_id", "owner_name", "title", "original_name", "format", "status", "revision", "created_at", "updated_at")} | {"is_owner": task.owner_user_id == user.id}


def list_tasks(db, user, factory_id):
    scope(user, factory_id)
    # Apply access before the result limit so other employees' tasks cannot hide
    # an older task that is actually shared with the current employee.
    columns = (Task.id, Task.factory_id, Task.owner_user_id, Task.owner_name, Task.title, Task.original_name,
               Task.format, Task.status, Task.revision, Task.created_at, Task.updated_at, Task.grants)
    rows = db.scalars(select(Task).options(load_only(*columns)).where(Task.factory_id == factory_id)
                      .order_by(Task.updated_at.desc()).execution_options(yield_per=100))
    result = []
    for task in rows:
        if accessible(task, user):
            result.append(summary(task, user))
            if len(result) == 200:
                break
    return {"items": result}


def participants(db, task, submissions=None):
    """Current assignment roster, independent of the activity feed's 50 rows.

    Account/department overlaps select one real account. Revoked, transferred,
    disabled and unconfirmed identities fall out of the roster on the next read;
    historical audit evidence itself is intentionally left intact.
    """
    accounts = _eligible_accounts(db, task.factory_id, task.grants)
    if not accounts:
        return []
    if submissions is None:
        submissions = db.scalars(select(Submission).where(Submission.task_id == task.id)).all()
    submitted = {row.user_id: row for row in submissions}
    saved = dict(db.execute(select(Event.actor_id, func.max(Event.created_at)).where(
        Event.task_id == task.id, Event.action == "cells_saved").group_by(Event.actor_id)).all())
    result = []
    for account in accounts:
        confirmation = submitted.get(account["id"])
        last_saved = saved.get(account["id"])
        if confirmation:
            status = "completed" if confirmation.revision == task.revision else "needs_confirmation"
        else:
            status = "in_progress" if last_saved else "not_started"
        result.append({"user_id": account["id"], "display_name": account["display_name"], "department": account["department"],
                       "status": status, "last_saved_at": last_saved,
                       "submitted_at": confirmation.submitted_at if confirmation else None})
    return result


def participant_status(db, user, factory_id, task_id):
    task = get_task(db, user, factory_id, task_id, lightweight=True)
    return {"id": task.id, "revision": task.revision, "status": task.status, "participants": participants(db, task)}


def detail(db, task, user):
    workbook = deepcopy(task.manifest)
    for index, sheet in enumerate(workbook["sheets"]):
        existing = {c["address"]: c for c in sheet["cells"]}
        for key, value in task.overrides.items():
            s, address = key.split(":", 1)
            if int(s) != index:
                continue
            cell = existing.get(address)
            if cell is None:
                row, column = coordinate_to_tuple(address)
                cell = {"address": address, "row": row - 1, "column": column - 1, "formula": False, "style": {}}
                sheet["cells"].append(cell)
            cell["value"], cell["display"] = value, files._display(value, cell.get("number_format", "General"), sheet.get("date_mode", 0))
    grants = task.grants if task.owner_user_id == user.id else matching_grants(task, user)
    submissions = db.scalars(select(Submission).where(Submission.task_id == task.id).order_by(Submission.submitted_at.desc())).all()
    events = db.scalars(select(Event).where(Event.task_id == task.id).order_by(Event.created_at.desc(), Event.id.desc()).limit(50)).all()
    return summary(task, user) | {"workbook": workbook, "grants": grants,
        "participants": participants(db, task, submissions),
        "editable_ranges": [{"sheet": g["sheet"], "range": g["range"]} for g in grants] if task.status == "open" else [],
        "submissions": [{"user_id": s.user_id, "display_name": s.display_name, "revision": s.revision,
                         "submitted_at": s.submitted_at, "current": s.revision == task.revision} for s in submissions],
        "activity": [{"id": e.id, "actor_name": e.actor_name, "action": e.action, "revision": e.revision,
                      "created_at": e.created_at, "detail": e.detail} for e in events]}


def event(db, task, user, action, data):
    db.add(Event(id=uid(), task_id=task.id, actor_id=user.id, actor_name=user.display_name or user.username,
                 action=action, revision=task.revision, detail=data, created_at=now()))


def create(db, user, factory_id, title, name, data):
    scope(user, factory_id)
    name = storage.safe_name(name)
    kind = Path(name).suffix.lower().lstrip(".")
    if kind not in {"xls", "xlsx"}:
        raise HTTPException(422, "请选择 XLS 或 XLSX 文件")
    title = (title or Path(name).stem).strip()
    if not title or len(title) > 160:
        raise HTTPException(422, "标题须为 1 至 160 个字符")
    try:
        manifest = files.inspect_workbook(data, kind)
    except files.WorkbookError as exc:
        raise HTTPException(422, str(exc)) from exc
    identity = uid()
    key = f"collaborative-sheets/{identity}/original.{kind}"
    path = storage.resolve(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    task = Task(id=identity, factory_id=factory_id, owner_user_id=user.id, owner_name=user.display_name or user.username,
                title=title, original_name=name, format=kind, storage_key=key, source_sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data), manifest=manifest, overrides={}, grants=[], status="draft", revision=1,
                created_at=now(), updated_at=now())
    try:
        db.add(task)
        db.flush()
        event(db, task, user, "created", {"original_name": name, "sha256": task.source_sha256})
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return detail(db, task, user)


def _cas(db, task, expected, values, bump=True):
    if task.revision != expected:
        raise HTTPException(409, "表格已被其他人更新，请刷新后核对再保存")
    patch = values | {"revision": expected + (1 if bump else 0), "updated_at": now()}
    result = db.execute(update(Task).where(Task.id == task.id, Task.revision == expected).values(**patch).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "表格已被其他人更新，请刷新后核对再保存")
    db.refresh(task)


def _range(task, sheet_index, address_range):
    if sheet_index >= len(task.manifest["sheets"]):
        raise HTTPException(422, "工作表不存在")
    sheet = task.manifest["sheets"][sheet_index]
    c1, r1, c2, r2 = range_boundaries(address_range)
    if not all((c1, r1, c2, r2)) or c1 > c2 or r1 > r2 or r2 > sheet["rows"] or c2 > sheet["columns"] or sheet.get("hidden"):
        raise HTTPException(422, "填写范围超出原表可见数据区")
    return c1, r1, c2, r2


def set_grants(db, task, user, payload):
    if task.status == "closed":
        raise HTTPException(409, "任务已结束，请先重新开放")
    available = recipients(db, user, task.factory_id)
    users = {u["id"] for u in available["users"]}
    departments = {d["id"] for d in available["departments"]}
    grants = []
    for grant in payload.grants:
        value = grant.model_dump()
        if grant.principal_id not in (users if grant.principal_type == "user" else departments):
            raise HTTPException(422, "只能选择本厂有效账号或部门")
        c1, r1, c2, r2 = _range(task, grant.sheet, grant.range)
        sheet = task.manifest["sheets"][grant.sheet]
        # A merged cell is one logical field; partial grants would make its
        # displayed editable area disagree with the server's anchor check.
        for merge in sheet["merges"]:
            mc1, mr1, mc2, mr2 = range_boundaries(merge)
            overlap = c1 <= mc2 and c2 >= mc1 and r1 <= mr2 and r2 >= mr1
            if overlap and not (c1 <= mc1 and c2 >= mc2 and r1 <= mr1 and r2 >= mr2):
                raise HTTPException(422, "填写范围不能切开合并单元格，请包含完整合并区域")
        if value not in grants:
            grants.append(value)
    if task.status == "open" and not grants:
        raise HTTPException(422, "开放中的任务至少需要一个填写范围")
    _cas(db, task, payload.expected_revision, {"grants": grants})
    event(db, task, user, "grants_changed", {"grants": grants})
    db.commit()
    return detail(db, task, user)


def set_state(db, task, user, payload):
    if payload.status == "open" and not task.grants:
        raise HTTPException(422, "请先设置填写人和填写范围")
    if task.status == "draft" and payload.status == "closed":
        raise HTTPException(409, "草稿请先发布后再结束")
    if task.status == payload.status:
        if task.revision != payload.expected_revision:
            raise HTTPException(409, "任务版本已更新")
        return detail(db, task, user)
    previous = task.status
    _cas(db, task, payload.expected_revision, {"status": payload.status})
    event(db, task, user, "opened" if payload.status == "open" else "closed", {"previous_status": previous})
    db.commit()
    return detail(db, task, user)


def source_bytes(task):
    try:
        data = storage.resolve(task.storage_key).read_bytes()
    except OSError as exc:
        raise HTTPException(409, "原文件暂不可用，请联系管理员恢复") from exc
    if hashlib.sha256(data).hexdigest() != task.source_sha256:
        raise HTTPException(409, "原文件完整性校验失败，已停止导出")
    return data


def save_cells(db, task, user, payload):
    if task.status != "open":
        raise HTTPException(409, "任务尚未开放或已经结束，不能填写")
    if task.revision != payload.expected_revision:
        raise HTTPException(409, "表格已被其他人更新，请刷新后核对再保存")
    grants = task.grants if task.owner_user_id == user.id else matching_grants(task, user)
    overrides = dict(task.overrides)
    changes, seen = [], set()
    for change in payload.changes:
        r, c = coordinate_to_tuple(change.address)
        _range(task, change.sheet, change.address)
        allowed = False
        for grant in grants:
            if grant["sheet"] != change.sheet:
                continue
            c1, r1, c2, r2 = range_boundaries(grant["range"])
            if c1 <= c <= c2 and r1 <= r <= r2:
                allowed = True
        if not allowed:
            raise HTTPException(403, "所填单元格未获授权")
        sheet = task.manifest["sheets"][change.sheet]
        original = next((x for x in sheet["cells"] if x["address"] == change.address), None)
        if original and original["formula"]:
            raise HTTPException(422, "原表公式不可覆盖")
        for merge in sheet["merges"]:
            c1, r1, c2, r2 = range_boundaries(merge)
            if c1 <= c <= c2 and r1 <= r <= r2 and (r, c) != (r1, c1):
                raise HTTPException(422, "请填写合并区域的左上角单元格")
        key = f"{change.sheet}:{change.address}"
        if key in seen:
            raise HTTPException(422, "保存请求包含重复单元格")
        seen.add(key)
        changes.append({"sheet": change.sheet, "address": change.address, "before": overrides.get(key, original["value"] if original else None), "after": change.value})
        overrides[key] = change.value
    # Validate the actual exporter before acknowledging a saved fill, so an
    # unsupported BIFF structure can never strand accepted work at download.
    try:
        files.export_workbook(source_bytes(task), task.format, overrides)
    except files.WorkbookError as exc:
        raise HTTPException(422, str(exc)) from exc
    _cas(db, task, payload.expected_revision, {"overrides": overrides})
    event(db, task, user, "cells_saved", {"changes": changes})
    db.commit()
    return detail(db, task, user)


def submit(db, task, user, payload):
    if task.status != "open" or not matching_grants(task, user):
        raise HTTPException(409, "仅开放任务的指定填写人可以提交")
    # A no-bump CAS UPDATE locks the row until submission commits, fencing a
    # concurrent close, revocation or edit without making other submissions stale.
    _cas(db, task, payload.expected_revision, {}, bump=False)
    row = db.get(Submission, (task.id, user.id))
    if row is None:
        row = Submission(task_id=task.id, user_id=user.id)
        db.add(row)
    row.display_name, row.revision, row.submitted_at = user.display_name or user.username, task.revision, now()
    event(db, task, user, "submitted", {})
    db.commit()
    return detail(db, task, user)


def download(task):
    try:
        return files.export_workbook(source_bytes(task), task.format, task.overrides)
    except files.WorkbookError as exc:
        raise HTTPException(422, str(exc)) from exc
