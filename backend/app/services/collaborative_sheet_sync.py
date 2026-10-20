"""Cell-level reconciliation over the immutable workbook and existing audit ledger.

No document serialization or image transfer occurs on the typing/save path.
All writes serialize on the task row (including SQLite's writer reservation).
"""
import hashlib
import json
from collections import OrderedDict
from threading import Lock

from fastapi import HTTPException
from sqlalchemy import select, update

from app.models.collaborative_sheets import CollaborativeSheet as Task, CollaborativeSheetEvent as Event
from app.services import collaborative_sheets as sheets


def same(a, b):
    # Python's True == 1 must not erase Excel's distinct boolean cell type.
    return a == b and isinstance(a, bool) == isinstance(b, bool)


def public_event(e):
    return {"id": e.id, "actor_id": e.actor_id, "actor_name": e.actor_name, "action": e.action,
            "revision": e.revision, "created_at": e.created_at,
            "detail": {k: v for k, v in e.detail.items() if k not in {"fingerprint", "operation_id"}}}


def delta(db, task, user, since):
    if since > task.revision:
        raise HTTPException(409, "客户端版本超前，请重新打开任务")
    events = db.scalars(select(Event).where(Event.task_id == task.id, Event.revision > since,
        Event.revision <= task.revision).order_by(Event.revision, Event.created_at, Event.id).limit(501)).all()
    grants = task.grants if task.owner_user_id == user.id else sheets.matching_grants(task, user)
    # A large reconnect is still only scalar data, never the image-heavy manifest.
    reset = len(events) > 500
    return {"id": task.id, "revision": task.revision, "status": task.status, "grants": grants,
            "editable_ranges": [{"sheet": g["sheet"], "range": g["range"]} for g in grants] if task.status == "open" else [],
            "events": [] if reset else [public_event(e) for e in events],
            "overrides": db.scalar(select(Task.overrides).where(Task.id == task.id)) if reset else None}


def save(db, user, factory_id, task_id, payload):
    sheets.scope(user, factory_id)
    # Acquire before reading revision/overrides/receipt. Legacy CAS writes also
    # update this row, so close/revoke/save cannot slip between validation/commit.
    db.execute(update(Task).where(Task.id == task_id, Task.factory_id == factory_id)
               .values(revision=Task.revision).execution_options(synchronize_session=False))
    db.expire_all()
    task = sheets.get_task(db, user, factory_id, task_id)
    receipt_id = hashlib.sha256(f"{task_id}:{user.id}:{payload.operation_id}".encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    receipt = db.get(Event, receipt_id)
    if receipt:
        if receipt.detail.get("fingerprint") != fingerprint:
            raise HTTPException(409, "重试标识已用于不同内容")
        result = delta(db, task, user, payload.expected_revision)
        result["applied_revision"] = receipt.revision
        db.commit()
        return result
    if task.status != "open":
        raise HTTPException(409, "任务尚未开放或已结束，填写仍保留在本机")
    if payload.expected_revision > task.revision:
        raise HTTPException(409, "客户端版本超前，请重新打开任务")
    changes, overrides = sheets.validated_changes(task, user, payload.changes)
    touched = {}
    for e in db.scalars(select(Event).where(Event.task_id == task.id, Event.action == "cells_saved",
            Event.revision > min(c.base_revision for c in payload.changes)).order_by(Event.revision)):
        for c in e.detail.get("changes", []):
            touched[(c["sheet"], c["address"])] = e
    conflicts = []
    for current, submitted in zip(changes, payload.changes):
        changed = touched.get((submitted.sheet, submitted.address))
        if submitted.base_revision > payload.expected_revision:
            raise HTTPException(422, "单元格基准版本不能超过已读取版本")
        if (changed and changed.revision > submitted.base_revision) or not same(current["before"], submitted.base_value):
            conflicts.append({"sheet": submitted.sheet, "address": submitted.address,
                              "value": current["before"], "mine": submitted.value,
                              "actor_name": changed.actor_name if changed else "其他填写人",
                              "revision": task.revision})
    if conflicts:
        raise HTTPException(409, {"code": "cell_conflict", "conflicts": conflicts})
    if task.format == "xls":
        # BIFF8 has value-dependent row-block/SST limits. Keep that validation
        # for legacy binary workbooks; XLSX's bounded scalar XML path needs no
        # full archive reserialization on each keystroke.
        try:
            sheets.files.export_workbook(sheets.source_bytes(task), task.format, overrides)
        except sheets.files.WorkbookError as exc:
            raise HTTPException(422, str(exc)) from exc
    sheets._cas(db, task, task.revision, {"overrides": overrides})
    sheets.event(db, task, user, "cells_saved", {"changes": changes, "fingerprint": fingerprint}, event_id=receipt_id)
    db.flush()
    result = delta(db, task, user, payload.expected_revision)
    result["applied_revision"] = task.revision
    db.commit()
    return result


def history(db, task, before=None, actor=None, sheet=None, address=None):
    query = select(Event).where(Event.task_id == task.id, Event.action == "cells_saved")
    if before is not None:
        query = query.where(Event.revision < before)
    if actor:
        query = query.where(Event.actor_id == actor)
    # Revision is unique for cells_saved; filter inside bounded batches so a
    # sparse cell's earlier history remains reachable without loading all rows.
    rows = db.scalars(query.order_by(Event.revision.desc()).limit(100)).all()
    items = []
    for row in rows:
        entry = public_event(row)
        entry["detail"] = {"changes": [c for c in row.detail.get("changes", [])
            if (sheet is None or c["sheet"] == sheet) and (not address or c["address"] == address)]}
        if entry["detail"]["changes"]:
            items.append(entry)
    return {"items": items, "next_before": rows[-1].revision if len(rows) == 100 else None}


_cache = OrderedDict()
_cache_lock = Lock()
_cache_bytes = 64 * 1024 * 1024


def download(task):
    # Source integrity is checked even on hits. Cache is bounded across tasks,
    # keyed by content rather than revision (submissions/grants don't change Excel).
    source = sheets.source_bytes(task)
    key = (task.source_sha256, task.format, hashlib.sha256(json.dumps(task.overrides, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        data = sheets.files.export_workbook(source, task.format, task.overrides)
    except sheets.files.WorkbookError as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(data) <= _cache_bytes:
        with _cache_lock:
            _cache[key] = data
            while sum(map(len, _cache.values())) > _cache_bytes:
                _cache.popitem(last=False)
    return data
