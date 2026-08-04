from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any, Callable

from app.services.huaxing_order_legacy import (
    edu_po_parser,
    edu_schedule,
    multi_po_parser,
    multi_schedule,
    new_order_excel,
    shixin_schedule,
    three_sixty_po_parser,
    three_sixty_schedule,
    yinhui_po_parser,
    yinhui_schedule,
)


PREVIEW_SCHEMA_VERSION = "customer-order-huaxing-mapped-preview-v1"


class HuaxingCustomerOrderError(ValueError):
    """A customer workbook could not be mapped safely."""


@dataclass(frozen=True)
class HuaxingCustomerMappingSpec:
    code: str
    name: str
    po_extensions: tuple[str, ...]
    schedule_extensions: tuple[str, ...]
    input_template: str
    target_template: str
    rule_summary: str


@dataclass
class PreparedBatch:
    records: list[dict[str, Any]]
    warnings: list[str]
    sheet_name: str


HUAXING_CUSTOMER_MAPPINGS: dict[str, HuaxingCustomerMappingSpec] = {
    "edu": HuaxingCustomerMappingSpec(
        "edu", "EDU", (".xls", ".xlsx", ".xlsm"), (".xls", ".xlsx", ".xlsm"),
        "HUAXING_EDU_ORDER_V1", "HUAXING_EDU_NEW_ORDER_V1",
        "按 PO 版本去重，自动续编 EDUHX 单号；验货期为走货期前 7 天并避开周末。",
    ),
    "360": HuaxingCustomerMappingSpec(
        "360", "360", (".pdf", ".xlsx", ".xlsm"), (".xlsx", ".xlsm"),
        "HUAXING_360_CONTRACT_RELEASE_V1", "HUAXING_360_NEW_ORDER_V1",
        "主合同补价格、Release 生成新单；按 RL 修订版去重并继承 360 排期主数据与日期码。",
    ),
    "yinhui": HuaxingCustomerMappingSpec(
        "yinhui", "银辉", (".pdf", ".xlsx", ".xlsm"), (".xlsx", ".xlsm"),
        "HUAXING_YINHUI_ORDER_V1", "HUAXING_YINHUI_NEW_ORDER_V1",
        "USD 按 7.75 换算 HKD，验货期为走货期前 5 天，并核对行金额及大写金额。",
    ),
    "seasons": HuaxingCustomerMappingSpec(
        "seasons", "SEASONS（施信）", (".pdf", ".xls", ".xlsx", ".xlsm"),
        (".xls", ".xlsx", ".xlsm"), "HUAXING_SEASONS_QF_PO_V1",
        "HUAXING_SEASONS_NEW_ORDER_V1",
        "区分 QF 预备单与正式 PO；同单同货号去重，数量冲突按修改单拦截。",
    ),
    "maxx": HuaxingCustomerMappingSpec(
        "maxx", "Maxx", (".pdf", ".xlsx", ".xlsm"), (".xlsx",),
        "HUAXING_MAXX_ORDER_V1", "HUAXING_MAXX_NEW_ORDER_V1",
        "严格识别 Maxx 客户，按 PO 修订版及现有排期去重；完成及验货日期为 Shipment 前 7 天。",
    ),
    "shushupapa": HuaxingCustomerMappingSpec(
        "shushupapa", "Shushupapa", (".pdf", ".xlsx", ".xlsm"), (".xlsx",),
        "HUAXING_SHUSHUPAPA_ORDER_V1", "HUAXING_SHUSHUPAPA_NEW_ORDER_V1",
        "严格识别 Shushupapa 客户并隔离客户数据；按 PO 修订版去重，验货日期为走货期前 7 天。",
    ),
}


def get_huaxing_customer_mapping(customer_code: str) -> HuaxingCustomerMappingSpec:
    try:
        return HUAXING_CUSTOMER_MAPPINGS[customer_code]
    except KeyError as exc:
        raise HuaxingCustomerOrderError(f"不支持的华兴客户映射：{customer_code}") from exc


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _joined(*values: Any) -> str:
    return "；".join(dict.fromkeys(text for value in values if (text := _text(value))))


def _combined_hash(file_names: list[str], hashes: list[str]) -> str:
    if len(hashes) == 1:
        return hashes[0]
    payload = "\n".join(
        f"{name}:{digest}" for name, digest in zip(file_names, hashes, strict=True)
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _business_key(*values: Any) -> tuple[str, ...]:
    return tuple(re.sub(r"[^A-Z0-9]", "", _text(value).upper()) for value in values)


def _quantity_key(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return _text(value)


def _mark_existing_order_lines(
    records: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    *,
    identity_fields: tuple[str, ...],
    quantity_field: str = "quantity",
) -> tuple[int, int]:
    existing_by_key: defaultdict[tuple[str, ...], set[str]] = defaultdict(set)
    for row in existing:
        key = _business_key(*(row.get(field) for field in identity_fields))
        if key and all(key):
            existing_by_key[key].add(_quantity_key(row.get(quantity_field)))

    duplicate_count = 0
    conflict_count = 0
    for record in records:
        key = _business_key(*(record.get(field) for field in identity_fields))
        quantities = existing_by_key.get(key) if key and all(key) else None
        if not quantities:
            continue
        quantity = _quantity_key(record.get(quantity_field))
        if quantity and quantity in quantities:
            record["_duplicate_existing"] = True
            duplicate_count += 1
            continue
        record.setdefault("flags", []).append({
            "level": "high",
            "code": "existing_quantity_conflict",
            "text": "相同订单及货号已存在排期，但数量不同；按修改/补单阻断",
        })
        record["risk_level"] = "high"
        conflict_count += 1
    return duplicate_count, conflict_count


def _safe_output_name(schedule_file_name: str, customer_name: str) -> str:
    stem = re.sub(r"[\\/:*?\"<>|]+", "_", Path(schedule_file_name).stem).strip(" ._")
    return f"{stem or '华兴客户排期'}_{customer_name}新单.xlsx"


def _schedule_kind(parsed: dict[str, Any], file_name: str) -> str:
    kinds = {
        _text(record.get("customer_type"))
        for record in parsed.get("records", [])
        if _text(record.get("customer_type")) in {"EDU", "彩星"}
    }
    if len(kinds) == 1:
        return kinds.pop()
    names = " ".join([
        file_name,
        _text(parsed.get("sheet")),
        *[_text(value) for value in parsed.get("meta", {}).get("sheet_names", [])],
    ])
    if "EDU" in names.upper():
        return "EDU"
    if "彩星" in names:
        return "彩星"
    raise HuaxingCustomerOrderError("无法判断底表是否属于 EDU；请在文件名或工作表名中标明 EDU")


def _next_edu_number(existing: list[dict[str, Any]]) -> int:
    values: list[int] = []
    for row in existing:
        match = re.search(r"EDUHX0*(\d+)", _text(row.get("huaxing_po")), re.I)
        if match:
            values.append(int(match.group(1)))
    return max(values, default=0) + 1


def _prepare_edu(
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    schedule = edu_schedule.read_schedule(schedule_content, filename=schedule_file_name)
    if _schedule_kind(schedule, schedule_file_name) != "EDU":
        raise HuaxingCustomerOrderError("当前入口只允许 EDU 排期底表，已拦截其他客户模板")
    parsed_files: list[dict[str, Any]] = []
    warnings: list[str] = []
    for file_name, content in po_files:
        try:
            parsed = edu_po_parser.parse_po_file(content, filename=file_name)
        except Exception as exc:
            raise HuaxingCustomerOrderError(f"{file_name}：无法读取 EDU PO：{exc}") from exc
        if parsed.get("customer_type") != "EDU":
            detected = _text(parsed.get("customer_type")) or "未知客户"
            raise HuaxingCustomerOrderError(
                f"{file_name}：识别为 {detected}，当前入口只处理 EDU"
            )
        for row in parsed.get("rows", []):
            row["_source_po_file_name"] = file_name
        warnings.extend(f"{file_name}：{item}" for item in parsed.get("warnings", []))
        parsed_files.append(parsed)
    next_number = _next_edu_number(schedule["records"])
    for parsed in parsed_files:
        generated = f"EDUHX{next_number:05d}"
        for row in parsed.get("rows", []):
            row["huaxing_po"] = row.get("huaxing_po") or generated
            edu_schedule.add_derived_fields(row)
        next_number += 1
    records, dedupe = edu_po_parser.merge_po_results(parsed_files)
    duplicate_count, conflict_count = _mark_existing_order_lines(
        records,
        schedule["records"],
        identity_fields=("customer_po", "item_no"),
    )
    if duplicate_count:
        warnings.append(f"当前 EDU 排期已有 {duplicate_count} 行相同订单，测试阶段需逐项确认。")
    if conflict_count:
        warnings.append(f"当前 EDU 排期有 {conflict_count} 行相同订单但数量不同，已按修改/补单阻断。")
    return PreparedBatch(records, [*warnings, *dedupe], _text(schedule.get("sheet")) or "EDU排期")


def _prepare_360(
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    schedule = three_sixty_schedule.read_schedule(
        schedule_content, filename=schedule_file_name, sheet_name="360客排期表",
    )
    parsed_files: list[dict[str, Any]] = []
    warnings: list[str] = []
    for file_name, content in po_files:
        try:
            parsed = three_sixty_po_parser.parse_po_file(content, filename=file_name)
        except Exception as exc:
            raise HuaxingCustomerOrderError(f"{file_name}：无法读取 360 主合同/Release：{exc}") from exc
        for row in parsed.get("rows", []):
            row["_source_po_file_name"] = file_name
        warnings.extend(f"{file_name}：{item}" for item in parsed.get("warnings", []))
        parsed_files.append(parsed)
    document_types = {item.get("document_type") for item in parsed_files}
    if "contract" in document_types and "release" not in document_types:
        warnings.append("本批只有主合同、缺少对应 Release，因此没有生成新单行。")
    if "release" in document_types and "contract" not in document_types:
        warnings.append("本批只有 Release、缺少主合同，单价和金额可能无法核对。")
    recognized = three_sixty_po_parser.merge_po_results(parsed_files)
    if any(row.get("unit_price_usd") in (None, "") for row in recognized):
        warnings.append("部分 Release 未匹配到相同合同号及货号的主合同价格，请人工核对。")
    prepared, inherited = three_sixty_schedule.apply_schedule_reference_data(
        schedule_content, recognized,
    )
    prepared = three_sixty_schedule.apply_schedule_date_codes(schedule_content, prepared)
    records, existing = three_sixty_schedule.filter_existing_schedule_records(
        schedule_content, prepared,
    )
    for record in existing:
        record["_duplicate_existing"] = True
    records.extend(existing)
    warnings.extend(inherited)
    missing_pack = [
        _text(row.get("production_no")) for row in records
        if row.get("quantity") not in (None, "") and row.get("outer_pack") in (None, "", 0)
    ]
    if missing_pack:
        warnings.append(
            f"{len(missing_pack)} 行未提供外箱装箱数，箱数保持空白：" + "、".join(missing_pack[:20])
        )
    if existing:
        numbers = sorted({_text(row.get("production_no")) for row in existing if row.get("production_no")})
        warnings.append(
            f"{len(existing)} 行已存在当前/历史排期，测试阶段可确认后重复生成："
            + "、".join(numbers[:20])
        )
    return PreparedBatch(records, warnings, _text(schedule.get("sheet")) or "360客排期表")


def _prepare_yinhui(
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    schedule = yinhui_schedule.read_schedule(schedule_content, filename=schedule_file_name)
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    duplicate_count = 0
    for file_name, content in po_files:
        try:
            parsed = yinhui_po_parser.parse_po(content, file_name)
        except Exception as exc:
            raise HuaxingCustomerOrderError(f"{file_name}：无法读取银辉 PO：{exc}") from exc
        warnings.extend(f"{file_name}：{item}" for item in parsed.get("warnings", []))
        for row in parsed.get("rows", []):
            key = tuple(_text(row.get(field)).upper() for field in (
                "contract_no", "item_no", "quantity", "po_ship_date", "unit_price_usd", "total_usd",
            ))
            if key in seen:
                duplicate_count += 1
                continue
            seen.add(key)
            row["_source_po_file_name"] = file_name
            records.append(row)
    if duplicate_count:
        warnings.append(f"本批去除 {duplicate_count} 行完全重复的银辉明细。")
    existing_count, conflict_count = _mark_existing_order_lines(
        records,
        schedule["records"],
        identity_fields=("contract_no", "item_no"),
    )
    if existing_count:
        warnings.append(f"当前银辉排期已有 {existing_count} 行相同订单，测试阶段需逐项确认。")
    if conflict_count:
        warnings.append(f"当前银辉排期有 {conflict_count} 行相同订单但数量不同，已按修改/补单阻断。")
    return PreparedBatch(records, warnings, _text(schedule.get("sheet")) or "银辉排期")


def _prepare_seasons(
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    schedule = shixin_schedule.parse_schedule(schedule_content, schedule_file_name)
    if schedule.get("family") != "seasons":
        raise HuaxingCustomerOrderError(
            "当前入口只允许 SEASONS（施信）的“正单评审表”，不能使用施信综合内部排期"
        )
    documents: list[dict[str, Any]] = []
    for file_name, content in po_files:
        try:
            document = shixin_schedule.parse_order_documents(
                content, file_name, schedule.get("records", []),
            )
        except Exception as exc:
            raise HuaxingCustomerOrderError(f"{file_name}：无法读取 SEASONS QF/PO：{exc}") from exc
        for row in document.get("records", []):
            row["_source_po_file_name"] = file_name
        documents.append(document)
    reconciled = shixin_schedule.reconcile_documents(documents, schedule.get("records", []))
    warnings = [
        _text(item).replace(
            "本次不重复生成、不重复入库",
            "测试阶段可在预览确认后重复生成",
        )
        for item in reconciled.get("warnings", [])
    ]
    existing_records = [
        {**record, "_duplicate_existing": True}
        for record in reconciled.get("existing_records", [])
    ]
    if reconciled.get("modification_records"):
        warnings.append(
            f"{len(reconciled['modification_records'])} 行数量冲突已按修改/补单拦截，不进入本次新单。"
        )
    return PreparedBatch(
        [*reconciled.get("records", []), *existing_records],
        warnings,
        _text(schedule.get("sheet")) or "正单评审表",
    )


def _multi_revision(file_name: str) -> int:
    name = re.sub(r"\(\d+\)\s*$", "", Path(file_name).stem).strip()
    best = 0
    for pattern in (r"rev\.?\s*(\d+)", r"\br\.?\s*(\d+)", r"\bv\.?\s*(\d+)"):
        for match in re.finditer(pattern, name, re.I):
            best = max(best, int(match.group(1)))
    return 1 if best == 0 and re.search(r"\brev\b", name, re.I) else best


def _dedupe_multi_orders(orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: defaultdict[str, list[tuple[int, str, dict[str, Any]]]] = defaultdict(list)
    result: list[dict[str, Any]] = []
    report: list[str] = []
    for order in orders:
        po_number = _text(order.get("po_number"))
        if not po_number:
            result.append(order)
            continue
        grouped[po_number.upper()].append(
            (_multi_revision(_text(order.get("filename"))), _text(order.get("filename")), order)
        )
    for po_number, entries in grouped.items():
        entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
        result.append(entries[0][2])
        if len(entries) > 1:
            report.append(
                f"PO {po_number}：保留 {entries[0][1]}，去掉 " + "、".join(item[1] for item in entries[1:])
            )
    return result, report


def _prepare_multi(
    customer_code: str, po_files: list[tuple[str, bytes]],
    schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    with TemporaryDirectory(prefix=f"huaxing-{customer_code}-") as temp_dir:
        schedule_path = Path(temp_dir) / Path(schedule_file_name).name
        schedule_path.write_bytes(schedule_content)
        try:
            info = multi_schedule.inspect_schedule(schedule_path, customer_code)
            history = multi_schedule._read_order_history(customer_code, schedule_path)
        except Exception as exc:
            name = get_huaxing_customer_mapping(customer_code).name
            raise HuaxingCustomerOrderError(
                f"{schedule_file_name}：无法读取 {name} 排期：{exc}"
            ) from exc
    orders: list[dict[str, Any]] = []
    warnings: list[str] = []
    for file_name, content in po_files:
        try:
            order = multi_po_parser.parse_po(content, file_name)
        except Exception as exc:
            raise HuaxingCustomerOrderError(f"{file_name}：无法读取 PO：{exc}") from exc
        detected = _text(order.get("client")).lower()
        if detected != customer_code:
            detected_name = _text(order.get("client_name")) or "未知客户"
            expected_name = get_huaxing_customer_mapping(customer_code).name
            raise HuaxingCustomerOrderError(
                f"{file_name}：识别为 {detected_name}，当前入口只处理 {expected_name}"
            )
        warnings.extend(f"{file_name}：{item}" for item in order.get("warnings", []))
        orders.append(order)
    orders, revision_warnings = _dedupe_multi_orders(orders)
    warnings.extend(revision_warnings)
    existing_by_po = {
        multi_schedule.normalize_key(record.get("po_number")) for record in history
        if multi_schedule.normalize_key(record.get("po_number"))
    }
    records: list[dict[str, Any]] = []
    existing_count = 0
    for order in orders:
        for line in order.get("lines", []):
            if line.get("is_charge"):
                continue
            po_number = line.get("po_number") or order.get("po_number")
            duplicate_existing = (
                multi_schedule.normalize_key(po_number) in existing_by_po
            )
            if duplicate_existing:
                existing_count += 1
            row = multi_schedule._line_values(order, line)
            row["_source_po_file_name"] = _text(order.get("filename"))
            row["flags"] = multi_schedule._record_flags(row, customer_code, date.today())
            if duplicate_existing:
                row["_duplicate_existing"] = True
            records.append(row)
    if existing_count:
        warnings.append(
            f"{existing_count} 行 PO 已存在当前或已走货排期，"
            "测试阶段可在预览确认后重复生成。"
        )
    return PreparedBatch(records, warnings, _text(info.get("sheet")))


def _prepare_batch(
    customer_code: str, po_files: list[tuple[str, bytes]],
    schedule_file_name: str, schedule_content: bytes,
) -> PreparedBatch:
    handlers: dict[str, Callable[[list[tuple[str, bytes]], str, bytes], PreparedBatch]] = {
        "edu": _prepare_edu,
        "360": _prepare_360,
        "yinhui": _prepare_yinhui,
        "seasons": _prepare_seasons,
    }
    if customer_code in {"maxx", "shushupapa"}:
        return _prepare_multi(customer_code, po_files, schedule_file_name, schedule_content)
    try:
        return handlers[customer_code](po_files, schedule_file_name, schedule_content)
    except HuaxingCustomerOrderError:
        raise
    except Exception as exc:
        raise HuaxingCustomerOrderError(str(exc)) from exc


def _record_fields(customer_code: str, record: dict[str, Any]) -> dict[str, Any]:
    if customer_code == "edu":
        return {
            "po_no": record.get("customer_po"),
            "contract_no": record.get("contract_no") or record.get("huaxing_po"),
            "customer_name": record.get("customer"),
            "country": record.get("country"),
            "product_no": record.get("item_no"),
            "product_name_zh": record.get("product_name"),
            "quantity": record.get("quantity"),
            "units_per_carton": record.get("case_pack"),
            "carton_count": record.get("cartons"),
            "standard": record.get("standards"),
            "unit_price_hkd": record.get("unit_price"),
            "amount_hkd": record.get("amount"),
            "packaging": record.get("packaging"),
            "line_q": record.get("inspection_date"),
            "requested_ship_date": record.get("ship_date"),
        }
    if customer_code == "360":
        return {
            "po_no": record.get("customer_po") or record.get("po_no") or record.get("production_no"),
            "contract_no": record.get("contract_no") or record.get("production_no"),
            "customer_country": record.get("customer_country"),
            "customer_name": record.get("customer"),
            "country": record.get("customer_country"),
            "product_no": record.get("item_full") or record.get("item_no"),
            "product_name_zh": record.get("product_name"),
            "quantity": record.get("quantity"),
            "units_per_carton": record.get("outer_pack"),
            "carton_count": record.get("cartons"),
            "standard": record.get("spec"),
            "unit_price_hkd": record.get("unit_price_hkd"),
            "amount_hkd": record.get("total_hkd"),
            "packaging": _joined(record.get("artwork"), record.get("manual"), record.get("customer_label")),
            "line_q": record.get("inspection_date"),
            "customer_q": record.get("fcd_date"),
            "requested_ship_date": record.get("po_ship_date"),
        }
    if customer_code == "yinhui":
        return {
            "po_no": record.get("contract_no"),
            "contract_no": record.get("contract_no"),
            "customer_name": record.get("customer"),
            "product_no": record.get("item_no"),
            "product_name_zh": record.get("product_name"),
            "product_name_en": record.get("product_name"),
            "quantity": record.get("quantity"),
            "units_per_carton": record.get("case_pack"),
            "carton_count": record.get("cartons"),
            "standard": record.get("spec"),
            "unit_price_hkd": record.get("unit_price_hkd"),
            "amount_hkd": record.get("total_hkd"),
            "packaging": _joined(record.get("artwork"), record.get("manual"), record.get("customer_label")),
            "line_q": record.get("factory_review_date"),
            "customer_q": record.get("inspection_date"),
            "requested_ship_date": record.get("po_ship_date"),
        }
    if customer_code == "seasons":
        return {
            "po_no": record.get("po_no") or record.get("oqf_no"),
            "contract_no": record.get("oc_no"),
            "customer_name": record.get("customer"),
            "country": record.get("customer"),
            "product_no": record.get("item_no"),
            "product_name_zh": record.get("product_name"),
            "product_name_en": record.get("product_name"),
            "quantity": record.get("quantity"),
            "units_per_carton": record.get("pack_qty"),
            "carton_count": record.get("cartons"),
            "standard": record.get("standard"),
            "unit_price_hkd": record.get("unit_price"),
            "amount_hkd": record.get("amount"),
            "packaging": record.get("packaging"),
            "line_q": record.get("factory_inspection"),
            "customer_q": record.get("customer_inspection"),
            "requested_ship_date": record.get("ship_date"),
        }
    return {
        "po_no": record.get("po_number"),
        "contract_no": record.get("po_number"),
        "customer_name": record.get("customer"),
        "country": record.get("country"),
        "product_no": record.get("item"),
        "product_name_en": record.get("product"),
        "quantity": record.get("quantity"),
        "units_per_carton": record.get("outer_pack") or record.get("inner_pack"),
        "carton_count": record.get("cartons"),
        "standard": _joined(record.get("country"), "PO价格币种USD"),
        "packaging": _joined(record.get("color_box"), record.get("manual"), record.get("label")),
        "line_q": record.get("complete_date"),
        "customer_q": record.get("inspection_date"),
        "requested_ship_date": record.get("ship_date"),
    }


def _issues(record: dict[str, Any], row_id: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, flag in enumerate(record.get("flags") or []):
        severity = "blocked" if flag.get("level") == "high" else "warning"
        code = _text(flag.get("code")) or f"risk_{index + 1}"
        if code in seen:
            continue
        seen.add(code)
        issues.append({
            "severity": severity,
            "code": code,
            "field": code.removeprefix("missing_"),
            "message": _text(flag.get("text")) or "该行需要人工复核",
            "can_skip": False,
            "skip_key": f"{row_id}:{code}",
            "skip_label": "",
        })
    if record.get("risk_level") == "high" and not any(
        item["severity"] == "blocked" for item in issues
    ):
        issues.append({
            "severity": "blocked",
            "code": "legacy_high_risk",
            "field": "row",
            "message": _text(record.get("risk_text")) or "旧系统规则判定为高风险，请人工处理",
            "can_skip": False,
            "skip_key": f"{row_id}:legacy_high_risk",
            "skip_label": "",
        })
    elif record.get("risk_level") == "medium" and not issues:
        issues.append({
            "severity": "warning",
            "code": "legacy_medium_risk",
            "field": "row",
            "message": _text(record.get("risk_text")) or "旧系统规则要求人工复核",
            "can_skip": False,
            "skip_key": f"{row_id}:legacy_medium_risk",
            "skip_label": "",
        })
    if record.get("_duplicate_existing"):
        duplicate_identity = _joined(
            record.get("customer_po"),
            record.get("po_no"),
            record.get("po_number"),
            record.get("production_no"),
            record.get("oqf_no"),
            record.get("contract_no"),
        ) or "当前订单"
        issues.append({
            "severity": "blocked",
            "code": "duplicate_existing_order",
            "field": "po_no",
            "message": (
                f"{duplicate_identity} 已存在当前或历史排期；"
                "测试阶段可人工确认后重复导入"
            ),
            "can_skip": True,
            "skip_key": f"{row_id}:duplicate_existing_order",
            "skip_label": "测试阶段确认重复导入当前或历史排期已有订单",
        })
    return issues


def _preview_row(
    *, customer_code: str, spec: HuaxingCustomerMappingSpec, received_date: str,
    record: dict[str, Any], index: int, default_source_file: str, sheet_name: str,
) -> dict[str, Any]:
    values = _record_fields(customer_code, record)
    row_id = f"{customer_code}-{index}"
    issues = _issues(record, row_id)
    status = (
        "blocked" if any(item["severity"] == "blocked" for item in issues)
        else "warning" if issues else "valid"
    )
    source_file = _text(record.get("_source_po_file_name")) or default_source_file
    source_sheet = _text(record.get("source_sheet") or record.get("schedule_category")) or sheet_name
    source_row = _text(record.get("source_row") or record.get("row_number") or record.get("row"))
    source_reference = f"{source_file} · {source_sheet}"
    if source_row:
        source_reference += f" 第 {source_row} 行"
    common: dict[str, Any] = {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "可导出", "warning": "需复核", "blocked": "已阻断"}[status],
        "row_role": "detail",
        "parent_product_no": "",
        "received_date": received_date,
        "po_no": "", "contract_no": "", "customer_country": "",
        "customer_name": "", "country": "", "product_no": "",
        "product_name_zh": "", "product_name_en": "", "quantity": "",
        "units_per_carton": "", "carton_count": "", "standard": "",
        "unit_price_hkd": "", "amount_hkd": "", "packaging": "",
        "line_q": "", "customer_q": "", "requested_ship_date": "",
        "input_template": spec.input_template,
        "target_template": spec.target_template,
        "item_sheet_name": sheet_name,
        "source_po_file_name": source_file,
        "lineage": {"source": source_reference, "mapping_rule": spec.rule_summary},
        "issues": issues,
    }
    for field, value in values.items():
        common[field] = _text(value)
    if not common["customer_country"]:
        common["customer_country"] = _joined(common["customer_name"], common["country"])
    return common


def create_huaxing_customer_preview(
    *, customer_code: str, factory_id: str, received_date: str,
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
) -> dict[str, Any]:
    spec = get_huaxing_customer_mapping(customer_code)
    if factory_id != "huaxing":
        raise HuaxingCustomerOrderError(f"{spec.name} 只属于华兴厂区，不能导入其他厂区")
    if not po_files:
        raise HuaxingCustomerOrderError(f"请至少上传一份 {spec.name} PO")
    try:
        normalized_received_date = date.fromisoformat(received_date).isoformat()
    except ValueError as exc:
        raise HuaxingCustomerOrderError("来单日期必须是 YYYY-MM-DD") from exc
    prepared = _prepare_batch(customer_code, po_files, schedule_file_name, schedule_content)
    first_file_name = po_files[0][0]
    rows = [
        _preview_row(
            customer_code=customer_code, spec=spec,
            received_date=normalized_received_date, record=record, index=index,
            default_source_file=first_file_name, sheet_name=prepared.sheet_name,
        )
        for index, record in enumerate(prepared.records, start=1)
    ]
    file_names = [name for name, _ in po_files]
    po_hashes = [sha256(content).hexdigest() for _, content in po_files]
    return {
        "preview_schema_version": PREVIEW_SCHEMA_VERSION,
        "customer_code": customer_code,
        "factory_id": factory_id,
        "po_file_name": file_names[0] if len(file_names) == 1 else f"{len(file_names)}个文件",
        "po_file_names": file_names,
        "po_file_count": len(file_names),
        "schedule_file_name": schedule_file_name,
        "source_po_sha256": _combined_hash(file_names, po_hashes),
        "source_po_sha256s": po_hashes,
        "source_schedule_sha256": sha256(schedule_content).hexdigest(),
        "input_template": spec.input_template,
        "target_template": spec.target_template,
        "output_file_name": _safe_output_name(schedule_file_name, spec.name),
        "summary": {
            "total": len(rows),
            "valid": sum(row["status"] == "valid" for row in rows),
            "warning": sum(row["status"] == "warning" for row in rows),
            "blocked": sum(row["status"] == "blocked" for row in rows),
        },
        "rows": rows,
        "warnings": list(dict.fromkeys([
            spec.rule_summary,
            "导出结果为继承当前排期表头、格式和产品主数据的独立“新单”工作簿，不会覆盖原排期。",
            *prepared.warnings,
        ])),
    }


def _export_prepared(
    *, customer_code: str, prepared: PreparedBatch, schedule_file_name: str,
    schedule_content: bytes, output_path: Path,
) -> None:
    if customer_code == "edu":
        schedule = edu_schedule.read_schedule(schedule_content, filename=schedule_file_name)
        edu_schedule.create_import_workbook(
            prepared.records, output_path, schedule.get("records", []), schedule_content,
        )
        return
    if customer_code == "360":
        three_sixty_schedule.create_schedule_review_workbook(
            schedule_content, prepared.records, output_path,
        )
        return
    if customer_code == "yinhui":
        yinhui_schedule.create_export(prepared.records, output_path, schedule_content)
        return
    if customer_code == "seasons":
        shixin_schedule.build_export(
            prepared.records, output_path, template_source=schedule_content,
            template_filename=schedule_file_name, sheet_names=shixin_schedule.SEASONS_SHEETS,
        )
        return
    with TemporaryDirectory(prefix=f"huaxing-{customer_code}-export-") as temp_dir:
        schedule_path = Path(temp_dir) / Path(schedule_file_name).name
        schedule_path.write_bytes(schedule_content)
        new_order_excel.create_new_order_workbook(
            schedule_path, output_path, prepared.records, multi_schedule.ALIASES,
            filename=schedule_file_name,
            sheet_names=multi_schedule.CLIENT_SHEETS[customer_code], sheet_title="新单",
        )


def _validate_skips(preview: dict[str, Any], requested_skips: set[str]) -> None:
    available_skips = {
        issue["skip_key"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["can_skip"]
    }
    if requested_skips - available_skips:
        raise HuaxingCustomerOrderError("所选确认项已失效或不允许通过，请重新解析")
    blockers = [
        issue["message"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["severity"] == "blocked"
        and issue["skip_key"] not in requested_skips
    ]
    if blockers:
        raise HuaxingCustomerOrderError(
            "仍有阻断项：" + "；".join(dict.fromkeys(blockers))
        )


def export_huaxing_customer_schedule(
    *, customer_code: str, factory_id: str, received_date: str,
    po_files: list[tuple[str, bytes]], schedule_file_name: str, schedule_content: bytes,
    skipped_issue_keys: set[str] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    preview = create_huaxing_customer_preview(
        customer_code=customer_code, factory_id=factory_id, received_date=received_date,
        po_files=po_files, schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
    )
    _validate_skips(preview, skipped_issue_keys or set())
    if not preview["rows"]:
        raise HuaxingCustomerOrderError("本批文件没有可安全生成的新单明细，请查看预览告警")
    prepared = _prepare_batch(customer_code, po_files, schedule_file_name, schedule_content)
    with TemporaryDirectory(prefix=f"huaxing-{customer_code}-output-") as temp_dir:
        output_path = Path(temp_dir) / preview["output_file_name"]
        try:
            _export_prepared(
                customer_code=customer_code, prepared=prepared,
                schedule_file_name=schedule_file_name, schedule_content=schedule_content,
                output_path=output_path,
            )
        except Exception as exc:
            name = get_huaxing_customer_mapping(customer_code).name
            raise HuaxingCustomerOrderError(f"生成 {name} 新单失败：{exc}") from exc
        return output_path.read_bytes(), preview["output_file_name"], preview
