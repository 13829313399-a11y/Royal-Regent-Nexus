"""Declared schedule coverage and absence evidence; never mutates procurement."""
import hashlib
import json
from collections import defaultdict
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select

from app.models.carton_procurement import CartonImportBatch, CartonAuditEvent
from app.services import carton_procurement as core
from app.services.carton_schedule_tracking import identity, tracked

ENTITY = "carton_schedule_missing"
EVENT = "SCHEDULE_MISSING_REVIEWED"
BASIS = "CUSTOMER_DUE_DATE"
ZERO_SCOPE = "UNDECLARED"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def complete_day(value, label):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        result = date.fromisoformat(value).isoformat()
        if result != value: raise ValueError()
        return result
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"{label}须为完整有效日期 YYYY-MM-DD") from exc


def normalize_scope(profile):
    result = dict(profile or {})
    mode = result.get("scope_mode") or ZERO_SCOPE
    if mode not in {ZERO_SCOPE, "FULL", "INCREMENTAL"}: raise HTTPException(422, "排期导入范围类型无效")
    start, end, as_of = (result.get(key) or None for key in ("coverage_start", "coverage_end", "as_of_date"))
    confirmed = result.get("full_scope_confirmed", False)
    if mode == ZERO_SCOPE:
        if start or end or as_of or confirmed: raise HTTPException(422, "请先声明全量或增量，再填写排期版本及范围")
        for key in ("scope_mode", "coverage_start", "coverage_end", "as_of_date", "full_scope_confirmed"):
            result.pop(key, None)
        return result
    as_of = complete_day(as_of, "排期版本日")
    if as_of > core.business_today(): raise HTTPException(422, "排期版本日不能晚于上海今天")
    if bool(start) != bool(end): raise HTTPException(422, "覆盖起止日期须完整成对填写")
    if start:
        start, end = complete_day(start, "覆盖开始日期"), complete_day(end, "覆盖结束日期")
        if start > end: raise HTTPException(422, "覆盖开始日期不可晚于结束日期")
    if mode == "FULL" and (not start or confirmed is not True):
        raise HTTPException(422, "全量排期须明确客户交期覆盖区间，并确认本文件完整覆盖该区间")
    result.update(scope_mode=mode, as_of_date=as_of, coverage_start=start, coverage_end=end,
        full_scope_confirmed=confirmed is True if mode == "FULL" else False)
    return result


def inside(source, start, end):
    try: day = complete_day(source.get("customer_due_date"), "客户交期")
    except HTTPException: return False
    return start <= day <= end


def profile_identity(profile):
    if profile.get("scope_mode"):
        return "schedule-coverage-v1:" + digest(profile)
    return json.dumps(profile, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def authorize(db, user, factory, customer_code=None, *, write=False):
    from app.services import carton_special_requests as special
    core.require_carton_factory(factory)
    if not special.allowed(user, factory, "read") or write and not special.allowed(user, factory, "import"):
        raise HTTPException(403, "没有本厂排期读取或导入核实权限")
    if write and customer_code:
        core.get_active_customer(db, factory, customer_code)
        special.ensure_customer_operation(db, user, factory, customer_code)


def locked_import_actor(db, user, factory, customer_code=None):
    from app.services.carton_special_requests import locked_actor
    user = locked_actor(db, user, core.require_carton_factory(factory))
    authorize(db, user, factory, customer_code, write=True)
    return user


def summary(batch):
    try:
        result = json.loads(batch.parse_summary_json or "{}")
        return result if isinstance(result, dict) else {}
    except (TypeError, json.JSONDecodeError): return {}


def batches(db, factory):
    query = select(CartonImportBatch, CartonAuditEvent.sequence).outerjoin(CartonAuditEvent,
        (CartonAuditEvent.factory_id == CartonImportBatch.factory_id)
        & (CartonAuditEvent.entity_id == CartonImportBatch.id)
        & (CartonAuditEvent.entity_type == "carton_import_batch")
        & (CartonAuditEvent.event_type == "IMPORT_BATCH_CREATED")).where(
        CartonImportBatch.factory_id == factory, CartonImportBatch.import_type == "WEEKLY_SCHEDULE")
    return [dict(batch=batch, sequence=sequence or 0, summary=summary(batch))
        for batch, sequence in db.execute(query.order_by(CartonAuditEvent.sequence.desc(), CartonImportBatch.created_at.desc(), CartonImportBatch.id.desc()))]


def customer_of(data):
    return str((data.get("schedule_customer") or {}).get("customer_code") or "")


def require_current_version(db, factory, profile):
    code = profile["customer_code"]
    active = [entry for entry in batches(db, factory) if entry["batch"].status != "REJECTED" and customer_of(entry["summary"]) == code]
    declared = [entry["summary"]["schedule_coverage"] for entry in active if entry["summary"].get("schedule_coverage", {}).get("scope_mode") in {"FULL", "INCREMENTAL"}]
    if declared and not profile.get("scope_mode"):
        raise HTTPException(409, "该客户已启用排期范围声明，请填写全量或增量及排期版本日；未保存新批次")
    if declared and profile["as_of_date"] < max(item["as_of_date"] for item in declared):
        raise HTTPException(409, "此排期版本早于该客户最新有效声明，不能用迟到旧文件覆盖当前排期")


def attach(db, factory, batch_id, data, profile):
    if not profile.get("scope_mode"): return
    rows = [row for row in data.get("rows", []) if isinstance(row, dict)]
    mode = profile["scope_mode"]
    if mode == "FULL":
        completeness = data.get("coverage_parse") or {}
        if data.get("engine") != "unified-item-header-mapping" or completeness.get("version") != 1 or completeness.get("unrecognized_sheets"):
            raise HTTPException(422, "全量范围仅支持完整 ITEM 模板；存在未识别工作表或跳行风险，请改为增量或修正原文件")
        if not rows or any(not identity(row) for row in rows):
            raise HTTPException(422, "全量文件为空或有合同、货号等关键身份缺损，不能据此判定其他排期缺失")
        if not any(inside(row, profile["coverage_start"], profile["coverage_end"]) for row in rows):
            raise HTTPException(422, "全量文件在声明客户交期范围内没有可识别业务行，不能据此批量判定缺失")
    excluded = []
    for row in rows:
        try: complete_day(row.get("customer_due_date"), "客户交期")
        except HTTPException:
            excluded.append(dict(source_sheet=row.get("source_sheet"), source_row=row.get("source_row"),
                contract_no=row.get("contract_no", ""), item_no=row.get("item_no", ""),
                source_customer_due_date=row.get("source_customer_due_date", ""), reason="客户交期缺少完整有效日期，不用于覆盖区间或缺失判断"))
    coverage = {key: profile.get(key) for key in ("scope_mode", "as_of_date", "coverage_start", "coverage_end", "full_scope_confirmed")}
    coverage.update(version=1, date_basis=BASIS, identity_profile=dict(profile), excluded_rows=excluded, missing_rows=[])
    if mode == "FULL":
        present = {identity(row) for row in rows if identity(row)}
        previous = {}
        for entry in batches(db, factory):
            if entry["batch"].status == "REJECTED" or customer_of(entry["summary"]) != profile["customer_code"]: continue
            groups = defaultdict(list)
            for row in entry["summary"].get("rows", []):
                if isinstance(row, dict) and row.get("schedule_section") and identity(row):
                    groups[identity(row)].append({**row, "batch_id": entry["batch"].id})
            for key, source_rows in groups.items(): previous.setdefault(key, source_rows)
        for key, sources in previous.items():
            if key in present or not all(tracked(row) and row.get("schedule_section") == "PENDING" for row in sources): continue
            valid = []
            for source in sources:
                try: day = complete_day(source.get("customer_due_date"), "历史客户交期")
                except HTTPException:
                    excluded.append(dict(batch_id=source["batch_id"], source_sheet=source.get("source_sheet"), source_row=source.get("source_row"),
                        contract_no=source.get("contract_no", ""), item_no=source.get("item_no", ""), reason="历史客户交期未核实，不能判断缺失"))
                    continue
                valid.append(profile["coverage_start"] <= day <= profile["coverage_end"])
            if not valid or len(valid) != len(sources) or not all(valid): continue
            first = sources[0]
            coverage["missing_rows"].append(dict(id="SCM-" + digest([factory, batch_id, key]), factory_id=factory,
                customer_code=profile["customer_code"], customer_name=data["schedule_customer"]["customer_name"],
                batch_id=batch_id, as_of_date=profile["as_of_date"], coverage_start=profile["coverage_start"], coverage_end=profile["coverage_end"],
                date_basis=BASIS, identity=key, **{field: first.get(field, "") for field in
                    ("contract_no", "item_no", "customer_po", "source_reference")}, source_rows=sources))
    data["schedule_coverage"] = coverage


def compact_coverage(data):
    if not data: return None
    return {key: data.get(key) for key in ("version", "scope_mode", "as_of_date", "coverage_start", "coverage_end", "date_basis", "full_scope_confirmed")} | {
        "excluded_count": len(data.get("excluded_rows", [])), "missing_count": len(data.get("missing_rows", []))}


def scope_summary(entry):
    batch, data = entry["batch"], entry["summary"].get("schedule_coverage") or {}
    return dict(batch_id=batch.id, filename=batch.original_filename, created_at=batch.created_at,
        scope_mode=data.get("scope_mode", ZERO_SCOPE), as_of_date=data.get("as_of_date"), coverage_start=data.get("coverage_start"),
        coverage_end=data.get("coverage_end"), date_basis=BASIS,
        excluded_count=len(data.get("excluded_rows", [])), missing_count=len(data.get("missing_rows", [])))


def cases(db, factory):
    entries = batches(db, factory)
    for entry in entries:
        entry["groups"] = defaultdict(list)
        for source in entry["summary"].get("rows", []):
            if isinstance(source, dict) and identity(source):
                entry["groups"][identity(source)].append({**source, "batch_id": entry["batch"].id})
    reviews = defaultdict(list)
    for event in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.factory_id == factory,
            CartonAuditEvent.entity_type == ENTITY, CartonAuditEvent.event_type == EVENT).order_by(CartonAuditEvent.sequence)):
        data = json.loads(event.detail_json)
        reviews[event.entity_id].append(dict(id=event.id, decision=data["decision"], reason=data["reason"],
            actor_name=event.actor_name, created_at=event.created_at, revision=data["revision"], source_fingerprint=data.get("source_fingerprint")))
    result = []
    for entry in entries:
        for frozen in entry["summary"].get("schedule_coverage", {}).get("missing_rows", []):
            row = dict(frozen)
            # Rebase the live guard on the latest surviving earlier evidence.
            # The original missing snapshot is never rewritten by withdrawal.
            previous = next((item["groups"][row["identity"]] for item in entries
                if item["sequence"] < entry["sequence"] and item["batch"].status != "REJECTED"
                and customer_of(item["summary"]) == row["customer_code"] and row["identity"] in item["groups"]), [])
            valid_prior = bool(previous) and all(tracked(source) and source.get("schedule_section") == "PENDING"
                and inside(source, row["coverage_start"], row["coverage_end"]) for source in previous)
            invalid = entry["batch"].status == "REJECTED" or not valid_prior
            later = [item for item in entries if item["sequence"] > entry["sequence"] and item["batch"].status != "REJECTED"
                and customer_of(item["summary"]) == row["customer_code"]]
            appearances = [dict(batch_id=item["batch"].id, source_sheet=source.get("source_sheet"), source_row=source.get("source_row"))
                for item in later for source in item["groups"].get(row["identity"], [])]
            appeared = next((item["groups"][row["identity"]] for item in later if row["identity"] in item["groups"]), [])
            actionable_appearance = len(appeared) == 1 and tracked(appeared[0]) and appeared[0].get("schedule_section") == "PENDING" \
                and isinstance(appeared[0].get("quantity"), (int, float)) and appeared[0]["quantity"] > 0
            history = reviews[row["id"]]
            fingerprint = digest([frozen, invalid, previous, appearances])
            effective_review = history[-1] if history and history[-1]["source_fingerprint"] == fingerprint else None
            decision = effective_review["decision"] if effective_review else "REOPEN"
            status = "INVALIDATED" if invalid else "RETURNED" if appearances else "PENDING" if decision == "REOPEN" else decision
            row.update(status=status, revision=history[-1]["revision"] if history else 1, history=history,
                reason=effective_review["reason"] if effective_review else "", source_fingerprint=fingerprint,
                effective_source_rows=previous, basis_changed=previous != row["source_rows"],
                appearance_source_rows=appeared,
                can_operate_source=status in {"KEEP_REQUIRED", "SOURCE_OMISSION"} or status == "RETURNED" and actionable_appearance,
                sequence=entry["sequence"])
            result.append(row)
    current = {}
    for row in result:
        if row["status"] == "INVALIDATED": continue
        latest = current.setdefault(row["identity"], row)
        if latest is not row:
            row.update(status="SUPERSEDED", can_operate_source=False, superseded_by=latest["id"],
                source_fingerprint=digest([row["source_fingerprint"], latest["id"], latest["source_fingerprint"]]))
    return entries, result


def can_review(db, user, row):
    try: authorize(db, user, row["factory_id"], row["customer_code"], write=True)
    except HTTPException: return False
    return row["status"] not in {"INVALIDATED", "RETURNED", "SUPERSEDED"}


def detail(db, user, factory, identifier):
    authorize(db, user, factory)
    _, rows = cases(db, factory)
    row = next((item for item in rows if item["id"] == identifier), None)
    if not row: raise HTTPException(404, "未找到本厂排期缺失核实证据")
    return live_context(db, factory, {key: value for key, value in row.items() if key != "sequence"}) | {"can_review": can_review(db, user, row)}


def workspace(db, user, factory, *, customer_code="", status="PENDING", keyword="", limit=50, offset=0):
    authorize(db, user, factory)
    if status not in {"ALL", "PENDING"}: raise HTTPException(422, "排期核实筛选状态无效")
    entries, all_rows = cases(db, factory)
    latest = {}
    for row in all_rows:
        if row["status"] not in {"INVALIDATED", "SUPERSEDED"}: latest.setdefault(row["identity"], row)
    current_rows = list(latest.values())
    customers = []
    masters = core.list_customers(db, factory, include_inactive=True)
    for customer in masters:
        active = [entry for entry in entries if entry["batch"].status != "REJECTED" and customer_of(entry["summary"]) == customer.customer_code]
        full = next((entry for entry in active if entry["summary"].get("schedule_coverage", {}).get("scope_mode") == "FULL"), None)
        customers.append(dict(customer_code=customer.customer_code, customer_name=customer.customer_name, status=customer.status,
            latest_import=scope_summary(active[0]) if active else None, full_coverage=scope_summary(full) if full else None,
            pending_count=sum(row["status"] == "PENDING" for row in current_rows if row["customer_code"] == customer.customer_code),
            excluded_count=len((active[0]["summary"].get("schedule_coverage") or {}).get("excluded_rows", [])) if active else 0))
    unbound = [entry for entry in entries if entry["batch"].status != "REJECTED" and not customer_of(entry["summary"])]
    if unbound:
        customers.append(dict(customer_code="__UNBOUND__", customer_name="未绑定客户", status="LEGACY", latest_import=scope_summary(unbound[0]),
            full_coverage=None, pending_count=0, excluded_count=0))
    rows = current_rows if status == "PENDING" else all_rows
    if customer_code: rows = [row for row in rows if row["customer_code"] == customer_code]
    pending_count = sum(row["status"] == "PENDING" for row in current_rows if not customer_code or row["customer_code"] == customer_code)
    if status == "PENDING": rows = [row for row in rows if row["status"] == "PENDING"]
    if keyword:
        word = keyword.casefold()
        rows = [row for row in rows if word in " ".join(str(row.get(key, "")) for key in
            ("customer_code", "customer_name", "contract_no", "item_no", "customer_po", "source_reference")).casefold()]
    state = core.schedule_order_state(db, factory) if rows[offset:offset+limit] else {}
    items = [live_context(db, factory, {key: value for key, value in row.items() if key != "sequence"}, state=state)
        | {"can_review": can_review(db, user, row)} for row in rows[offset:offset+limit]]
    return dict(factory_id=factory, customers=customers, missing=dict(items=items, total=len(rows), limit=limit, offset=offset, pending_count=pending_count))


def review(db, user, identifier, payload):
    user = locked_import_actor(db, user, payload.factory_id)
    row = detail(db, user, payload.factory_id, identifier)
    authorize(db, user, payload.factory_id, row["customer_code"], write=True)
    request_id = "CAE-SCM-" + digest([payload.factory_id, user.id, payload.request_id])
    fingerprint = digest([identifier, payload.model_dump(mode="json")])
    previous = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.id == request_id))
    if previous:
        if json.loads(previous.detail_json).get("fingerprint") != fingerprint: raise HTTPException(409, "提交标识已用于其他排期核实内容")
        return dict(row, replayed=True)
    if row["status"] in {"INVALIDATED", "RETURNED", "SUPERSEDED"} or payload.expected_revision != row["revision"] or payload.source_fingerprint != row["source_fingerprint"]:
        raise HTTPException(409, "排期或缺失核实版本已变化，请刷新原始证据后再核实")
    if len(payload.reason.strip()) < 4: raise HTTPException(422, "请填写至少四字的客户核实依据")
    event = core._audit(db, user, payload.factory_id, EVENT, ENTITY, identifier,
        dict(decision=payload.decision, reason=payload.reason.strip(), revision=row["revision"] + 1,
            request_id=payload.request_id, fingerprint=fingerprint, source_fingerprint=payload.source_fingerprint))
    event.id = request_id
    db.flush()
    result = detail(db, user, payload.factory_id, identifier)
    db.commit()
    return result


def source_reviews(db, factory):
    _, rows = cases(db, factory)
    result = {}
    for row in rows:
        if row["status"] not in {"INVALIDATED", "SUPERSEDED"}: result.setdefault(row["identity"], row)
    return result


def source_allowed(row, source, batch_id):
    if row["can_operate_source"]: return True
    if row["status"] != "RETURNED": return False
    return any(item["batch_id"] == batch_id and item.get("source_sheet") == source.get("source_sheet")
        and item.get("source_row") == source.get("source_row") and tracked(item) and item.get("schedule_section") == "PENDING"
        and isinstance(item.get("quantity"), (int, float)) and item["quantity"] > 0 for item in row["appearance_source_rows"])


def live_context(db, factory, row, *, state=None):
    from app.services.carton_schedule_tracking import mark_for_row, mark_changes
    state = core.schedule_order_state(db, factory) if state is None else state
    current = []
    for source in row["source_rows"]:
        key = source.get("schedule_identity") or identity(source)
        linked = state.get(key, {})
        mark = mark_for_row(source, state)
        current.append(dict(batch_id=source["batch_id"], source_sheet=source.get("source_sheet"), source_row=source.get("source_row"),
            current_order_ids=linked.get("order_ids", []), current_manual_marked=bool(mark.get("marked")),
            manual_review_required=bool(mark_changes(source, mark))))
    row.update(current_sources=current, current_order_ids=sorted({value for source in current for value in source["current_order_ids"]}),
        current_manual_marked=any(source["current_manual_marked"] for source in current),
        current_state_basis="EXPLICIT_SOURCE_LINKS_AND_MANUAL_MARKS")
    return row


def guard_source(db, factory, source, *, batch_id):
    row = source_reviews(db, factory).get(identity(source))
    if row and not source_allowed(row, source, batch_id):
        raise HTTPException(409, "最新全量排期缺失此来源，尚未核实或已确认不再需要；请先在缺失待核实清单核对，不会自动取消正式采购单")


def decorate(db, result):
    if result.import_type != "WEEKLY_SCHEDULE" or not result.detail_loaded: return result
    reviews = source_reviews(db, result.factory_id)
    for source in result.parse_summary.get("rows", []):
        row = reviews.get(identity(source)) if isinstance(source, dict) else None
        if row:
            source["missing_review"] = {key: row[key] for key in ("id", "status", "can_operate_source", "reason")}
            source["can_operate_source"] = source_allowed(row, source, result.id)
            source["missing_review"]["can_operate_source"] = source["can_operate_source"]
    return result


def completed_batch(db, user, factory, identifier):
    user = locked_import_actor(db, user, factory)
    batch = db.get(CartonImportBatch, identifier)
    if not batch or batch.factory_id != factory: raise HTTPException(404, "导入批次不存在")
    authorize(db, user, factory, customer_of(summary(batch)), write=True)
    return decorate(db, core.import_batch_out(batch))
