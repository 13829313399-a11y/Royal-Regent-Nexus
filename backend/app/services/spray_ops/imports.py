"""Immutable source evidence and per-document atomic import confirmation."""
from collections import defaultdict
import hashlib
from sqlalchemy import select

from app.models import spray_ops as m
from . import schemas as s, production, handover, materials, finance, history
from .common import add, get, scoped, serialize, require, version, touch, digest, check_period
from .source_reader import PROFILES, read_source

TARGETS = {
    "opening": (s.OpeningCreate, history.create_opening, ("stock_write", "import")),
    "demand": (s.DemandCreate, production.create_demand, ("plan", "cost_write")),
    "batch": (s.BatchCreate, production.create_batch, ("stock_write",)),
    "delivery": (s.DeliveryCreate, handover.create_delivery, ("stock_write",)),
    "return": (s.ReturnCreate, handover.return_goods, ("stock_write",)),
    "container": (s.ContainerCreate, handover.container, ("stock_write",)),
    "report": (s.ReportCreate, production.create_report, ("report",)),
    "expense": (s.ExpenseCreate, finance.expense, ("cost_write",)),
    "purchase": (s.PurchaseCreate, materials.create_purchase, ("procure", "cost_write")),
    "material_receipt": (s.MaterialReceiptCreate, materials.receipt, ("procure", "stock_write")),
    "saving": (s.SavingCreate, materials.saving, ("cost_write",)),
    "settlement": (s.SettlementCreate, finance.create_settlement, ("settle", "cost_read")),
}


def source_permissions(source):
    return ("import",) + (("cost_read",) if source.cost_sensitive else ()) + (("payroll_read",) if source.payroll_sensitive else ())


def source_metadata(source):
    return {key: value for key, value in serialize(source).items() if key != "payload"}


def upload(db, f, b, name, payload, parsed):
    require(b.expected_version == 0 and b.profile in PROFILES, "import_profile", "请选择支持的导入配置", 422)
    profile = PROFILES[b.profile]
    old = db.scalar(scoped(db, m.SprayOpsSource, f).where(m.SprayOpsSource.sha256 == parsed["sha256"]))
    if old:
        # A later more-sensitive interpretation must never weaken source access.
        old.payroll_sensitive = old.payroll_sensitive or profile["payroll"]
        return source_metadata(old)
    source = add(db, m.SprayOpsSource, f, name=name, sha256=parsed["sha256"], format=parsed["format"], payload=payload, cost_sensitive=True, payroll_sensitive=profile["payroll"])
    return {**source_metadata(source), "summary": dict(sheets=[dict(name=sheet["name"], state=sheet["state"], cells=len(sheet["cells"])) for sheet in parsed["sheets"]], warnings=parsed["warnings"], pages=parsed.get("pages"))}


def source_view(source, parsed, sheet_name=None, page=1, page_size=50):
    selected = next((sheet for sheet in parsed["sheets"] if sheet["name"] == sheet_name), parsed["sheets"][0] if parsed["sheets"] else None)
    grouped = defaultdict(list)
    if selected:
        for cell in selected["cells"]:
            grouped[cell["row"]].append(cell)
    records = [dict(row=row, cells=sorted(grouped[row], key=lambda cell: cell["column"])) for row in sorted(grouped)]
    return dict(source=source_metadata(source), epoch=parsed.get("epoch"), pages=parsed.get("pages"), sheets=[dict(name=sheet["name"], state=sheet["state"], cells=len(sheet["cells"])) for sheet in parsed["sheets"]], sheet=selected["name"] if selected else None, rows=records[(page - 1) * page_size:page * page_size], total=len(records), warnings=parsed["warnings"])


def preview(db, f, b, parsed):
    source = get(db, m.SprayOpsSource, f, b.source_id)
    require(b.profile in PROFILES, "import_profile", "导入配置不存在", 422)
    require(b.expected_version == 0, "version_conflict", "修改映射或决策后须建立新的预览")
    require(len({doc.document_key for doc in b.documents}) == len(b.documents), "duplicate_document", "业务单据键不能重复", 422)
    decisions, warnings = [], list(parsed["warnings"])
    for doc in b.documents:
        require(doc.target in PROFILES[b.profile]["targets"], "profile_target", "该资料不能直接产生此类业务事实", 422)
        require(doc.mode != "opening" or doc.target in {"reference", "opening"}, "opening_review_required", "期初不能混入普通来料或生产实绩", 422)
        require(doc.target != "opening" or doc.mode == "opening", "opening_mode", "期初结余必须明确选择期初口径", 422)
        if doc.mode in {"opening", "replay"} and doc.target != "reference":
            policy = history.policy(db,f)
            require(policy and policy.mode == doc.mode, "history_policy", "请先确认本工厂采用期初或逐笔重放，不能两者叠加")
        require(doc.mode != "historical_reference" or doc.target == "reference", "historical_replay_blocked", "历史参考资料不能直接重复生成生产或库存", 422)
        sheet = next((item for item in parsed["sheets"] if item["name"] == doc.sheet), None)
        evidence = []
        if parsed["format"] == "PDF":
            require(doc.sheet == "PDF" and all(coord.startswith("page:") and coord[5:].isdigit() and 1 <= int(coord[5:]) <= parsed["pages"] for coord in doc.coordinates), "source_coordinate", "PDF 证据必须指定有效页码", 422)
        else:
            require(sheet is not None, "source_sheet", "来源工作表不存在", 422)
            by_coordinate = {cell["coordinate"]: cell for cell in sheet["cells"]}
            require(set(doc.coordinates) <= by_coordinate.keys(), "source_coordinate", "来源坐标不存在或为空白", 422)
            evidence = [by_coordinate[coordinate] for coordinate in doc.coordinates]
        flags = sorted({flag for cell in evidence for flag in cell["flags"]})
        if any(str(cell.get("raw_value", "")).startswith("-") for cell in evidence):
            flags.append("negative_source_requires_match")
            require(doc.target in {"return", "reference", "expense", "saving"}, "negative_source", "含负数来源必须按退货、贷项或参考差异人工匹配，不能正常入库/报工", 422)
        values = doc.values
        if doc.target != "reference":
            schema, _, _ = TARGETS[doc.target]
            # Validated typed commands are frozen in preview. No arbitrary domain
            # blob is interpreted by the confirmation endpoint.
            typed = schema.model_validate(dict(values, factory_id=f, operation_id="preview", expected_version=values.get("expected_version", 0)))
            require(str(typed.business_date).startswith(b.business_month), "import_month_mismatch", "业务日期必须属于所选导入月份", 422)
            values = typed.model_dump(mode="json", exclude={"factory_id", "operation_id"})
        key = digest(dict(sheet=doc.sheet, coordinates=sorted(set(doc.coordinates))))
        semantic = digest(dict(target=doc.target, document_no=values.get("document_no", doc.document_key), business_date=values.get("business_date", b.business_month), identity={key: values.get(key) for key in ("counterparty", "supplier", "delivery_line_id", "purchase_line_id")}))
        prior = db.scalar(scoped(db, m.SprayOpsImportFact, f).where(m.SprayOpsImportFact.fact_category == doc.target, m.SprayOpsImportFact.semantic_key == semantic))
        decisions.append(dict(**doc.model_dump(exclude={"values"}), values=values, source_key=key, semantic_key=semantic, evidence=evidence, flags=flags, conflict_id=prior.id if prior else None))
    snapshot = dict(source_sha256=source.sha256, profile=b.profile, profile_version=1, mappings=b.mappings, business_month=b.business_month, documents=decisions, warnings=warnings)
    job = add(db, m.SprayOpsImport, f, source_id=source.id, profile=b.profile, status="review", snapshot=snapshot, fingerprint=digest(snapshot))
    return detail(db, f, job)


def detail(db, f, job):
    facts = production.rows(db, m.SprayOpsImportFact, f, import_id=job.id)
    return {**serialize(job), "confirmed": [dict(document_key=fact.decision["document_key"], target_id=fact.target_id, id=fact.id) for fact in facts]}


def cancel(db, f, job_id, b):
    job = get(db, m.SprayOpsImport, f, job_id)
    version(job, b.expected_version)
    require(job.status in {"review", "partial"}, "import_state", "该预览已结束")
    job.status = "cancelled"
    touch(job)
    return {**detail(db, f, job), "reason": b.reason}


def confirmation_permissions(db, f, job_id, b):
    job = get(db, m.SprayOpsImport, f, job_id)
    source = get(db, m.SprayOpsSource, f, job.source_id)
    doc = next((doc for doc in job.snapshot["documents"] if doc["document_key"] == b.document_key), None)
    require(doc is not None, "document_not_found", "预览中不存在此业务单据", 404)
    return source_permissions(source) + (TARGETS[doc["target"]][2] if doc["target"] != "reference" else ())


def confirm(db, f, job_id, b):
    job = get(db, m.SprayOpsImport, f, job_id)
    version(job, b.expected_version)
    require(job.status in {"review", "partial"}, "import_state", "此预览已结束，不能继续确认")
    require(job.fingerprint == b.fingerprint == digest(job.snapshot), "stale_import_preview", "预览内容已变化，请重新映射和核对")
    source = get(db, m.SprayOpsSource, f, job.source_id)
    require(hashlib.sha256(source.payload).hexdigest() == job.snapshot["source_sha256"], "source_changed", "来源文件与预览不一致")
    doc = next((doc for doc in job.snapshot["documents"] if doc["document_key"] == b.document_key), None)
    require(doc is not None, "document_not_found", "业务单据不在此预览", 404)
    prior = db.scalar(scoped(db, m.SprayOpsImportFact, f).where(m.SprayOpsImportFact.fact_category == doc["target"], ((m.SprayOpsImportFact.source_id == source.id) & (m.SprayOpsImportFact.source_key == doc["source_key"])) | (m.SprayOpsImportFact.semantic_key == doc["semantic_key"])))
    require(prior is None, "duplicate_source_fact", "相同来源或跨文件同一业务事实已导入，须核对主事实来源")
    if doc["target"] == "reference":
        target_id = source.id
    else:
        schema, handler, _ = TARGETS[doc["target"]]
        typed = schema.model_validate(dict(doc["values"], factory_id=f, operation_id=b.operation_id))
        if getattr(typed, "business_date", None):
            check_period(db, f, typed.business_date)
            if doc['target'] not in {'opening','demand'}:
                history.guard_date(db,f,typed.business_date)
        result = handler(db, f, typed)
        target_id = result["id"]
    add(db, m.SprayOpsImportFact, f, import_id=job.id, source_id=source.id, fact_category=doc["target"], source_key=doc["source_key"], semantic_key=doc["semantic_key"], target_id=target_id, decision=doc)
    confirmed = len(production.rows(db, m.SprayOpsImportFact, f, import_id=job.id))
    job.status = "completed" if confirmed == len(job.snapshot["documents"]) else "partial"
    touch(job)
    return detail(db, f, job)
