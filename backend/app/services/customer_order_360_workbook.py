"""Organize an existing 360 unified workbook without needing a new PO."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from app.services import customer_order_unified as unified
from app.services.huakang_a_order_legacy import unified_schedule as huakang
from app.services.customer_order_360_order_types import ensure_360_order_type_dropdowns, OrderTypeValidationError


def organize_workbook(file_name: str, content: bytes):
    source_hash = sha256(content).hexdigest()
    if not content.startswith(b"PK"):
        from app.services.customer_order_buzzbee import _decrypt_schedule
        content, _ = _decrypt_schedule(content)
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 200 * 1024 * 1024:
                raise unified.CustomerOrderUnifiedError("排期解压后过大，请拆分后整理")
    except BadZipFile as exc:
        raise unified.CustomerOrderUnifiedError("请选择可打开的 .xlsx 排期") from exc
    unified.ensure_unified_schedule(file_name, content, factory_id="huakang-a", customer_code="360")
    workbook = unified._load_workbook(content)
    try:
        report = huakang.organize_360_schedule(workbook, source_content=content)
        from app.services.customer_order_360_shipping_item import backfill_shipping_items, ShippingItemError
        try:
            report['shipping_items'] = backfill_shipping_items(workbook)
            report.setdefault('warnings', []).extend(report['shipping_items'].get('warnings', []))
        except ShippingItemError as exc:
            raise unified.CustomerOrderUnifiedError(str(exc)) from exc
        try:
            report["order_type_dropdowns"] = ensure_360_order_type_dropdowns(
                workbook, factory_id="huakang-a", customer_code="360")
        except OrderTypeValidationError as exc:
            raise unified.CustomerOrderUnifiedError(str(exc)) from exc
        workbook.calculation.calcMode = "auto"
        workbook.calculation.fullCalcOnLoad = True
        workbook.calculation.forceFullCalc = True
        stream = BytesIO()
        workbook.save(stream)
    finally:
        workbook.close()
    stem = re.sub(r'[\\/:*?"<>|]+', '_', Path(file_name).stem).strip(' ._')[:150] or "360排期"
    output_name = f"{stem}_按验货日期整理.xlsx"
    return stream.getvalue(), output_name, report, source_hash
