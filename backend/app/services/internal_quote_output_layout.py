"""Output-layout reads, non-persisting previews and atomic source-field edits."""
import hashlib
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal_quote import InternalQuoteAlternative, InternalQuoteAttachment, InternalQuoteSection
from app.schemas.internal_quote import InternalQuoteCostPreviewRequest, InternalQuoteWholeProductSaveRequest
from app.services.auth import AuthContext
from app.services.internal_quote import (
    ALL_QUOTE_DEPARTMENTS, MUTABLE_SECTION_STATUSES, _cost_context, _find_reference_set,
    _get_quote, _json_object, _rr2_cost_summary, ensure_quote_permission,
    ensure_section_permission, preview_quote_costs, quote_write, save_whole_product_sections,
    _can_project_molding_read, _project_molding_parts, _molding_projection_warning,
    molding_projection_pending,
)
from app.services.internal_quote_calculator import canonical_json
from app.services.internal_quote_document import document_archive
from app.services.internal_quote_excel import build_internal_quote_workbook_model
from app.services.internal_quote_output_fields import source_groups
from app.services.internal_quote_workbook_view import serialize_workbook


class OutputCellEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(min_length=1, max_length=512)
    value: StrictStr | StrictInt | StrictFloat | None


class OutputLayoutEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_token: str = Field(min_length=64, max_length=64)
    edits: list[OutputCellEdit] = Field(min_length=1, max_length=2000)


def _load(db, quote_id, user):
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(db, user, "internal_quote:summary_read", quote.factory_id, ALL_QUOTE_DEPARTMENTS)
    sections = list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote_id)).all())
    reference = _find_reference_set(db, quote)
    if reference is None:
        raise HTTPException(409, "报价缺少参考资料，请返回填写页重新读取")
    alternative = db.get(InternalQuoteAlternative, quote_id)
    archive = document_archive(db, quote)
    locked = bool(quote.status in {"archived", "exported", "released", "final_pending", "final_reviewing", "fully_approved"}
                  or quote.final_release_status in {"issued", "approved", "pending"}
                  or archive or (alternative and alternative.archived))
    identity = [quote.id, quote.header_revision, quote.reference_snapshot_id, quote.status, quote.final_release_status,
                bool(alternative and alternative.archived), archive, reference.sha256,
                [(s.department, s.revision, s.status, s.is_required, s.payload_json, s.calculation_json,
                  s.calculation_status, s.dependency_status) for s in sorted(sections, key=lambda s: s.department)]]
    token = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    editable = set()
    if not locked:
        for section in sections:
            if not section.is_required or section.status not in MUTABLE_SECTION_STATUSES:
                continue
            try:
                ensure_section_permission(db, user, quote.factory_id, section.department, "edit")
                editable.add(section.department)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
    return quote, sections, reference, token, editable


def _projection_pending(db, quote, sections):
    molding = next((s for s in sections if s.department == "molding"), None)
    return bool(molding and _can_project_molding_read(db, quote, molding)
                and molding_projection_pending(db, quote, sections))


def _prepare(db, quote_id, request, user):
    quote, sections, reference, token, editable = _load(db, quote_id, user)
    if token != request.base_token:
        raise HTTPException(409, "报价已发生变化，当前表格修改尚未保存。请重新读取并核对后再修改")
    if _projection_pending(db, quote, sections):
        raise HTTPException(409, _molding_projection_warning()["message"] + "请先返回填写页同步，再修改输出表格。")
    fields = {field["id"]: (group, field) for group in source_groups(sections, quote.region_code) for field in group["fields"]}
    by_code = {s.department: s for s in sections}
    payloads, seen = {}, set()
    for edit in request.edits:
        if edit.field_id in seen or edit.field_id not in fields:
            raise HTTPException(400, "只允许修改现有名称和原始单价；新增、删除请返回填写页")
        seen.add(edit.field_id)
        group, field = fields[edit.field_id]
        code = group["section"]
        ensure_section_permission(db, user, quote.factory_id, code, "edit")
        if code not in editable:
            raise HTTPException(409, "当前方案版本或部门已锁定，请返回填写页处理或复制新版本")
        if field["kind"] == "name":
            if not isinstance(edit.value, str) or not edit.value.strip() or len(edit.value) > 500:
                raise HTTPException(400, "名称不能为空，且不能超过 500 字")
            value = edit.value.strip()
        elif edit.value in (None, "") and field["nullable"]:
            value = None
        else:
            try:
                number = Decimal(str(edit.value))
                if not number.is_finite() or number < 0 or number > Decimal("1000000000"):
                    raise ValueError()
            except (InvalidOperation, ValueError):
                raise HTTPException(400, f"{field['label']}必须是有效的非负金额")
            value = str(number)
        if code not in payloads:
            payloads[code] = _json_object(by_code[code].payload_json)
        parent = payloads[code]
        for key in field["path"][:-1]:
            parent = parent[key]
        parent[field["path"][-1]] = value

    # Engineering can invalidate molding's saved dependency snapshot. Include
    # the unchanged downstream inputs in the same transaction and revision check.
    if "engineering" in payloads:
        molding = by_code.get("molding")
        if molding and molding.is_required and molding.filled_at:
            if "molding" not in editable:
                raise HTTPException(409, "模具修改需要同时重算啤机资料，请先将相关部门退回可编辑状态")
            payloads.setdefault("molding", _json_object(molding.payload_json))
    sales = by_code.get("sales")
    if sales and sales.is_required and sales.filled_at and "sales" in editable:
        payloads.setdefault("sales", _json_object(sales.payload_json))
    engineering = by_code.get("engineering")
    if "molding" in payloads and engineering and engineering.is_required and engineering.status != "not_applicable":
        payloads["molding"] = _project_molding_parts(
            payloads.get("engineering", _json_object(engineering.payload_json)), payloads["molding"],
        )
    drafts = [{"section_code": code, "revision": by_code[code].revision, "payload": payload}
              for code, payload in payloads.items()]
    preview = preview_quote_costs(db, quote_id, InternalQuoteCostPreviewRequest(drafts=drafts), user)
    for code, calculation in preview.calculations.items():
        if calculation.get("status") != "valid":
            warnings = calculation.get("warnings", [])
            detail = "；".join(str(w.get("message", "")) for w in warnings if isinstance(w, dict))
            raise HTTPException(400, f"{by_code[code].department_name}需要核对：{detail or '资料不完整，请返回填写页补全'}")
    return (quote, sections, reference, token, editable), drafts, preview


def _bind_aggregate_cells(workbook, groups):
    """Aggregates open explicit source rows; never treat an HKD total as a price."""
    ids = {g["id"] for g in groups}
    section_groups = {}
    for group in groups:
        section_groups.setdefault(group["section"], []).append(group["id"])
    departments = {"装配工": ["assembly"], "喷油工": ["painting"], "油漆": ["painting"],
                   "搪胶": ["slush"], "车发": ["hair"], "车衣": ["sewing"], "啤工": ["molding"],
                   "料价": ["engineering", "molding"], "纸箱": ["sales"], "印尼运费": ["sales"],
                   "电子": ["electronic"]}
    for sheet in workbook:
        if sheet.sheet_state != "visible":
            continue
        bindings = getattr(sheet, "_quote_bindings", {})
        sheet._quote_bindings = bindings
        for address, binding in list(bindings.items()):
            if binding.get("group") not in ids:
                del bindings[address]
        if sheet.title.startswith("电子明细"):
            suffix = sheet.title.removeprefix("电子明细")
            prefix = f"electronic:quote_groups/{int(suffix) - 1}/" if suffix.isdigit() else "electronic:"
            row_groups = [g for g in groups if g["id"].startswith(prefix) and any(f["kind"] == "price" for f in g["fields"])]
            for index, group in enumerate(row_groups, 4):
                bindings[f"B{index}"] = {"group": group["id"], "kind": "name"}
                price = next(f for f in group["fields"] if f["kind"] == "price")
                bindings[f"{'E' if price['currency'] == 'RMB' else 'F'}{index}"] = {"group": group["id"], "kind": "price"}
            continue
        if sheet.title != "报价明细":
            continue
        for row in sheet:
            if len(row) < 4:
                continue
            category = str(row[1].value or "")
            group_ids = [key for code in departments.get(category, []) for key in section_groups.get(code, [])]
            if group_ids:
                for cell in row[2:4]:
                    bindings.setdefault(cell.coordinate, {"groups": group_ids, "kind": "source"})
            if isinstance(row[0].value, int) and row[0].value > 0 and row[2].value:
                # The generated mold schedule uses numbered rows; source names
                # may be composite, so show the explicitly labelled source list.
                molds = [g["id"] for g in groups if g["category"] in {"模具", "模具零件", "注塑"}]
                if molds:
                    bindings.setdefault(row[2].coordinate, {"groups": molds, "kind": "source"})


def _render(db, loaded, preview=None, drafts=()):
    quote, sections, reference, token, editable = loaded
    snapshot = _json_object(reference.snapshot_json)
    projection_pending = _projection_pending(db, quote, sections)
    # Detached copies: all display/preview changes must leave persisted rows intact.
    sections = [SimpleNamespace(**{c.key: getattr(s, c.key) for c in s.__table__.columns}) for s in sections]
    if projection_pending:
        for section in sections:
            if section.department == "molding":
                section.calculation_status = section.dependency_status = "stale"
                section.calculation_json = canonical_json({"status": "stale", "warnings": [_molding_projection_warning()]})
        editable = set()
    context = _cost_context(db, quote, calculation_overrides={"molding": {"status": "stale"}} if projection_pending else None)
    summary = _rr2_cost_summary([s for s in sections if s.is_required], context, snapshot, quote.qty, factory_id=quote.factory_id)
    if quote.module_version == "v4" and quote.final_release_status == "issued":
        summary = _json_object(quote.final_submission_manifest_json).get("rr2_cost_summary", summary)
    if preview is not None:
        overridden = {d["section_code"]: d["payload"] for d in drafts}
        for section in sections:
            if section.department in overridden:
                section.payload_json = canonical_json(overridden[section.department])
                section.calculation_json = canonical_json(preview.calculations[section.department])
                section.calculation_status = "valid"
                section.dependency_status = "current"
        context = {**context, **preview.components_hkd, "factory_price_hkd": preview.preview_factory_price_hkd}
        summary = preview.rr2_cost_summary
    groups = source_groups(sections, quote.region_code)
    for group in groups:
        group["editable"] = group["section"] in editable
    # Only product/component images are needed by the generated layout. Source
    # workbooks remain stored on the original form and never become output tabs.
    attachments = list(db.scalars(select(InternalQuoteAttachment).where(
        InternalQuoteAttachment.quote_id == quote.id,
        InternalQuoteAttachment.content_type.like("image/%"),
    )).all())
    workbook = build_internal_quote_workbook_model(quote, sections, {}, snapshot, summary, context, attachments, allow_incomplete=True)
    try:
        _bind_aggregate_cells(workbook, groups)
        sheets, errors = serialize_workbook(workbook)
    finally:
        workbook.close()
    for group in groups:
        for field in group["fields"]:
            field.pop("path")
    warnings = [{"message": f"{s.department_name}资料尚未完成或需要重新计算，当前合计不完整。"}
                for s in sections if s.is_required and (s.calculation_status != "valid" or s.dependency_status != "current")]
    warnings.extend(warning for section in sections if section.is_required and section.department == "sewing"
                    for warning in _json_object(section.calculation_json).get("warnings", [])
                    if warning.get("code") == "sewing_quoted_price_pending")
    if projection_pending:
        warnings.append(_molding_projection_warning())
    return {"quote_id": quote.id, "version_label": quote.version_label, "base_token": token,
            "sheets": sheets, "groups": groups, "formula_errors": errors,
            "factory_price_hkd": str(context["factory_price_hkd"]), "preview": preview is not None,
            "read_only": not editable, "warnings": [*warnings, *(preview.warnings if preview is not None else [])]}


def get_output_layout(db: Session, quote_id: str, user: AuthContext):
    return _render(db, _load(db, quote_id, user))


def preview_output_layout(db: Session, quote_id: str, payload: OutputLayoutEdits, user: AuthContext):
    loaded, drafts, preview = _prepare(db, quote_id, payload, user)
    return _render(db, loaded, preview, drafts)


@quote_write
def save_output_layout(db: Session, quote_id: str, payload: OutputLayoutEdits, user: AuthContext, request: Request | None = None):
    _, drafts, _ = _prepare(db, quote_id, payload, user)
    # Already under quote_write's lock; ordinary section saving retains audit,
    # permission checks, dependency invalidation and one all-or-nothing commit.
    return save_whole_product_sections.__wrapped__(
        db, quote_id, InternalQuoteWholeProductSaveRequest(sections=drafts, reason="在输出表格修改名称与原始单价"), user, request,
    )
