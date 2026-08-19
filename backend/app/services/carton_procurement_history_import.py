from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonOrder
from app.schemas.carton_procurement import (
    CartonHistoryOrderImportOut,
    CartonOrderCreate,
    CartonOrderLineCreate,
)
from app.services.auth import AuthContext
from app.services.carton_procurement import (
    MAX_IMPORT_BYTES,
    create_order,
    get_active_customer_by_name,
    require_carton_factory,
)
from app.services.carton_procurement_imports import (
    _cell,
    _date_text,
    _header_mapping,
    _number,
    _sheet_rows,
    _text,
)


HISTORY_ORDER_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
MAX_HISTORY_ORDER_GROUPS = 1_000

HISTORY_ORDER_ALIASES = {
    "order_no": {
        "历史订单号",
        "历史订单号选填",
        "历史订单编号",
        "原订单号",
        "订单号",
        "historyorderno",
    },
    "contract_no": {"合同号", "合同编号", "contractno"},
    "customer_name": {"客户名称", "客名", "customername"},
    "item_no": {"货号", "产品编号", "客货号", "itemno"},
    "product_name": {"产品名称", "品名", "productname"},
    "product_order_quantity": {
        "产品订单数量",
        "订单数量",
        "产品数量",
        "productorderquantity",
    },
    "order_date": {"下单日期", "订单日期", "orderdate"},
    "due_date": {"计划交期", "交货日期", "交期", "duedate"},
    "order_note": {"订单备注", "合同备注", "ordernote"},
    "packaging_type": {"纸品类型", "纸箱类型", "类型", "packagingtype"},
    "paper_quality": {"纸质", "材质", "paperquality"},
    "specification": {"规格", "尺寸", "specification"},
    "dimension_unit": {"规格单位", "尺寸单位", "dimensionunit"},
    "usage_quantity": {
        "每箱个数",
        "每箱数量",
        "装箱数量",
        "unitspercarton",
        "单件用量",
        "用量",
        "usagequantity",
    },
    "unit": {"纸品单位", "单位", "unit"},
    "unit_price": {"单价", "unitprice"},
    "currency": {"币种", "currency"},
    "price_source": {"价格来源", "pricesource"},
    "line_note": {"明细备注", "纸品备注", "linenote"},
}

REQUIRED_HEADERS = {
    "contract_no",
    "customer_name",
    "item_no",
    "product_order_quantity",
    "order_date",
    "due_date",
    "packaging_type",
    "paper_quality",
    "specification",
    "usage_quantity",
    "unit",
}

GROUP_MAIN_FIELDS = (
    "contract_no",
    "customer_name",
    "item_no",
    "product_order_quantity",
    "order_date",
    "due_date",
)


def _validation_message(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors()[:6]:
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = str(error.get("msg", "字段不合法"))
        messages.append(f"{location}: {message}" if location else message)
    return "；".join(messages)


def _required_text(
    row: list[Any],
    mapping: dict[str, int],
    field: str,
    label: str,
    source: str,
    errors: list[str],
) -> str:
    value = _text(_cell(row, mapping, field))
    if not value:
        errors.append(f"{source} 的“{label}”不能为空")
    return value


def _legacy_usage_header(
    rows: list[list[Any]],
    header_index: int,
    mapping: dict[str, int],
) -> bool:
    label = _text(_cell(rows[header_index], mapping, "usage_quantity"))
    normalized = "".join(character for character in label.casefold() if character.isalnum())
    return "单件用量" in label or normalized in {"用量", "usagequantity"}


def _convert_legacy_usage_to_units_per_carton(value: Decimal) -> Decimal:
    converted = Decimal(1) / value
    nearest_integer = converted.to_integral_value(rounding=ROUND_HALF_UP)
    if abs(converted - nearest_integer) <= Decimal("0.0001"):
        converted = nearest_integer
    return converted.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def _parse_rows(filename: str, content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    worksheets = _sheet_rows(filename, content)
    worksheets.sort(key=lambda item: 0 if item[0].strip() == "历史订单导入" else 1)
    warnings: list[str] = []
    parsed: list[dict[str, Any]] = []
    found_header = False

    for sheet_name, rows, datemode in worksheets:
        if sheet_name.strip() in {"填写示例", "字段说明"}:
            continue
        header = _header_mapping(rows, HISTORY_ORDER_ALIASES)
        if header is None or not REQUIRED_HEADERS.issubset(header[1]):
            if any(any(_text(cell) for cell in row) for row in rows[:20]):
                warnings.append(f"工作表“{sheet_name}”未找到完整的历史订单映射表头，已跳过")
            continue
        found_header = True
        header_index, mapping = header
        legacy_usage = _legacy_usage_header(rows, header_index, mapping)
        if legacy_usage:
            warnings.append(
                f"工作表“{sheet_name}”使用旧版“单件用量”列，系统已自动换算为“每箱个数”"
            )
        for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            if not any(_text(_cell(row, mapping, field)) for field in HISTORY_ORDER_ALIASES):
                continue

            source = f"“{sheet_name}”第 {row_number} 行"
            errors: list[str] = []
            order_no = _text(_cell(row, mapping, "order_no"))
            if len(order_no) > 64:
                errors.append(f"{source} 的“历史订单号”不能超过 64 个字符")

            contract_no = _required_text(row, mapping, "contract_no", "合同号", source, errors)
            customer_name = _required_text(
                row, mapping, "customer_name", "客户名称", source, errors
            )
            item_no = _required_text(row, mapping, "item_no", "货号", source, errors)
            packaging_type = _required_text(
                row, mapping, "packaging_type", "纸品类型", source, errors
            )
            paper_quality = _required_text(row, mapping, "paper_quality", "纸质", source, errors)
            specification = _required_text(
                row, mapping, "specification", "规格", source, errors
            )
            unit = _required_text(row, mapping, "unit", "纸品单位", source, errors)

            product_quantity = _number(_cell(row, mapping, "product_order_quantity"))
            if product_quantity is None or product_quantity <= 0:
                errors.append(f"{source} 的“产品订单数量”必须是大于 0 的数字")
            elif product_quantity.as_tuple().exponent < -6:
                product_quantity = product_quantity.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            usage_quantity = _number(_cell(row, mapping, "usage_quantity"))
            if usage_quantity is None or usage_quantity <= 0:
                label = "单件用量" if legacy_usage else "每箱个数"
                errors.append(f"{source} 的“{label}”必须是大于 0 的数字")
            elif legacy_usage:
                usage_quantity = _convert_legacy_usage_to_units_per_carton(usage_quantity)
            elif usage_quantity.as_tuple().exponent < -8:
                usage_quantity = usage_quantity.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            unit_price = _number(_cell(row, mapping, "unit_price"))
            if unit_price is not None and unit_price < 0:
                errors.append(f"{source} 的“单价”不能小于 0")
            elif unit_price is not None and unit_price.as_tuple().exponent < -6:
                unit_price = unit_price.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

            order_date = _date_text(_cell(row, mapping, "order_date"), datemode)
            due_date = _date_text(_cell(row, mapping, "due_date"), datemode)
            if not order_date:
                errors.append(f"{source} 的“下单日期”无法识别")
            if not due_date:
                errors.append(f"{source} 的“计划交期”无法识别")
            if order_date and due_date and due_date < order_date:
                errors.append(f"{source} 的“计划交期”不能早于“下单日期”")

            if errors:
                raise HTTPException(status_code=422, detail="；".join(errors))

            try:
                line = CartonOrderLineCreate(
                    packaging_type=packaging_type,
                    paper_quality=paper_quality,
                    specification=specification,
                    dimension_unit=_text(_cell(row, mapping, "dimension_unit")),
                    usage_quantity=usage_quantity,
                    unit=unit,
                    unit_price=unit_price or Decimal(0),
                    currency=(_text(_cell(row, mapping, "currency")) or "CNY").upper(),
                    price_source=_text(_cell(row, mapping, "price_source")) or "历史导入",
                    note=_text(_cell(row, mapping, "line_note")),
                )
            except ValidationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{source} 校验失败：{_validation_message(exc)}",
                ) from exc

            parsed.append(
                {
                    "source": source,
                    "order_no": order_no,
                    "contract_no": contract_no,
                    "customer_name": customer_name,
                    "item_no": item_no,
                    "product_name": _text(_cell(row, mapping, "product_name")),
                    "product_order_quantity": product_quantity,
                    "order_date": order_date,
                    "due_date": due_date,
                    "note": _text(_cell(row, mapping, "order_note")),
                    "line": line,
                }
            )

    if not found_header:
        raise HTTPException(
            status_code=422,
            detail="未找到历史订单导入表头，请先下载系统模板并按模板填写",
        )
    if not parsed:
        raise HTTPException(status_code=422, detail="历史订单导入表中没有可导入的数据行")
    return parsed, warnings


def _group_rows(rows: list[dict[str, Any]]) -> OrderedDict[str, list[dict[str, Any]]]:
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        key = (
            f"order:{row['order_no'].casefold()}"
            if row["order_no"]
            else f"contract-item:{row['contract_no'].casefold()}|{row['item_no'].casefold()}"
        )
        groups.setdefault(key, []).append(row)

    if len(groups) > MAX_HISTORY_ORDER_GROUPS:
        raise HTTPException(
            status_code=422,
            detail=f"单次最多导入 {MAX_HISTORY_ORDER_GROUPS} 张历史订单",
        )

    for group in groups.values():
        first = group[0]
        for row in group[1:]:
            inconsistent = [field for field in GROUP_MAIN_FIELDS if row[field] != first[field]]
            for field in ("product_name", "note"):
                if row[field] and first[field] and row[field] != first[field]:
                    inconsistent.append(field)
                elif row[field] and not first[field]:
                    first[field] = row[field]
            if inconsistent:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{row['source']} 与同组首行的订单主信息不一致："
                        + "、".join(inconsistent)
                    ),
                )
        if len(group) > 50:
            raise HTTPException(
                status_code=422,
                detail=f"{first['source']} 所在订单包含 {len(group)} 行纸品，超过单张订单 50 行上限",
            )
    return groups


def import_history_orders(
    db: Session,
    factory_id: str,
    filename: str,
    content: bytes,
    user: AuthContext,
) -> CartonHistoryOrderImportOut:
    factory_id = require_carton_factory(factory_id)
    filename = Path(filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in HISTORY_ORDER_SUFFIXES:
        raise HTTPException(status_code=422, detail="历史订单仅支持 .xlsx、.xlsm 或 .xls 文件")
    if not content:
        raise HTTPException(status_code=422, detail="上传的历史订单文件为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="历史订单文件不能超过 20MB")

    rows, warnings = _parse_rows(filename, content)
    groups = _group_rows(rows)
    existing = db.execute(
        select(CartonOrder.order_no, CartonOrder.contract_no, CartonOrder.item_no).where(
            CartonOrder.factory_id == factory_id
        )
    ).all()
    existing_order_nos = {str(item.order_no).casefold() for item in existing}
    existing_contract_items = {
        (str(item.contract_no).casefold(), str(item.item_no).casefold()) for item in existing
    }

    imported_orders: list[str] = []
    skipped_orders: list[str] = []
    imported_line_count = 0
    staged_contract_items = set(existing_contract_items)

    try:
        for group in groups.values():
            first = group[0]
            order_no = first["order_no"]
            contract_item = (
                first["contract_no"].casefold(),
                first["item_no"].casefold(),
            )
            duplicate = (
                bool(order_no and order_no.casefold() in existing_order_nos)
                or contract_item in staged_contract_items
            )
            if duplicate:
                label = order_no or f"{first['contract_no']} / {first['item_no']}"
                skipped_orders.append(label)
                warnings.append(f"{label} 已存在，已跳过以避免重复建单")
                continue

            try:
                customer = get_active_customer_by_name(
                    db, factory_id, first["customer_name"]
                )
                payload = CartonOrderCreate(
                    factory_id=factory_id,
                    customer_code=customer.customer_code,
                    customer_name=customer.customer_name,
                    contract_no=first["contract_no"],
                    item_no=first["item_no"],
                    product_name=first["product_name"],
                    product_order_quantity=first["product_order_quantity"],
                    order_date=first["order_date"],
                    due_date=first["due_date"],
                    status="CONFIRMED",
                    note=first["note"],
                    lines=[item["line"] for item in group],
                )
            except ValidationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{first['source']} 所在订单校验失败：{_validation_message(exc)}",
                ) from exc

            order = create_order(
                db,
                payload,
                user,
                order_no=order_no or None,
                commit=False,
                audit_event="HISTORY_ORDER_IMPORTED",
            )
            imported_orders.append(order.order_no)
            imported_line_count += len(group)
            staged_contract_items.add(contract_item)
            existing_order_nos.add(order.order_no.casefold())
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="历史订单与现有订单发生编号冲突") from exc
    except Exception:
        db.rollback()
        raise

    return CartonHistoryOrderImportOut(
        factory_id=factory_id,
        original_filename=filename,
        row_count=len(rows),
        group_count=len(groups),
        imported_count=len(imported_orders),
        imported_line_count=imported_line_count,
        skipped_count=len(skipped_orders),
        imported_orders=imported_orders,
        skipped_orders=skipped_orders,
        warnings=warnings,
    )
