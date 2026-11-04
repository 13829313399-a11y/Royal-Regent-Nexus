"""Row-owned price annotations and protected evidence images; no schema migration."""
import base64
import hashlib
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select

from app.models.internal_quote import InternalQuoteAttachment
from app.services.auth import now_text


def validate_note_images(db, quote, department, payload):
    if isinstance(payload, list):
        for child in payload:
            validate_note_images(db, quote, department, child)
    elif isinstance(payload, dict):
        notes = payload.get("price_annotations", {})
        if not isinstance(notes, dict) or len(notes) > 30:
            raise HTTPException(400, "调价批注格式无效")
        for note in notes.values():
            if not isinstance(note, dict) or not isinstance(note.get("text", ""), str) or len(note.get("text", "")) > 3000:
                raise HTTPException(400, "调价批注不能超过 3000 字")
            ids = note.get("image_attachment_ids", [])
            if not isinstance(ids, list) or len(ids) > 4 or any(not isinstance(i, str) for i in ids):
                raise HTTPException(400, "每条调价批注最多保留 4 张截图")
            for image_id in ids:
                attachment = db.scalar(select(InternalQuoteAttachment).where(
                    InternalQuoteAttachment.id == image_id, InternalQuoteAttachment.quote_id == quote.id,
                    InternalQuoteAttachment.department == department))
                if attachment is None or not attachment.content_type.startswith("image/"):
                    raise HTTPException(400, "调价截图必须属于本报价的同一部门")
        for key, child in payload.items():
            if key != "price_annotations":
                validate_note_images(db, quote, department, child)


def make_annotation(db, quote, code, field, annotation, user, persist=False):
    ids = list(dict.fromkeys(annotation.image_attachment_ids))
    validate_note_images(db, quote, code, {"price_annotations": {"note": {"text": annotation.text, "image_attachment_ids": ids}}})
    if len(ids) + len(annotation.new_images) > 4:
        raise HTTPException(400, "每条调价批注最多保留 4 张截图")
    for encoded in annotation.new_images:
        try:
            content = base64.b64decode(encoded, validate=True)
            if len(content) > 3 * 1024 * 1024:
                raise ValueError()
            with Image.open(BytesIO(content)) as source:
                if source.width * source.height > 16_000_000:
                    raise ValueError()
                source.load()
                buffer = BytesIO()
                source.convert("RGB").save(buffer, format="PNG")
                content = buffer.getvalue()
        except Exception as error:
            raise HTTPException(400, "截图必须为有效图片，每张不超过 3 MB、1600 万像素") from error
        if persist:
            digest = hashlib.sha256(content).hexdigest()
            attachment = db.scalar(select(InternalQuoteAttachment).where(
                InternalQuoteAttachment.quote_id == quote.id, InternalQuoteAttachment.department == code,
                InternalQuoteAttachment.sha256 == digest))
            if attachment is None:
                attachment = InternalQuoteAttachment(id=f"IQATT-{uuid4().hex}", quote_id=quote.id, factory_id=quote.factory_id,
                    department=code, file_name=f"调价截图-{uuid4().hex[:8]}.png", content_type="image/png",
                    size_bytes=len(content), sha256=digest, content=content, uploaded_by=user.id,
                    uploaded_by_name=user.display_name, uploaded_at=now_text())
                db.add(attachment)
                db.flush()
            ids.append(attachment.id)
    return {"text": annotation.text.strip(), "image_attachment_ids": list(dict.fromkeys(ids)),
            "author": user.display_name, "updated_at": now_text(), "price_at_note": str(field.get("value", ""))}


def append_price_notes(workbook, sections, attachments, region_code="", snapshot=None):
    from openpyxl.comments import Comment
    from openpyxl.drawing.image import Image as ExcelImage
    from openpyxl.styles import Font, PatternFill, Alignment
    from app.services.internal_quote_output_fields import source_groups, _bind_aggregate_cells
    groups = source_groups(sections, region_code, snapshot)
    annotated = [(g, f) for g in groups for f in g["fields"] if f.get("annotation")]
    if not annotated:
        return
    _bind_aggregate_cells(workbook, groups)
    sheet = workbook.create_sheet("调价说明")
    headers = ["对应项目", "部门", "单价字段 / 币种", "当前单价", "批注时单价", "批注", "记录人 / 时间", "对应单元格"]
    sheet.append(headers)
    sheet.freeze_panes = "A2"
    widths = [24, 14, 24, 16, 16, 56, 30, 36]
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = width
        cell = sheet.cell(1, column); cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="23796A")
    by_id = {a.id: a for a in attachments or []}
    index = 2
    for group, field in annotated:
        note = field["annotation"]
        targets = []
        direct = any(binding.get("kind") == "price" and binding.get("group") == group["id"]
                     for target in workbook if target.sheet_state == "visible"
                     for binding in getattr(target, "_quote_bindings", {}).values())
        body = f"{group['label']} · {field['label']} {field['currency']}\n{note.get('text', '')}\n{note.get('author', '')} {note.get('updated_at', '')}\n截图及明细见“调价说明”第 {index} 行"
        adjustment = field.get("adjustment")
        calculation_note = ""
        if adjustment:
            from decimal import Decimal
            original = Decimal(adjustment["original_per_piece_hkd"])
            adopted = Decimal(adjustment["effective_per_piece_hkd"])
            unit = "HKD/箱（含该平卡用量）" if adjustment["mode"] == "per_carton" and "flat_cards" in field["id"] else "HKD/箱" if adjustment["mode"] == "per_carton" else "HKD/件"
            calculation_note = (f"原核算 {original:.4f} HKD/件；采用 {adopted:.4f} HKD/件；差额 {adopted-original:+.4f} HKD/件。"
                                f"输入 {adjustment['amount_hkd']} {unit}，均为倍率前成本。")
            body += "\n" + calculation_note
        for target in workbook:
            if target.title == "调价说明" or target.sheet_state != "visible":
                continue
            for address, binding in getattr(target, "_quote_bindings", {}).items():
                if direct and binding.get("kind") != "price":
                    continue
                if binding.get("kind") in {"price", "source"} and (binding.get("group") == group["id"] or group["id"] in binding.get("groups", [])):
                    cell = target[address]
                    if cell.__class__.__name__ == "MergedCell":
                        continue
                    targets.append(f"{target.title}!{address}")
                    text = f"{cell.comment.text}\n\n{body}" if cell.comment else body
                    cell.comment = Comment(text, str(note.get("author") or "内部报价"))
        values = [group["label"], group["section_name"], f"{field['label']} {field['currency']}", str(field.get("value", "")),
                  note.get("price_at_note", ""), note.get("text", "") + ("\n" + calculation_note if calculation_note else ""), f"{note.get('author', '')} {note.get('updated_at', '')}", "、".join(targets) or "报价明细（部门汇总）"]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(index, column, str(value)); cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[index].height = 70
        index += 1
        for image_id in note.get("image_attachment_ids", []):
            attachment = by_id.get(image_id)
            if attachment is None or attachment.department != group["section"]:
                continue
            try:
                picture = ExcelImage(BytesIO(attachment.content))
                ratio = min(680 / picture.width, 360 / picture.height, 1)
                picture.width *= ratio; picture.height *= ratio
                sheet.cell(index, 1, f"{group['label']} · {field['label']} · 调价截图").data_type = "s"
                sheet.add_image(picture, f"C{index}")
                sheet.row_dimensions[index].height = max(50, picture.height * .75 + 16)
                index += 1
            except Exception:
                sheet.cell(index, 1, "截图无法读取，请核对原附件")
                index += 1
    sheet.sheet_state = "visible"
