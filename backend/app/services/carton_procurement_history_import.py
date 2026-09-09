from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
import hashlib
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonOrder, CartonCustomer, CartonSupplier
from app.models.carton_master import CartonMasterRecord
from app.services.carton_history_wide import parse_wide
from app.services.carton_master import validate_order as validate_master_order
from app.schemas.carton_procurement import (
    CartonHistoryOrderImportOut,
    CartonOrderCreate,
    CartonOrderLineCreate,
)
from app.services.auth import AuthContext
from app.services.carton_procurement import (
    MAX_IMPORT_BYTES,
    _lock_receipt_factory,
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
    wide = parse_wide(worksheets)
    if wide is not None:
        return wide
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


def _group_rows(rows: list[dict[str, Any]]) -> OrderedDict[tuple[str, ...], list[dict[str, Any]]]:
    groups: OrderedDict[tuple[str, ...], list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        key = (
            ("order", row["order_no"].casefold())
            if row["order_no"]
            else (
                "customer-contract-item",
                " ".join(row["customer_name"].split()).casefold(),
                row["contract_no"].casefold(),
                row["item_no"].casefold(),
            )
        )
        groups.setdefault(key, []).append(row)

    if len(groups) > MAX_HISTORY_ORDER_GROUPS:
        raise HTTPException(
            status_code=422,
            detail=f"单次最多导入 {MAX_HISTORY_ORDER_GROUPS} 张历史订单",
        )

    for group in groups.values():
        first = group[0]
        signatures = set()
        for item in group:
            signature = item["line"].model_dump_json()
            if signature in signatures:
                raise HTTPException(422, detail=f"{item['source']} 存在完全重复的纸品明细，请先核实，不能重复累计需求")
            signatures.add(signature)
        for row in group[1:]:
            inconsistent = [field for field in GROUP_MAIN_FIELDS if row[field] != first[field]]
            if row.get("customer_due_date") != first.get("customer_due_date"):
                inconsistent.append("客户交期")
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


def _check_file(filename: str, content: bytes):
    if Path(filename).suffix.lower() not in HISTORY_ORDER_SUFFIXES:
        raise HTTPException(422, detail="历史订单仅支持 .xlsx、.xlsm 或 .xls 文件")
    if not content:
        raise HTTPException(422, detail="上传的历史订单文件为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(413, detail="历史订单文件不能超过 20MB")


def _fill_master(db: Session, factory: str, group: list[dict]):
    first = group[0]
    if first.get("quantity_basis") != "EXPLICIT":
        return
    records = db.scalars(select(CartonMasterRecord).where(
        CartonMasterRecord.factory_id == factory, CartonMasterRecord.kind == "CONFIG",
        CartonMasterRecord.status == "ACTIVE",
    )).all()
    for row in group:
        line = row["line"]
        missing = [key for key in ("paper_quality", "specification", "dimension_unit") if not getattr(line,key)]
        if not missing:
            continue
        candidates = {}
        for record in records:
            if record.code.strip().casefold() != first["item_no"].strip().casefold():
                continue
            data = json.loads(record.data_json)
            for item in data.get("lines", []):
                if item.get("packaging_type") != line.packaging_type:
                    continue
                if not item.get("paper_quality") or not item.get("specification") or not item.get("unit"):
                    continue
                if any(getattr(line,key) and str(item.get(key, "")) != str(getattr(line,key)) for key in ("paper_quality","specification","dimension_unit","unit")):
                    continue
                if line.usage_quantity is not None:
                    try:
                        if Decimal(str(item.get("usage_quantity"))) != line.usage_quantity:
                            continue
                    except Exception:
                        continue
                signature = json.dumps({key:item.get(key, "") for key in ("paper_quality","specification","dimension_unit","unit","usage_quantity")},sort_keys=True)
                candidates[signature] = (record,item)
        if len(candidates) == 1:
            record,item = next(iter(candidates.values()))
            updates = {key:str(item.get(key, "")) for key in missing}
            row["line"] = line.model_copy(update=updates)
            row.setdefault("row_warnings", []).append(f"{line.packaging_type}的{'、'.join(missing)}由唯一匹配基础资料 {record.id}（版本{record.revision}）带出；未复制价格或推断装箱数")
        elif missing:
            row.setdefault("row_warnings", []).append(f"{line.packaging_type}资料{'存在多个匹配' if candidates else '未完整匹配'}，缺失纸质/规格须补齐后才能确认订单")


def _payload(factory: str, group: list[dict], customer) -> CartonOrderCreate:
    first=group[0]
    try:
        return CartonOrderCreate(factory_id=factory,customer_code=customer.customer_code,
            customer_name=customer.customer_name,contract_no=first["contract_no"],item_no=first["item_no"],
            product_name=first["product_name"],quantity_basis=first.get("quantity_basis","CALCULATED"),
            product_order_quantity=first["product_order_quantity"],order_date=first["order_date"],
            due_date=first["due_date"],customer_due_date=first.get("customer_due_date"),
            status="CONFIRMED",note=first["note"],lines=[row["line"] for row in group])
    except ValidationError as exc:
        raise HTTPException(422, detail=f"{first['source']} 所在订单校验失败：{_validation_message(exc)}") from exc


def _preview(db: Session, factory: str, filename: str, content: bytes):
    """The fingerprint freezes both the uploaded file and mutable lookup/duplicate evidence."""
    masters=db.scalars(select(CartonMasterRecord).where(CartonMasterRecord.factory_id==factory)).all()
    customers=db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id==factory)).all()
    existing=db.scalars(select(CartonOrder).where(CartonOrder.factory_id==factory)).all()
    suppliers=db.scalars(select(CartonSupplier).where(CartonSupplier.factory_id==factory)).all()
    evidence={"factory":factory,"file":hashlib.sha256(content).hexdigest(),"parser":3,
        "masters":sorted((r.id,r.kind,r.code,r.revision,r.status,r.data_json) for r in masters),
        "customers":sorted((r.customer_code,r.customer_name,r.status) for r in customers),
        "suppliers":sorted((r.id,r.supplier_code,r.supplier_name,r.status) for r in suppliers),
        "orders":sorted((r.id,r.order_no,r.customer_code,r.contract_no,r.item_no,r.revision) for r in existing)}
    fingerprint=hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    result={"factory_id":factory,"original_filename":filename,"source_fingerprint":fingerprint,
        "row_count":0,"group_count":0,"line_count":0,"ready_count":0,"draft_count":0,"incomplete_count":0,
        "skipped_count":0,"warnings":[],"errors":[],"orders":[]}
    active_suppliers=[supplier for supplier in suppliers if supplier.status=="ACTIVE"]
    if len(active_suppliers)!=1:
        result["errors"].append("当前厂区必须配置唯一有效纸箱供应商，才能预览并确认历史订单")
        return result,[]
    supplier=active_suppliers[0]
    result.update(supplier_id=supplier.id,supplier_name=supplier.supplier_name)
    try:
        rows,warnings=_parse_rows(filename,content)
        groups=_group_rows(rows)
    except HTTPException as exc:
        result["errors"].append(str(exc.detail))
        return result,[]
    result.update(row_count=len({r["source"] for r in rows}),group_count=len(groups),line_count=len(rows),warnings=warnings)
    order_nos={o.order_no.casefold() for o in existing}
    identities={(o.customer_code,o.contract_no.casefold(),o.item_no.casefold()) for o in existing}
    prepared=[]
    for group in groups.values():
        first=group[0]
        try:
            customer=get_active_customer_by_name(db,factory,first["customer_name"])
            identity=(customer.customer_code,first["contract_no"].casefold(),first["item_no"].casefold())
            # New explicit IDs identify independent batches; legacy retry behavior is unchanged.
            explicit_batch=first.get("quantity_basis")=="EXPLICIT" and bool(first["order_no"])
            duplicate=(first["order_no"].casefold() in order_nos if explicit_batch else
                bool(first["order_no"] and first["order_no"].casefold() in order_nos) or identity in identities)
            if not duplicate:
                validate_master_order(db,factory,customer.customer_code,first["contract_no"],first["item_no"])
            _fill_master(db,factory,group)
            payload=_payload(factory,group,customer)
            payload.supplier_id=supplier.id
        except HTTPException as exc:
            result["errors"].append(f"{first['source']}：{exc.detail}")
            continue
        missing=any(not line.paper_quality or not line.specification for line in payload.lines)
        messages=list(dict.fromkeys(message for row in group for message in row.get("row_warnings",[])))
        if missing: messages.append("导入为待下单；缺失的纸质、规格须补齐后才能确认锁定")
        if duplicate:
            result["skipped_count"]+=1
            messages.append("已存在，将跳过避免重复建单")
        else:
            result["incomplete_count" if missing else "ready_count"]+=1
        view=payload.model_dump(mode="json")
        view.update(order_no=first["order_no"],source_rows=list(dict.fromkeys(r["source"] for r in group)),
            duplicate=duplicate,ready=not missing,warnings=messages)
        result["orders"].append(view)
        prepared.append((group,payload,duplicate))
        order_nos.add(first["order_no"].casefold()) if first["order_no"] else None
        identities.add(identity)
    result["draft_count"]=result["incomplete_count"]
    return result,prepared


def preview_history_orders(db: Session, factory_id: str, filename: str, content: bytes) -> dict:
    factory_id=require_carton_factory(factory_id)
    filename=Path(filename or "").name
    _check_file(filename,content)
    return _preview(db,factory_id,filename,content)[0]


def import_history_orders(
    db: Session,
    factory_id: str,
    filename: str,
    content: bytes,
    user: AuthContext,
    expected_preview_fingerprint: str | None = None,
) -> CartonHistoryOrderImportOut:
    factory_id = require_carton_factory(factory_id)
    filename = Path(filename or "").name
    _check_file(filename, content)

    imported_orders: list[str] = []
    skipped_orders: list[str] = []
    imported_line_count = 0

    try:
        # Read duplicate candidates only after serializing against other order writers.
        _lock_receipt_factory(db, factory_id)
        preview, prepared = _preview(db,factory_id,filename,content)
        if expected_preview_fingerprint and expected_preview_fingerprint != preview["source_fingerprint"]:
            raise HTTPException(409, detail="文件、客户、基础资料或现有订单已变化，请重新预览后确认导入")
        if preview["errors"]:
            raise HTTPException(422, detail="；".join(preview["errors"]))
        if any(payload.quantity_basis == "EXPLICIT" for _,payload,_ in prepared) and not expected_preview_fingerprint:
            raise HTTPException(409, detail="新版历史订单请先预览核对，再确认导入")
        warnings = list(preview["warnings"])
        for item in preview["orders"]:
            warnings.extend(f"{item['contract_no']} / {item['item_no']}：{message}" for message in item["warnings"] if "已存在" not in message)
        for group, payload, duplicate in prepared:
            first = group[0]
            order_no = first["order_no"]
            if duplicate:
                label = order_no or f"{first['contract_no']} / {first['item_no']}"
                skipped_orders.append(label)
                warnings.append(f"{label} 已存在，已跳过以避免重复建单")
                continue

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
        row_count=preview["row_count"],
        group_count=preview["group_count"],
        imported_count=len(imported_orders),
        imported_line_count=imported_line_count,
        skipped_count=len(skipped_orders),
        imported_orders=imported_orders,
        skipped_orders=skipped_orders,
        warnings=warnings,
    )
