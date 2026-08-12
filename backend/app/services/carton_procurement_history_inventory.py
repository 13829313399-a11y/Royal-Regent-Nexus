from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.carton_procurement import (
    CartonInventoryMovement,
    CartonOrder,
    CartonOrderLine,
)
from app.schemas.carton_procurement import CartonHistoryInventoryImportOut
from app.services.auth import AuthContext
from app.services.carton_procurement import (
    MAX_IMPORT_BYTES,
    _audit,
    _ensure_period_open,
    get_active_customer_by_name,
    normalize_currency,
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


HISTORY_INVENTORY_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
MAX_HISTORY_INVENTORY_ROWS = 5_000
QUANTITY_QUANTUM = Decimal("0.0001")
PRICE_QUANTUM = Decimal("0.000001")

HISTORY_INVENTORY_ALIASES = {
    "legacy_row_no": {"历史库存行号", "历史库存行号选填", "原库存行号", "legacyrowno"},
    "customer_name": {"客户名称", "客名", "customername"},
    "order_no": {"纸箱订单号", "纸箱订单号选填", "订单号", "orderno"},
    "contract_no": {"合同号po", "合同号", "po", "contractno"},
    "item_no": {"货号", "产品编号", "客货号", "itemno"},
    "packaging_type": {"纸品类型", "纸箱类型", "类型", "packagingtype"},
    "paper_quality": {"纸质", "材质", "paperquality"},
    "specification": {"规格", "尺寸", "specification"},
    "unit": {"单位", "纸品单位", "unit"},
    "opening_quantity": {"期初库存数量", "历史库存数量", "库存数量", "数量", "openingquantity"},
    "unit_price": {"单价", "unitprice"},
    "currency": {"币种", "currency"},
    "location": {"仓位", "库位", "location"},
    "snapshot_date": {"盘点日期", "库存日期", "日期", "snapshotdate"},
    "document_no": {"来源单号", "盘点单号", "单据号", "documentno"},
    "note": {"备注", "说明", "note"},
}

REQUIRED_HEADERS = {
    "customer_name",
    "item_no",
    "packaging_type",
    "paper_quality",
    "specification",
    "unit",
    "opening_quantity",
    "snapshot_date",
}


def _normalized(value: Any) -> str:
    return "".join(_text(value).casefold().split())


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


def _parse_rows(filename: str, content: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    worksheets = _sheet_rows(filename, content)
    worksheets.sort(key=lambda item: 0 if item[0].strip() == "历史库存导入" else 1)
    parsed: list[dict[str, Any]] = []
    warnings: list[str] = []
    found_header = False

    for sheet_name, rows, datemode in worksheets:
        if sheet_name.strip() in {"填写示例", "字段说明"}:
            continue
        header = _header_mapping(rows, HISTORY_INVENTORY_ALIASES)
        if header is None or not REQUIRED_HEADERS.issubset(header[1]):
            if any(any(_text(cell) for cell in row) for row in rows[:20]):
                warnings.append(f"工作表“{sheet_name}”未找到完整的历史库存映射表头，已跳过")
            continue
        found_header = True
        header_index, mapping = header
        for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            if not any(_text(_cell(row, mapping, field)) for field in HISTORY_INVENTORY_ALIASES):
                continue
            source = f"“{sheet_name}”第 {row_number} 行"
            errors: list[str] = []
            customer_name = _required_text(row, mapping, "customer_name", "客户名称", source, errors)
            item_no = _required_text(row, mapping, "item_no", "货号", source, errors)
            packaging_type = _required_text(row, mapping, "packaging_type", "纸品类型", source, errors)
            paper_quality = _required_text(row, mapping, "paper_quality", "纸质", source, errors)
            specification = _required_text(row, mapping, "specification", "规格", source, errors)
            unit = _required_text(row, mapping, "unit", "单位", source, errors)
            opening_quantity = _number(_cell(row, mapping, "opening_quantity"))
            if opening_quantity is None or opening_quantity <= 0:
                errors.append(f"{source} 的“期初库存数量”必须大于 0")
            unit_price = _number(_cell(row, mapping, "unit_price"))
            if unit_price is None:
                unit_price = Decimal(0)
            elif unit_price < 0:
                errors.append(f"{source} 的“单价”不能小于 0")
            snapshot_date = _date_text(_cell(row, mapping, "snapshot_date"), datemode)
            if not snapshot_date:
                errors.append(f"{source} 的“盘点日期”不是有效日期")
            if errors:
                raise HTTPException(status_code=422, detail="；".join(errors))

            parsed.append(
                {
                    "source": source,
                    "source_sheet": sheet_name,
                    "source_row": row_number,
                    "legacy_row_no": _text(_cell(row, mapping, "legacy_row_no")),
                    "customer_name": customer_name,
                    "order_no": _text(_cell(row, mapping, "order_no")),
                    "contract_no": _text(_cell(row, mapping, "contract_no")),
                    "item_no": item_no,
                    "packaging_type": packaging_type,
                    "paper_quality": paper_quality,
                    "specification": specification,
                    "unit": unit,
                    "opening_quantity": opening_quantity.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP),
                    "unit_price": unit_price.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP),
                    "currency": normalize_currency(_text(_cell(row, mapping, "currency")) or "CNY"),
                    "location": _text(_cell(row, mapping, "location")),
                    "snapshot_date": snapshot_date,
                    "document_no": _text(_cell(row, mapping, "document_no")),
                    "note": _text(_cell(row, mapping, "note")),
                }
            )
            if len(parsed) > MAX_HISTORY_INVENTORY_ROWS:
                raise HTTPException(
                    status_code=422,
                    detail=f"单次最多导入 {MAX_HISTORY_INVENTORY_ROWS} 行历史库存",
                )

    if not found_header:
        raise HTTPException(
            status_code=422,
            detail="未找到历史库存导入表头，请先下载系统模板并按模板填写",
        )
    if not parsed:
        raise HTTPException(status_code=422, detail="历史库存导入表中没有可导入的数据行")
    return parsed, warnings


def _source_line_id(factory_id: str, row: dict[str, Any]) -> str:
    if row["legacy_row_no"]:
        identity = "|".join(
            (factory_id, row["source_sheet"], _normalized(row["legacy_row_no"]))
        )
    else:
        identity = "|".join(
            _normalized(row[field])
            for field in (
                "customer_code",
                "contract_no",
                "item_no",
                "packaging_type",
                "paper_quality",
                "specification",
                "unit",
                "location",
                "snapshot_date",
                "document_no",
            )
        )
    return f"CHI-LINE-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:48]}"


def _match_order_line(
    db: Session,
    factory_id: str,
    row: dict[str, Any],
) -> tuple[CartonOrderLine | None, CartonOrder | None]:
    statement = (
        select(CartonOrderLine, CartonOrder)
        .join(CartonOrder, CartonOrder.id == CartonOrderLine.order_id)
        .where(
            CartonOrderLine.factory_id == factory_id,
            CartonOrderLine.customer_code == row["customer_code"],
            CartonOrderLine.item_no == row["item_no"],
        )
    )
    if row["order_no"]:
        statement = statement.where(CartonOrder.order_no == row["order_no"])
    elif row["contract_no"]:
        statement = statement.where(CartonOrderLine.contract_no == row["contract_no"])

    exact: list[tuple[CartonOrderLine, CartonOrder]] = []
    for line, order in db.execute(statement).all():
        if all(
            _normalized(getattr(line, field)) == _normalized(row[field])
            for field in ("packaging_type", "paper_quality", "specification", "unit")
        ):
            exact.append((line, order))
    return exact[0] if len(exact) == 1 else (None, None)


def import_history_inventory(
    db: Session,
    factory_id: str,
    filename: str,
    content: bytes,
    user: AuthContext,
) -> CartonHistoryInventoryImportOut:
    factory_id = require_carton_factory(factory_id)
    filename = Path(filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in HISTORY_INVENTORY_SUFFIXES:
        raise HTTPException(status_code=422, detail="历史库存仅支持 .xlsx、.xlsm 或 .xls 文件")
    if not content:
        raise HTTPException(status_code=422, detail="上传的历史库存文件为空")
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="历史库存文件不能超过 20MB")

    rows, warnings = _parse_rows(filename, content)
    source_hash = hashlib.sha256(content).hexdigest()
    source_id = f"CHI-{source_hash[:32]}"
    existing_file_rows = list(
        db.scalars(
            select(CartonInventoryMovement).where(
                CartonInventoryMovement.factory_id == factory_id,
                CartonInventoryMovement.source_type == "HISTORY_INVENTORY",
                CartonInventoryMovement.source_id == source_id,
            )
        ).all()
    )
    if existing_file_rows:
        return CartonHistoryInventoryImportOut(
            factory_id=factory_id,
            original_filename=filename,
            row_count=len(rows),
            imported_count=0,
            skipped_count=len(rows),
            matched_order_line_count=sum(1 for item in existing_file_rows if item.order_line_id),
            standalone_count=sum(1 for item in existing_file_rows if not item.order_line_id),
            total_quantity=sum((item.quantity for item in existing_file_rows), Decimal(0)),
            duplicate=True,
            movement_ids=[item.id for item in existing_file_rows],
            warnings=["该文件已导入，系统已跳过以避免期初库存重复累计"],
        )

    customer_cache: dict[str, Any] = {}
    for row in rows:
        customer_key = _normalized(row["customer_name"])
        customer = customer_cache.get(customer_key)
        if customer is None:
            customer = get_active_customer_by_name(db, factory_id, row["customer_name"])
            customer_cache[customer_key] = customer
        row["customer_code"] = customer.customer_code
        row["customer_name"] = customer.customer_name

    source_line_ids = [_source_line_id(factory_id, row) for row in rows]
    existing_line_ids = set(
        db.scalars(
            select(CartonInventoryMovement.source_line_id).where(
                CartonInventoryMovement.factory_id == factory_id,
                CartonInventoryMovement.source_type == "HISTORY_INVENTORY",
                CartonInventoryMovement.source_line_id.in_(source_line_ids),
            )
        ).all()
    )
    seen: set[str] = set()
    movement_ids: list[str] = []
    skipped_count = 0
    matched_count = 0
    standalone_count = 0
    total_quantity = Decimal(0)

    try:
        for row, source_line_id in zip(rows, source_line_ids, strict=True):
            if source_line_id in existing_line_ids or source_line_id in seen:
                skipped_count += 1
                warnings.append(f"{row['source']} 与既有或本文件其他记录重复，已跳过")
                continue
            seen.add(source_line_id)
            customer = customer_cache[_normalized(row["customer_name"])]

            occurred_at = datetime.fromisoformat(row["snapshot_date"]).replace(
                hour=0, minute=0, second=0
            ).isoformat(timespec="seconds") + "+08:00"
            _ensure_period_open(db, factory_id, row["customer_code"], occurred_at)
            order_line, order = _match_order_line(db, factory_id, row)
            if order_line is not None and order is not None:
                matched_count += 1
                contract_no = order_line.contract_no
                order_line_id = order_line.id
            else:
                standalone_count += 1
                contract_no = row["contract_no"]
                order_line_id = None
                warnings.append(f"{row['source']} 未唯一匹配正式订单明细，已作为独立旧库存入账")

            movement_id = f"CIM-{uuid4().hex}"
            db.add(
                CartonInventoryMovement(
                    id=movement_id,
                    factory_id=factory_id,
                    order_line_id=order_line_id,
                    customer_code=customer.customer_code,
                    customer_name=customer.customer_name,
                    contract_no=contract_no,
                    item_no=row["item_no"],
                    packaging_type=row["packaging_type"],
                    paper_quality=row["paper_quality"],
                    specification=row["specification"],
                    movement_type="ADJUSTMENT",
                    quantity=row["opening_quantity"],
                    unit=row["unit"],
                    unit_price=row["unit_price"],
                    currency=row["currency"],
                    location=row["location"],
                    document_no=row["document_no"] or f"HIST-STOCK-{row['snapshot_date']}-{row['source_row']}",
                    source_type="HISTORY_INVENTORY",
                    source_id=source_id,
                    source_line_id=source_line_id,
                    reversal_of_movement_id=None,
                    reason=row["note"] or "历史库存期初导入",
                    actor_user_id=user.id,
                    actor_name=user.display_name,
                    occurred_at=occurred_at,
                )
            )
            movement_ids.append(movement_id)
            total_quantity += row["opening_quantity"]

        _audit(
            db,
            user,
            factory_id,
            "HISTORY_INVENTORY_IMPORTED",
            "carton_inventory_import",
            source_id,
            {
                "filename": filename,
                "source_sha256": source_hash,
                "row_count": len(rows),
                "imported_count": len(movement_ids),
                "skipped_count": skipped_count,
                "matched_order_line_count": matched_count,
                "standalone_count": standalone_count,
                "total_quantity": str(total_quantity),
            },
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="历史库存记录与既有流水发生冲突") from exc
    except Exception:
        db.rollback()
        raise

    return CartonHistoryInventoryImportOut(
        factory_id=factory_id,
        original_filename=filename,
        row_count=len(rows),
        imported_count=len(movement_ids),
        skipped_count=skipped_count,
        matched_order_line_count=matched_count,
        standalone_count=standalone_count,
        total_quantity=total_quantity.quantize(QUANTITY_QUANTUM),
        duplicate=False,
        movement_ids=movement_ids,
        warnings=warnings,
    )
