"""Download-only PDF drafts: no order identity, bindings or QC records are created."""
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore

from fastapi import HTTPException
from pypdf import PdfReader

from app.core.config import settings
from app.services import carton_supplier_portal as portal
from app.services import carton_supplier_mark_ai as ai
from app.services.carton_mark import MAX_DOCUMENT_FILE_BYTES, extract_excel_document_items, CartonMarkDocumentError
from app.services.document_tools.document_ir import ToolError
from app.services.document_tools.storage import root, safe_name

_SLOTS = BoundedSemaphore(1)


def access(db, user, factory=""):
    if not settings.document_tools_enabled:
        raise HTTPException(503, "文档转换服务暂未启用")
    if factory:
        suppliers = [portal.supplier_access(db, user, factory, "carton_supplier:edit")]
    else:
        suppliers = [s for s in portal.supplier_factories(db, user)
                     if portal.supplier_permission(user, "carton_supplier:edit", s.factory_id)]
    if not suppliers:
        raise HTTPException(403, "当前账号没有箱唛资料生成权限")
    return sorted((s.factory_id, s.id) for s in suppliers)


def source(db, user, factory, asset_id, revision):
    if not factory or revision < 1:
        raise HTTPException(422, "资料库原稿须保留所属厂区和版本")
    portal.supplier_access(db, user, factory, "carton_supplier:edit")
    row = next((r for r in portal.supplier_mark_assets(db, user, factory, asset_ids=[asset_id])
                if r["id"] == asset_id), None)
    if row is None:
        raise HTTPException(404, "未找到可用于生成的 Excel 原稿")
    if row["revision"] != revision:
        raise HTTPException(409, "Excel 原稿已变化，请刷新后重新选择")
    if row["kind"] != "excel" or row["workflow"]["status"] == "HISTORY":
        raise HTTPException(422, "请选择当前版本的 Excel 原稿")
    asset = portal.supplier_mark_asset_document(db, user, factory, asset_id)
    content = bytes(asset.content)
    if hashlib.sha256(content).hexdigest() != asset.sha256:
        raise HTTPException(409, "Excel 原稿完整性校验失败")
    return dict(name=asset.file_name, content=content, sha256=asset.sha256, revision=asset.revision)


def original(name, content, engine, consent, supplements):
    name = safe_name(name)
    if Path(name).suffix.lower() not in {".xls", ".xlsx"}:
        raise HTTPException(422, "请选择 .xls / .xlsx 文件")
    if not 0 < len(content) <= MAX_DOCUMENT_FILE_BYTES:
        raise HTTPException(413, "Excel 文件须为 1 字节至 20 MB")
    if set(supplements) - {"quantity", "carton_total"} or any(
            not isinstance(v, str) or len(v) > 100 for v in supplements.values()):
        raise HTTPException(422, "此审阅稿仅支持补齐每箱数量和总箱数")
    if engine == "excel_original" and supplements:
        raise HTTPException(422, "原版导出不修改 Excel 内容，请在原文件中补齐")
    result = dict(excel_file_name=name, excel_bytes=content, unbound=True, contract_no="", item_no="",
                  issue_id="", supplements=supplements, order_fields={}, source_item="")
    if engine == "deepseek_zumiez":
        if not consent:
            raise HTTPException(422, "请先同意发送本次必要文字给 DeepSeek")
        from app.services import carton_mark_kroger as kroger
        try:
            kroger_source = kroger.extract(name, content)
        except ai.pilot.PilotError as exc:
            raise HTTPException(422, str(exc)) from None
        try:
            if kroger_source:
                if supplements:
                    raise HTTPException(422, "数量和箱数取当前 PO 明细表，不能用共用补齐值覆盖多单数据")
                _, signature = ai.provider_configuration()
                result.update(ai_profile="kroger", kroger_source=kroger_source, provider_signature=signature,
                              ai_consent_version=ai.CONSENT_VERSION)
                return result
            _, template, reference, signature = ai.configuration()
        except (ai.pilot.PilotError, OSError, ValueError, KeyError):
            raise HTTPException(503, "DeepSeek或Zumiez模板素材尚未就绪") from None
        result.update(provider_signature=signature, ai_consent_version=ai.CONSENT_VERSION,
                      layout=dict(config=template, reference_bytes=reference))
        try:
            ai.current_evidence(result)
        except ai.pilot.PilotError as exc:
            if not any(fragment in str(exc) for fragment in ("原稿结构未匹配", "此模板仅支持一个明确")):
                raise HTTPException(422, str(exc)) from None
            from app.services import carton_mark_flexible as flexible
            try:
                result.update(ai_profile="flexible", flexible_source=flexible.read(name, content))
            except ai.pilot.PilotError as problem:
                raise HTTPException(422, str(problem)) from None
    return result


def prepare(original, engine):
    if not _SLOTS.acquire(blocking=False):
        raise HTTPException(429, "正在生成其他文档，请稍后手动重试")
    try:
        if engine == "deepseek_zumiez":
            if original.get("ai_profile") == "flexible":
                from app.services import carton_mark_flexible as flexible
                return flexible.prepare(original)
            if original.get("ai_profile") == "kroger":
                from app.services import carton_mark_kroger as kroger
                return kroger.prepare(original)
            content, pages, warnings, _ = ai.prepare(original)
            return content, pages, warnings + ["未关联订单；合同及内部货号留空，不读取其他订单数据。"]
        # Use the existing isolated Office engine: macros/link updates disabled,
        # unique profile, bounded timeout and process-tree cleanup.
        try:
            extracted = extract_excel_document_items(original["excel_file_name"], original["excel_bytes"])
            if extracted.reviews:
                raise HTTPException(422, "Excel 有公式未保存计算结果，请先重新计算并保存")
            from app.services.document_tools.office_engine import render_office
            with TemporaryDirectory(prefix="carton-draft-", dir=root()) as temporary:
                work = Path(temporary)
                source = work / ("source" + Path(original["excel_file_name"]).suffix.lower())
                source.write_bytes(original["excel_bytes"])
                output = work / "draft.pdf"
                render_office(source, output, {"secure_load": True, "recalculate": False}, work, lambda: False)
                if output.stat().st_size > MAX_DOCUMENT_FILE_BYTES:
                    raise HTTPException(413, "生成 PDF 超过 20 MB，请拆分文件")
                content = output.read_bytes()
                pages = len(PdfReader(io.BytesIO(content)).pages)
                if not 1 <= pages <= 100:
                    raise HTTPException(422, "生成 PDF 超过 100 页，请核实 Excel 打印范围")
                return content, pages, ["按 Excel 原有打印设置导出，请核对分页及完整性；未关联订单，未提交审核。"]
        except (CartonMarkDocumentError, ToolError) as exc:
            raise HTTPException(422, getattr(exc, "message", str(exc))) from None
    finally:
        _SLOTS.release()
