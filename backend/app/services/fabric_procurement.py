"""Factory-scoped, previewed purchase-source ingestion. No inventory mutations."""
from collections import Counter, defaultdict, deque
from uuid import uuid4
import json

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.core.time import business_now
from app.models.fabric_procurement import FabricProcurementState, FabricProcurementLine, FabricProcurementImport, FabricProcurementEvidence
from app.services.fabric_procurement_parser import PARSER_VERSION, digest, dump, document_identity, upstream_identity, number

FACTORY = "huakang-c"


def require_factory(factory_id):
    if factory_id != FACTORY:
        raise HTTPException(422, "布料仓采购来源目前仅适用于华康 C，请明确选择厂区")
    return factory_id


def ensure_schema(db):
    from sqlalchemy import inspect
    names = set(inspect(db.get_bind()).get_table_names())
    expected = {model.__tablename__ for model in (FabricProcurementState, FabricProcurementLine, FabricProcurementImport, FabricProcurementEvidence)}
    if not expected <= names:
        raise HTTPException(503, "布料仓采购来源数据库尚未升级，请先备份并执行迁移 20261005_0134")


def revision(db):
    return db.scalar(select(FabricProcurementState.revision).where(FabricProcurementState.factory_id == FACTORY)) or 0


def lock_factory(db):
    # A database lock, shared by API workers and future upstream adapters.
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise HTTPException(503, "采购来源写入仅支持 SQLite / PostgreSQL")
    try:
        db.execute(insert(FabricProcurementState).values(factory_id=FACTORY, revision=0).on_conflict_do_nothing())
        db.execute(update(FabricProcurementState).where(FabricProcurementState.factory_id == FACTORY).values(revision=FabricProcurementState.revision))
    except OperationalError as exc:
        if dialect == "sqlite" and "locked" in str(exc).lower():
            db.rollback()
            raise HTTPException(409, "另一笔采购导入正在保存，请稍后重新预览或重试") from exc
        raise
    return db.scalar(select(FabricProcurementState).where(FabricProcurementState.factory_id == FACTORY).with_for_update().execution_options(populate_existing=True))


def empty_reference_upgrade_matches(db, old, group, source_digest):
    """Bridge only a proven v3 empty-arrival interpretation, never guess row IDs."""
    if len(old) != len(group):
        return None
    remaining = {line.id: line for line in old}
    matches = {}
    pending = [row for row in group if row["facts"].get("reported_received_quantity_basis") == "EMPTY_PENDING_DELIVERY"]
    if not pending:
        return None
    evidence = defaultdict(set)
    events = db.execute(select(FabricProcurementEvidence, FabricProcurementImport).join(FabricProcurementImport,
        FabricProcurementImport.id == FabricProcurementEvidence.import_id).where(
        FabricProcurementEvidence.factory_id == FACTORY, FabricProcurementEvidence.line_id.in_(remaining)))
    for event, batch in events:
        metadata = json.loads(batch.result_json)
        # Legacy evidence omitted shared-formula attributes and header mappings.
        # Matching the complete file hash proves those omitted parts unchanged.
        if not metadata.get("withdrawal") and batch.request_hash == digest([source_digest, metadata.get("scope"), batch.actor_id]):
            facts = json.loads(remaining[event.line_id].payload_json)
            if digest(json.loads(event.after_json)) != digest(facts):
                continue
            raw = json.loads(event.raw_json)
            raw_hash = digest({key: raw.get(key, {}) for key in ("values", "formulas", "number_formats")})
            evidence[(digest(facts), event.sheet, event.row_number, raw_hash)].add(event.line_id)
    for row in pending:
        facts = row["facts"]
        if facts.get("reported_received_quantity") != "0":
            return None
        legacy = {key: value for key, value in facts.items() if key != "reported_received_quantity_basis"}
        legacy["reported_received_quantity"] = None
        raw_hash = digest({key: row["raw"].get(key, {}) for key in ("values", "formulas", "number_formats")})
        candidates = evidence[(digest(legacy), row["sheet"], row["row_number"], raw_hash)] & remaining.keys()
        if len(candidates) > 1:
            return None
        if not candidates:
            continue
        line = remaining[next(iter(candidates))]
        matches[row["row_key"]] = line
        remaining.pop(line.id)
    if not matches:
        return None
    # Reserve uniquely proven upgrade rows before matching identical unchanged
    # facts, so an unchanged duplicate cannot consume the upgrade's source ID.
    exact = defaultdict(deque)
    for line in remaining.values():
        exact[digest(json.loads(line.payload_json))].append(line)
    for row in group:
        if row["row_key"] in matches:
            continue
        candidates = exact[digest(row["facts"])]
        if not candidates:
            return None
        line = candidates.popleft()
        matches[row["row_key"]] = line
        remaining.pop(line.id)
    return matches if not remaining else None


def prepare(db, parsed):
    all_lines = list(db.scalars(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == FACTORY).order_by(FabricProcurementLine.ordinal)))
    active_lines = [line for line in all_lines if line.status != "WITHDRAWN"]
    if parsed["scope"] == "TRACKING":
        keys = {line.identity_key for line in active_lines}
        naturals = {document_identity(json.loads(line.payload_json)) for line in active_lines}
        upstream = {upstream_identity(facts) for line in active_lines if (facts := json.loads(line.payload_json)).get("source_line_id")}
        selected = [row for row in parsed["rows"] if row["facts"]["status"] == "PENDING" or row["identity_key"] in keys | upstream or document_identity(row["facts"]) in naturals]
        parsed["excluded_history"] = len(parsed["rows"]) - len(selected)
        parsed["rows"] = selected
    incoming = defaultdict(list)
    natural_incoming = defaultdict(list)
    for row in parsed["rows"]:
        incoming[row["identity_key"]].append(row)
        natural_incoming[document_identity(row["facts"])].append(row)
    for group in natural_incoming.values():
        if any(row["facts"]["source_line_id"] for row in group) and any(not row["facts"]["source_line_id"] for row in group):
            for row in group:
                row["errors"].append("同一采购来源同时有带明细 ID 和不带 ID 的行，请明确行对应，避免重复新增或覆盖")
    existing, natural = defaultdict(list), defaultdict(list)
    by_id = {line.id: line for line in active_lines}
    withdrawn = defaultdict(list)
    for line in all_lines:
        if line.status == "WITHDRAWN":
            withdrawn[line.identity_key].append(line)
    for line in active_lines:
        facts = json.loads(line.payload_json)
        natural[document_identity(facts)].append(line)
        aliases = {line.identity_key}
        if facts.get("source_line_id"):
            aliases.add(upstream_identity(facts))
        for alias in aliases & incoming.keys():
            existing[alias].append(line)
    for key, group in incoming.items():
        for row in group:
            bind = row.get("bind_line_id")
            if bind:
                line = by_id.get(bind)
                if line is None or line.revision != row.get("expected_line_revision"):
                    row["errors"].append("仓库来源编号或版本无效，请重新读取当前明细后核对")
                elif document_identity(json.loads(line.payload_json)) != document_identity(row["facts"]):
                    row["errors"].append("仓库来源编号的采购单、物料、单位和归属不一致，不能关联")
                elif json.loads(line.payload_json).get("source_line_id") not in {"", row["facts"]["source_line_id"]}:
                    row["errors"].append("仓库来源编号已关联其他采购明细 ID")
                elif existing[key] and any(old.id != line.id for old in existing[key]):
                    row["errors"].append("采购明细 ID 与指定的仓库来源编号冲突")
                elif not existing[key]:
                    existing[key].append(line)
            elif not existing[key] and natural[document_identity(row["facts"])]:
                row["errors"].append("已有同来源的文档或直用数据，请明确关联仓库来源编号，避免重复新增")
    for key, group in incoming.items():
        old = existing[key]
        old_facts = [json.loads(line.payload_json) for line in old]
        if len(old) == len(group) == 1 and not group[0]["facts"]["source_line_id"]:
            # A later file cannot erase an explicitly linked upstream identifier.
            group[0]["facts"]["source_line_id"] = old_facts[0].get("source_line_id", "")
        equal = Counter(digest(f) for f in old_facts) == Counter(digest(row["facts"]) for row in group)
        group_error = any(row["errors"] for row in group)
        if group_error:
            for row in group:
                if not row["errors"]:
                    row["errors"].append("同组采购明细有异常，须一起核对，避免漏行")
        upgrade_matches = empty_reference_upgrade_matches(db, old, group, parsed["source_digest"]) if old and not equal and not group_error and (len(old) > 1 or len(group) > 1) else None
        if old and not equal and not upgrade_matches and (len(old) > 1 or len(group) > 1):
            for row in group:
                row["errors"].append("同组多条明细发生变化，缺少稳定采购明细 ID，无法确定对应关系；请补充采购明细 ID 后核对接入")
        if len(group) > 1 and not group[0]["facts"]["source_line_id"]:
            for row in group:
                row["warnings"].append("同组有多条采购明细，分别保留；后续变化需核对行对应")
        if len(group) > 1 and group[0]["facts"]["source_line_id"]:
            for row in group:
                row["errors"].append("采购明细 ID 重复，不能接入")
        matching = defaultdict(deque)
        for line, facts in zip(old, old_facts):
            matching[digest(facts)].append(line)
        # Reordered exact re-imports retain their original IDs even after withdrawal.
        # For changed ambiguous groups, allocate new slots instead of reassigning history.
        resurrection = {}
        inactive_matches = defaultdict(deque)
        for line in withdrawn[key]:
            inactive_matches[digest(json.loads(line.payload_json))].append(line)
        if not old:
            for row in group:
                candidates = inactive_matches[digest(row["facts"])]
                if candidates:
                    resurrection[row["row_key"]] = candidates.popleft()
            if len(group) == len(withdrawn[key]) == 1:
                resurrection[group[0]["row_key"]] = withdrawn[key][0]
        next_ordinal = max((line.ordinal for line in withdrawn[key]), default=0) + 1
        for ordinal, row in enumerate(group, start=1):
            row.update(action="BLOCKED", existing_id=None, previous=None, changes=[], ordinal=ordinal)
            if row["errors"]:
                continue
            if equal:
                line = matching[digest(row["facts"])].popleft()
                row.update(action="UNCHANGED", existing_id=line.id, ordinal=line.ordinal)
            elif upgrade_matches:
                line = upgrade_matches[row["row_key"]]
                previous = json.loads(line.payload_json)
                action = "UNCHANGED" if previous == row["facts"] else "UPDATE"
                row.update(action=action, existing_id=line.id, previous=previous, ordinal=line.ordinal,
                           changes=[key for key, val in row["facts"].items() if previous.get(key) != val])
            elif old:
                previous = old_facts[0]
                row.update(action="UPDATE", existing_id=old[0].id, previous=previous, ordinal=old[0].ordinal,
                           changes=[key for key, val in row["facts"].items() if previous.get(key) != val])
            else:
                row["action"] = "NEW"
                if inactive := resurrection.get(row["row_key"]):
                    row.update(existing_id=inactive.id, ordinal=inactive.ordinal)
                else:
                    row["ordinal"] = next_ordinal
                    next_ordinal += 1
    targets = defaultdict(list)
    for row in parsed["rows"]:
        if row["existing_id"]:
            targets[row["existing_id"]].append(row)
    for group in targets.values():
        if len(group) > 1:
            for row in group:
                row["action"] = "BLOCKED"
                row["errors"].append("多条采购来源指向同一仓库明细，请明确对应关系，不能重复覆盖")
    return parsed


def counts(rows):
    actions = Counter(row["action"] for row in rows)
    return {"total": len(rows), "new": actions["NEW"], "updated": actions["UPDATE"], "unchanged": actions["UNCHANGED"], "blocked": actions["BLOCKED"],
            "warnings": sum(bool(row["warnings"]) for row in rows), "pending": sum(row["facts"]["status"] == "PENDING" for row in rows),
            "returned": sum(row["facts"]["status"] == "RETURNED" for row in rows)}


def preview_token(parsed, actor_id, expected_revision):
    return digest([PARSER_VERSION, FACTORY, actor_id, expected_revision, parsed["source_digest"], parsed["scope"]])


def preview(db, parsed, actor_id, *, offset=0, limit=100, action="ALL"):
    ensure_schema(db)
    expected_revision = revision(db)
    prepare(db, parsed)
    rows = parsed["rows"]
    filtered = rows if action == "ALL" else [row for row in rows if row["action"] == action]
    # Raw cells/formulas stay on the server and in immutable source evidence.
    result_rows = [{k: v for k, v in row.items() if k not in {"raw", "identity_key", "ordinal", "bind_line_id", "expected_line_revision"}} for row in filtered[offset:offset + limit]]
    return {"preview_token": preview_token(parsed, actor_id, expected_revision), "revision": expected_revision,
            "source_digest": parsed["source_digest"], "counts": counts(rows), "sheets": parsed["sheets"], "ignored_sheets": parsed["ignored_sheets"],
            "excluded_history": parsed.get("excluded_history", 0),
            "filtered_total": len(filtered), "offset": offset, "limit": limit, "items": result_rows}


def apply(db, parsed, actor, filename, request_id, token, *, confirmed, acknowledge_excluded):
    ensure_schema(db)
    if not confirmed:
        raise HTTPException(422, "请核对预览后明确确认导入")
    state = lock_factory(db)
    request_hash = digest([parsed["source_digest"], parsed["scope"], actor.id])
    prior = db.scalar(select(FabricProcurementImport).where(FabricProcurementImport.factory_id == FACTORY, FabricProcurementImport.request_id == request_id))
    if prior:
        if prior.request_hash != request_hash:
            raise HTTPException(409, "重复请求编号对应不同文件或范围，请重新核对")
        if json.loads(prior.result_json).get("withdrawal"):
            raise HTTPException(409, "这次导入已撤销；需要重新导入时请重新预览并确认")
        db.rollback()
        return json.loads(prior.result_json)
    if token != preview_token(parsed, actor.id, state.revision):
        raise HTTPException(409, "文件、账号或采购资料已变化，请重新预览后导入")
    prepare(db, parsed)
    summary = counts(parsed["rows"])
    if summary["blocked"] and not acknowledge_excluded:
        raise HTTPException(422, "存在异常明细，请确认仅导入可用明细，异常行继续核对")
    if summary["new"] + summary["updated"] + summary["unchanged"] == 0:
        raise HTTPException(422, "没有可用明细，请先修正原表")
    now, batch_id = business_now().isoformat(), uuid4().hex
    result = {"id": batch_id, "source_name": filename, "occurred_at": now, "actor_name": actor.display_name,
              "scope": parsed["scope"], "counts": summary, "stock_posted": False, "sequence": state.revision + 1}
    batch = FabricProcurementImport(id=batch_id, factory_id=FACTORY, request_id=request_id, request_hash=request_hash,
                                  source_name=filename, actor_id=actor.id, actor_name=actor.display_name, occurred_at=now, result_json=dump(result))
    db.add(batch)
    db.flush()
    lines = {line.id: line for line in db.scalars(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == FACTORY))}
    evidences = []
    for row in parsed["rows"]:
        if row["action"] in {"BLOCKED", "UNCHANGED"}:
            continue
        facts = row["facts"]
        line = lines.get(row["existing_id"])
        if line is None:
            line = FabricProcurementLine(id=uuid4().hex, factory_id=FACTORY, identity_key=row["identity_key"], ordinal=row["ordinal"], revision=0)
            db.add(line)
        previous = "{}" if line.status == "WITHDRAWN" else line.payload_json or "{}"
        line.status, line.order_no, line.supplier, line.material_code, line.production_no = (facts[k] for k in ("status", "order_no", "supplier", "material_code", "production_no"))
        line.payload_json, line.updated_at, line.revision = dump(facts), now, line.revision + 1
        evidences.append(FabricProcurementEvidence(id=uuid4().hex, factory_id=FACTORY, line_id=line.id, import_id=batch_id,
                                        sheet=row["sheet"], row_number=row["row_number"], before_json=previous,
                                        after_json=dump(facts), raw_json=dump({**row["raw"], "warnings": row["warnings"]})))
    db.flush()
    db.add_all(evidences)
    state.revision += 1
    db.commit()
    return result


def list_lines(db, status="PENDING", search="", offset=0, limit=50, view=None, filters=None, sort="UPDATED"):
    ensure_schema(db)
    where = [FabricProcurementLine.factory_id == FACTORY, FabricProcurementLine.status != "WITHDRAWN"]
    if status != "ALL" and not view:
        where.append(FabricProcurementLine.status == status)
    if search.strip():
        pattern = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(or_(*[column.ilike(pattern, escape="\\") for column in (FabricProcurementLine.order_no, FabricProcurementLine.supplier, FabricProcurementLine.material_code, FabricProcurementLine.production_no, FabricProcurementLine.payload_json)]))
    from app.services.fabric_procurement_tracking import tracking_context, line_tracking
    context = tracking_context(db)
    lines = db.scalars(select(FabricProcurementLine).where(*where).order_by(FabricProcurementLine.updated_at.desc(), FabricProcurementLine.id))
    items = [{"id": line.id, "revision": line.revision, "updated_at": line.updated_at, "facts": json.loads(line.payload_json),
              **line_tracking(line, context)} for line in lines]
    from app.services.fabric_master import material_info, records
    master_records = records(db)
    for item in items:
        item.update(material_info(item["facts"], master_records))
    from app.services.fabric_procurement_tracking import batches
    options = {"suppliers": sorted({item["facts"]["supplier"] for item in items}), "units": sorted({item["facts"]["unit"] for item in items}),
               "imports": [{"id": b.id, "name": b.source_name + " · " + b.occurred_at[:16]} for b in batches(db) if not json.loads(b.result_json).get("withdrawal")]}
    filters = filters or {}
    if filters.get("promise_from") and filters.get("promise_to") and filters["promise_from"] > filters["promise_to"]:
        raise HTTPException(422, "复期开始日期不能晚于结束日期")
    if sort in {"QUANTITY_ASC", "QUANTITY_DESC"} and not filters.get("unit"):
        raise HTTPException(422, "按数量排序须先选择同一单位")
    batch_lines = None
    if filters.get("import_batch"):
        batch = db.scalar(select(FabricProcurementImport).where(FabricProcurementImport.factory_id == FACTORY, FabricProcurementImport.id == filters["import_batch"]))
        batch_lines = set(db.scalars(select(FabricProcurementEvidence.line_id).where(FabricProcurementEvidence.factory_id == FACTORY, FabricProcurementEvidence.import_id == filters["import_batch"]))) if batch and not json.loads(batch.result_json).get("withdrawal") else set()
    def matches(item):
        facts = item["facts"]
        for field in ("supplier", "unit", "source_category"):
            if filters.get(field) and facts.get(field, "PURCHASE" if field == "source_category" else "") != filters[field]:
                return False
        for field in ("order_no", "production_no", "material_code", "style_no"):
            if filters.get(field) and filters[field].casefold() not in str(facts.get(field, "")).casefold():
                return False
        if filters.get("category") and (item["material_category"] or "UNCLASSIFIED") != filters["category"]:
            return False
        review = filters.get("quantity_review")
        if review and bool(item["receipt_quantity_review_required"]) != (review == "REVIEW"):
            return False
        if batch_lines is not None and item["id"] not in batch_lines:
            return False
        for key, op in (("promise_from", lambda a, b: a >= b), ("promise_to", lambda a, b: a <= b)):
            if filters.get(key) and (not item["promise_date"] or not op(item["promise_date"], filters[key])):
                return False
        return True
    items = [item for item in items if matches(item)]
    summary = {key: sum(item["tracking"][key] for item in items) for key in ("outstanding", "not_arrived", "partial", "arrival_review", "changed", "overdue", "due_today", "awaiting_date", "quantity_review")}
    if view:
        items = [item for item in items if item["tracking"][view.lower()]]
    items.sort(key=lambda item: item["id"])
    if sort == "UPDATED":
        items.sort(key=lambda item: item["updated_at"], reverse=True)
    elif sort == "OVERDUE":
        items.sort(key=lambda item: (not item["tracking"]["overdue"], -item["overdue_days"], item["promise_date"] or "9999", item["facts"]["order_no"]))
    elif sort == "PROMISE":
        items.sort(key=lambda item: (item["promise_date"] or "9999", item["facts"]["order_no"]))
    elif sort in {"ORDER", "SUPPLIER"}:
        field = "order_no" if sort == "ORDER" else "supplier"
        items.sort(key=lambda item: item["facts"][field].casefold())
    elif sort in {"QUANTITY_ASC", "QUANTITY_DESC"}:
        known = [item for item in items if item["warehouse_outstanding_quantity"] is not None]
        unknown = [item for item in items if item["warehouse_outstanding_quantity"] is None]
        known.sort(key=lambda item: number(item["warehouse_outstanding_quantity"]), reverse=sort == "QUANTITY_DESC")
        items = known + unknown
    return {"total": len(items), "offset": offset, "limit": limit, "summary": summary, "options": options, "items": items[offset:offset + limit]}


def line_detail(db, line_id):
    ensure_schema(db)
    line = db.scalar(select(FabricProcurementLine).where(FabricProcurementLine.factory_id == FACTORY, FabricProcurementLine.id == line_id))
    if not line:
        raise HTTPException(404, "找不到该厂区的采购明细")
    sources = db.execute(select(FabricProcurementEvidence, FabricProcurementImport).join(FabricProcurementImport, FabricProcurementEvidence.import_id == FabricProcurementImport.id).where(FabricProcurementEvidence.factory_id == FACTORY, FabricProcurementEvidence.line_id == line.id).order_by(FabricProcurementImport.occurred_at.desc()).limit(100))
    from app.services.fabric_procurement_tracking import tracking_context, line_tracking
    from app.services.fabric_master import material_info, records, ready
    from app.models.fabric_master import FabricChaseResolution
    resolutions = list(db.scalars(select(FabricChaseResolution).where(FabricChaseResolution.factory_id == FACTORY, FabricChaseResolution.source_line_id == line_id).order_by(FabricChaseResolution.revision.desc()))) if ready(db) else []
    return {"id": line.id, "active": line.status != "WITHDRAWN", "facts": json.loads(line.payload_json), "revision": line.revision, **line_tracking(line, tracking_context(db)),
            **material_info(json.loads(line.payload_json), records(db)),
            "available_locations": [{"id": r.id, "label": f"{json.loads(r.data_json).get('warehouse', '')}／{r.code}", "code": r.code, "name": r.name, "warehouse": json.loads(r.data_json).get("warehouse", "")} for r in records(db) if r.kind == "LOCATION" and r.status == "ACTIVE"],
            "chase_resolution_history": [{"id": r.id, "revision": r.revision, "starting_quantity": r.starting_quantity, "evidence": r.evidence, "cutoff": json.loads(r.cutoff_json), "actor_name": r.actor_name, "occurred_at": r.occurred_at} for r in resolutions],
            "evidence": [{"id": evidence.id, "withdrawal": json.loads(batch.result_json).get("withdrawal"), "source_name": batch.source_name, "sheet": evidence.sheet, "row_number": evidence.row_number,
                          "actor_name": batch.actor_name, "occurred_at": batch.occurred_at,
                          "before": json.loads(evidence.before_json), "after": json.loads(evidence.after_json), "raw": json.loads(evidence.raw_json)} for evidence, batch in sources]}
