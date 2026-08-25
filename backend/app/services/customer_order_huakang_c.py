from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Any

from app.services.huakang_c_order_legacy import huakang_po_parser, huakang_schedule
from app.services.huaxing_order_legacy.new_order_excel import (
    append_column_records_to_workbook,
    append_grouped_column_records_to_workbook,
)
from app.services.customer_order_manual import (
    apply_overrides_to_preview,
    coerce_manual_value,
    decorate_manual_resolution_policy,
)


PREVIEW_SCHEMA_VERSION = "customer-order-huakang-c-mapped-preview-v1"
EXCHANGE_RATE = 7.75


class HuakangCCustomerOrderError(ValueError):
    """A Huakang C customer order could not be mapped safely."""


@dataclass(frozen=True)
class HuakangCCustomerMappingSpec:
    code: str
    legacy_code: str
    name: str
    po_extensions: tuple[str, ...]
    schedule_extensions: tuple[str, ...]
    input_template: str
    target_template: str
    rule_summary: str


@dataclass
class PreparedBatch:
    orders: list[dict[str, Any]]
    entries: list[tuple[dict[str, Any], dict[str, Any]]]
    warnings: list[str]
    sheet_name: str
    inheritance: dict[str, Any]


_PO_EXTENSIONS = (".pdf", ".xls", ".xlsx", ".xlsm")
_SCHEDULE_EXTENSIONS = (".xls", ".xlsx", ".xlsm")


HUAKANG_C_CUSTOMER_MAPPINGS: dict[str, HuakangCCustomerMappingSpec] = {
    "index": HuakangCCustomerMappingSpec(
        "index", "index", "INDEX", _PO_EXTENSIONS, _SCHEDULE_EXTENSIONS,
        "HUAKANG_C_INDEX_PO_V1", "HUAKANG_C_INDEX_SCHEDULE_APPEND_V2",
        "读取 INDEX PO号、PO日期、Ex-Factory、产品、数量、箱规和USD价格；按货号继承唯一排期品名并以7.75换算港币。",
    ),
    "jazwares": HuakangCCustomerMappingSpec(
        "jazwares", "jazwares", "JAZAWARES", _PO_EXTENSIONS, _SCHEDULE_EXTENSIONS,
        "HUAKANG_C_JAZWARES_PO_V1", "HUAKANG_C_JAZWARES_SCHEDULE_APPEND_V2",
        "按旧版 JAZWARES 版式读取PO、版本、合同、产品、数量、PCS/CTN、走货日和USD价格；同PO保留最新修订版。",
    ),
    "maxx": HuakangCCustomerMappingSpec(
        "maxx", "maxx", "MAXX", _PO_EXTENSIONS, _SCHEDULE_EXTENSIONS,
        "HUAKANG_C_MAXX_PO_V1", "HUAKANG_C_MAXX_SCHEDULE_APPEND_V2",
        "读取 MAXX P.O.、S.C.合同、日期、货号、数量和USD价格；PO未提供装箱数时保持空白。",
    ),
    "strottman": HuakangCCustomerMappingSpec(
        "strottman", "strottman", "STROTTMAN", _PO_EXTENSIONS, _SCHEDULE_EXTENSIONS,
        "HUAKANG_C_STROTTMAN_PO_V1", "HUAKANG_C_STROTTMAN_SCHEDULE_APPEND_V2",
        "按Special Instructions把Case数量换算为PCS与每箱件数；多走货日取最早日期写主列，其余保留在备注。",
    ),
    "jp": HuakangCCustomerMappingSpec(
        "jp", "supplier", "JP", _PO_EXTENSIONS, _SCHEDULE_EXTENSIONS,
        "HUAKANG_C_JP_SUPPLIER_PO_V1", "HUAKANG_C_JP_SCHEDULE_APPEND_V2",
        "读取华康车衣中文采购单编号、日期、交货日、货号、数量和版本；只有原单明确提供的出厂价才写入JP内部排期。",
    ),
}


def get_huakang_c_customer_mapping(customer_code: str) -> HuakangCCustomerMappingSpec:
    try:
        return HUAKANG_C_CUSTOMER_MAPPINGS[customer_code]
    except KeyError as exc:
        raise HuakangCCustomerOrderError(
            f"不支持的华康C客户映射：{customer_code}"
        ) from exc


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


def _quantity_key(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return _text(value)


def _schedule_quantity_column(profile_code: str) -> int:
    return {
        "index": 11,
        "jazwares": 11,
        "maxx": 11,
        "strottman": 11,
        "supplier": 7,
    }[profile_code]


def _safe_output_name(schedule_file_name: str, customer_name: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(schedule_file_name).stem).strip(" ._")
    suffix = ".xlsm" if Path(schedule_file_name).suffix.lower() == ".xlsm" else ".xlsx"
    return f"{stem or '华康C排期'}_{customer_name}新单{suffix}"


def _revision(file_name: str, order: dict[str, Any]) -> int:
    best = 0
    name = re.sub(r"\(\d+\)\s*$", "", Path(file_name).stem).strip()
    for pattern in (r"rev\.?\s*(\d+)", r"\bv\.?\s*(\d+)", r"\br\.?\s*(\d+)"):
        for found in re.finditer(pattern, name, re.I):
            best = max(best, int(found.group(1)))
    if best == 0 and re.search(r"\brev\b", name, re.I):
        best = 1
    version = _text(order.get("version"))
    found = re.search(r"(\d+)", version)
    return max(best, int(found.group(1))) if found else best


def _deduplicate(orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    without_po: list[dict[str, Any]] = []
    for order in orders:
        po_number = _text(order.get("po_number"))
        if not po_number:
            without_po.append(order)
            continue
        grouped[(_text(order.get("customer_code")), po_number)].append(order)
    result = list(without_po)
    report: list[str] = []
    for (_, po_number), entries in grouped.items():
        entries.sort(
            key=lambda entry: (
                _revision(_text(entry.get("filename")), entry),
                _text(entry.get("filename")),
            ),
            reverse=True,
        )
        result.append(entries[0])
        if len(entries) > 1:
            report.append(
                f"PO {po_number}：保留 {_text(entries[0].get('filename'))}；忽略 "
                + "、".join(_text(entry.get("filename")) for entry in entries[1:])
            )
    return result, report


def _temporary_name(index: int, file_name: str) -> str:
    return f"{index:03d}_{Path(file_name).name or f'PO-{index}'}"


def _load_schedule(
    schedule_path: Path,
    spec: HuakangCCustomerMappingSpec,
) -> tuple[Any, Any]:
    profile = huakang_schedule.PROFILES[spec.legacy_code]
    workbook = huakang_schedule._load_workbook(schedule_path)
    try:
        worksheet = huakang_schedule._select_sheet(workbook, profile)
    except Exception:
        workbook.close()
        raise
    return workbook, worksheet


def _prepare_batch(
    *,
    spec: HuakangCCustomerMappingSpec,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
    received_date: str,
) -> PreparedBatch:
    parser = huakang_po_parser.HuakangPOParser()
    orders: list[dict[str, Any]] = []
    errors: list[str] = []
    with TemporaryDirectory(prefix=f"huakang-c-{spec.code}-") as temp_dir:
        root = Path(temp_dir)
        schedule_path = root / (Path(schedule_file_name).name or "客户排期.xlsx")
        schedule_path.write_bytes(schedule_content)
        try:
            workbook, worksheet = _load_schedule(schedule_path, spec)
        except Exception as exc:
            raise HuakangCCustomerOrderError(
                f"{schedule_file_name}：无法读取{spec.name}排期：{exc}"
            ) from exc
        sheet_name = worksheet.title
        workbook.close()

        for index, (file_name, content) in enumerate(po_files, start=1):
            po_path = root / _temporary_name(index, file_name)
            po_path.write_bytes(content)
            try:
                order = parser.parse(str(po_path))
            except Exception as exc:
                errors.append(f"{file_name}：无法读取PO：{exc}")
                continue
            detected = _text(order.get("customer_code")).lower()
            if detected != spec.legacy_code:
                detected_name = huakang_po_parser.CUSTOMERS.get(detected, detected or "未知客户")
                raise HuakangCCustomerOrderError(
                    f"{file_name}：识别为{detected_name}，当前入口只处理{spec.name}"
                )
            order["filename"] = file_name
            original_date = _text(order.get("po_date"))
            order["po_date"] = received_date
            if original_date and original_date != received_date:
                order.setdefault("warnings", []).append(
                    f"接单日期已由PO日期 {original_date} 覆盖为邮件确认日期 {received_date}。"
                )
            orders.append(order)

        if not orders:
            detail = "；".join(errors)
            raise HuakangCCustomerOrderError(
                "所有文件均解析失败" + (f"：{detail}" if detail else "")
            )
        orders, dedup_report = _deduplicate(orders)
        if spec.code == "jp":
            for order in orders:
                order.setdefault("warnings", []).append(
                    "JP旧系统只有安全格式模板，尚无真实PO与人工确认正确输出；本次结果必须逐字段复核。"
                )

        workbook, worksheet = _load_schedule(schedule_path, spec)
        try:
            profile = huakang_schedule.PROFILES[spec.legacy_code]
            entries = [
                (order, line)
                for order in orders
                for line in order.get("lines") or []
            ]
            entries, inheritance = huakang_schedule._inherit_product_names(
                worksheet,
                profile,
                entries,
            )
            existing_index = huakang_schedule._build_existing_index(worksheet, profile)
            quantity_column = _schedule_quantity_column(profile.code)
            for order, line in entries:
                key = huakang_schedule._row_key_from_order(profile, order, line)
                existing_rows = existing_index.get(key, []) if all(key) else []
                existing_quantities = {
                    _quantity_key(worksheet.cell(row, quantity_column).value)
                    for row in existing_rows
                }
                quantity = _quantity_key(line.get("qty"))
                if existing_quantities and quantity and quantity in existing_quantities:
                    line["_duplicate_existing"] = True
                elif existing_quantities:
                    line["_existing_quantity_conflict"] = True
        finally:
            workbook.close()

    warnings = [
        *errors,
        *dedup_report,
        *(
            f"{_text(order.get('filename'))}：{message}"
            for order in orders
            for message in order.get("warnings") or []
        ),
    ]
    if spec.code == "jp":
        warnings.append(
            "JP旧系统只有安全格式模板，尚无真实PO与人工确认正确输出；本次结果必须逐字段复核。"
        )
    if inheritance.get("conflicts"):
        warnings.append(
            f"排期中有 {len(inheritance['conflicts'])} 组货号对应多个品名，未自动继承。"
        )
    return PreparedBatch(
        orders=orders,
        entries=entries,
        warnings=list(dict.fromkeys(warnings)),
        sheet_name=sheet_name,
        inheritance=inheritance,
    )


def _record_fields(
    spec: HuakangCCustomerMappingSpec,
    order: dict[str, Any],
    line: dict[str, Any],
) -> dict[str, Any]:
    quantity = float(line.get("qty") or 0)
    usd_price = float(line.get("unit_price_usd") or 0)
    hkd_price = float(line.get("unit_price_hkd") or 0) or (
        usd_price * EXCHANGE_RATE if usd_price else 0
    )
    usd_amount = float(line.get("amount_usd") or 0)
    hkd_amount = usd_amount * EXCHANGE_RATE if usd_amount else quantity * hkd_price
    return {
        "po_no": order.get("po_number"),
        "contract_no": order.get("contract_no") or order.get("po_number"),
        "customer_name": spec.name,
        "country": order.get("ship_to"),
        "product_no": line.get("item_code"),
        "product_name_zh": line.get("description") if spec.code == "jp" else "",
        "product_name_en": "" if spec.code == "jp" else line.get("description"),
        "quantity": line.get("qty"),
        "units_per_carton": line.get("pcs_per_carton"),
        "carton_count": line.get("carton_qty"),
        "standard": _joined(line.get("unit"), line.get("version") or order.get("version")),
        "unit_price_hkd": round(hkd_price, 6) if hkd_price else "",
        "amount_hkd": round(hkd_amount, 2) if hkd_amount else "",
        "packaging": huakang_schedule._notes(order, line),
        "line_q": "",
        "customer_q": "",
        "requested_ship_date": order.get("ship_date"),
    }


def _jazwares_parent_item(value: Any) -> str:
    item = _text(value)
    match = re.fullmatch(r"(.+?)-(XXS|XS|S|M|L|XL|XXL|XXXL)", item, re.I)
    return match.group(1) if match else item


def _jazwares_group_entries(
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[tuple[str, list[tuple[dict[str, Any], dict[str, Any]]]]]:
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for index, (order, line) in enumerate(entries, start=1):
        parent_item = _jazwares_parent_item(line.get("item_code")) or f"未识别货号-{index}"
        line["_jazwares_parent_item"] = parent_item
        groups.setdefault(parent_item, []).append((order, line))
    return list(groups.items())


def _maxx_parent_item(order: dict[str, Any], line: dict[str, Any]) -> str:
    project_no = _text(order.get("project_no"))
    if project_no:
        return project_no
    item = _text(line.get("item_code"))
    match = re.match(r"^([A-Z0-9]+)-", item, re.I)
    return match.group(1) if match else item


def _maxx_group_entries(
    entries: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[tuple[str, list[tuple[dict[str, Any], dict[str, Any]]]]]:
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for index, (order, line) in enumerate(entries, start=1):
        parent_item = _maxx_parent_item(order, line) or f"未识别货号-{index}"
        line["_maxx_parent_item"] = parent_item
        groups.setdefault(parent_item, []).append((order, line))
    return list(groups.items())


def _strottman_group_key(entry: tuple[dict[str, Any], dict[str, Any]]) -> str:
    _order, line = entry
    return re.sub(r"-F\d+$", "", _text(line.get("item_code")), flags=re.I)


def _strottman_group_row_values(
    entry: tuple[dict[str, Any], dict[str, Any]],
    _row_no: int,
) -> dict[int, Any]:
    _order, line = entry
    return {
        1: _strottman_group_key(entry),
        4: line.get("description") or "",
    }


def _issues(order: dict[str, Any], line: dict[str, Any], row_id: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, message in enumerate(order.get("warnings") or [], start=1):
        code = f"legacy_warning_{index}"
        issues.append({
            "severity": "warning",
            "code": code,
            "field": "row",
            "message": _text(message) or "该行需要人工复核",
            "can_skip": False,
            "skip_key": f"{row_id}:{code}",
            "skip_label": "",
        })
    if line.get("_existing_quantity_conflict"):
        issues.append({
            "severity": "blocked",
            "code": "existing_quantity_conflict",
            "field": "quantity",
            "message": "相同合同/PO及货号已存在排期，但数量不同；按修改/补单阻断",
            "can_skip": False,
            "skip_key": f"{row_id}:existing_quantity_conflict",
            "skip_label": "",
        })
    if line.get("_duplicate_existing"):
        identity = _joined(
            order.get("contract_no") or order.get("po_number"),
            line.get("item_code"),
        ) or "当前订单"
        issues.append({
            "severity": "blocked",
            "code": "duplicate_existing_order",
            "field": "po_no",
            "message": f"{identity} 已存在当前{_text(order.get('customer_code')).upper()}排期；测试阶段可人工确认后重复导入",
            "can_skip": True,
            "skip_key": f"{row_id}:duplicate_existing_order",
            "skip_label": "测试阶段确认重复导入当前排期已有订单",
        })
    return issues


def _preview_row(
    *,
    spec: HuakangCCustomerMappingSpec,
    received_date: str,
    order: dict[str, Any],
    line: dict[str, Any],
    index: int,
    sheet_name: str,
) -> dict[str, Any]:
    row_id = f"huakang-c-{spec.code}-{index}"
    issues = _issues(order, line, row_id)
    source_file = _text(order.get("filename"))
    common: dict[str, Any] = {
        "id": row_id,
        "status": "blocked" if any(issue["severity"] == "blocked" for issue in issues) else "warning" if issues else "valid",
        "status_label": "已阻断" if any(issue["severity"] == "blocked" for issue in issues) else "需复核" if issues else "可导出",
        "row_role": "detail",
        "parent_product_no": "",
        "received_date": received_date,
        "po_no": "",
        "contract_no": "",
        "customer_country": "",
        "customer_name": "",
        "country": "",
        "product_no": "",
        "product_name_zh": "",
        "product_name_en": "",
        "quantity": "",
        "units_per_carton": "",
        "carton_count": "",
        "standard": "",
        "unit_price_hkd": "",
        "amount_hkd": "",
        "packaging": "",
        "line_q": "",
        "customer_q": "",
        "requested_ship_date": "",
        "input_template": spec.input_template,
        "target_template": spec.target_template,
        "item_sheet_name": sheet_name,
        "source_po_file_name": source_file,
        "lineage": {
            "source": f"{source_file} · {sheet_name}",
            "mapping_rule": spec.rule_summary,
        },
        "issues": issues,
    }
    for field_name, value in _record_fields(spec, order, line).items():
        common[field_name] = _text(value)
    common["customer_country"] = _joined(common["customer_name"], common["country"])
    return common


def create_huakang_c_customer_preview(
    *,
    customer_code: str,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> dict[str, Any]:
    spec = get_huakang_c_customer_mapping(customer_code)
    if factory_id not in {"huakang-c", "huakang-d"}:
        raise HuakangCCustomerOrderError(
            f"{spec.name}外部单映射只属于华康D（保留华康C历史兼容），不能导入其他厂区"
        )
    if not po_files:
        raise HuakangCCustomerOrderError(f"请至少上传一份{spec.name} PO")
    try:
        normalized_received_date = date.fromisoformat(received_date).isoformat()
    except ValueError as exc:
        raise HuakangCCustomerOrderError("来单日期必须是 YYYY-MM-DD") from exc

    prepared = _prepare_batch(
        spec=spec,
        po_files=po_files,
        schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
        received_date=normalized_received_date,
    )
    rows = [
        _preview_row(
            spec=spec,
            received_date=normalized_received_date,
            order=order,
            line=line,
            index=index,
            sheet_name=prepared.sheet_name,
        )
        for index, (order, line) in enumerate(prepared.entries, start=1)
    ]
    file_names = [name for name, _ in po_files]
    po_hashes = [sha256(content).hexdigest() for _, content in po_files]
    if spec.code == "jazwares":
        append_rule = (
            "JAZWARES 按现有排期的“分+总”结构追加：同一大货号的小PO明细连续写入，"
            "随后新增一行大货号合计；明细与合计分别继承最近正常明细行和合计行的完整样式、"
            "公式及行高。"
        )
    elif spec.code == "maxx":
        append_rule = (
            "MAXX 按第1行字段和第2至8行的“分+总”结构追加：Project# 作为大货号，"
            "同项目的小货号明细连续写入，随后只保留一行合计；明细与合计分别继承原表"
            "正常明细行和合计行的完整样式、公式及行高。"
        )
    elif spec.code == "strottman":
        append_rule = (
            "STROTTMAN 以“建文客排期表”第3行为字段行，并按第4至10行的结构追加："
            "每个产品先复制一行货号/品名标题，随后写入订单明细；标题与明细分别继承"
            "最近同类行的合并、字体、边框、公式和行高。"
        )
    else:
        append_rule = (
            "仅在对应客户目标表明细末尾/合计行之前插入本批新单，并从插入点向上选择"
            "最近的正常明细行继承格式、字体和公式逻辑，跳过合计/小计、分组标题和空白分隔行。"
        )
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
            "来单日期按旧系统的“邮件确认接单日期”规则覆盖PO Date。",
            "美元价格按固定汇率7.75换算港币。导出结果完整保留当前排期的所有 Sheet、"
            f"历史数据、格式、公式、图片和打印设置；{append_rule}"
            "另存为新文件，不覆盖原排期。",
            *prepared.warnings,
        ])),
    }


def export_huakang_c_customer_schedule(
    *,
    customer_code: str,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
    skipped_issue_keys: set[str] | None = None,
    manual_overrides: list[dict[str, str]] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    preview = create_huakang_c_customer_preview(
        customer_code=customer_code,
        factory_id=factory_id,
        received_date=received_date,
        po_files=po_files,
        schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
    )
    decorate_manual_resolution_policy(preview)
    apply_overrides_to_preview(preview, manual_overrides or [])
    requested_skips = set(skipped_issue_keys or set())
    skippable = {
        issue["skip_key"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue.get("skip_key")
    }
    if requested_skips - skippable:
        raise HuakangCCustomerOrderError("确认项已失效，请重新预览后再生成")
    blockers = [
        issue["message"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["severity"] == "blocked" and issue["skip_key"] not in requested_skips
    ]
    if blockers:
        raise HuakangCCustomerOrderError("仍有阻断项：" + "；".join(dict.fromkeys(blockers)))
    if not preview["rows"]:
        raise HuakangCCustomerOrderError("本批文件没有可生成的新单明细")

    spec = get_huakang_c_customer_mapping(customer_code)
    prepared = _prepare_batch(
        spec=spec,
        po_files=po_files,
        schedule_file_name=schedule_file_name,
        schedule_content=schedule_content,
        received_date=received_date,
    )
    entries_by_row = {
        str(row["id"]): entry
        for row, entry in zip(preview["rows"], prepared.entries, strict=True)
    }
    order_aliases = {
        "po_no": "po_number",
        "contract_no": "contract_no",
        "country": "ship_to",
        "requested_ship_date": "ship_date",
    }
    line_aliases = {
        "product_no": "item_code",
        "product_name_zh": "description",
        "product_name_en": "description",
        "quantity": "qty",
        "units_per_carton": "pcs_per_carton",
        "carton_count": "carton_qty",
        "unit_price_hkd": "unit_price_hkd",
        "amount_hkd": "amount_hkd",
    }
    for override in manual_overrides or []:
        entry = entries_by_row.get(override["row_id"])
        if entry is None:
            continue
        order, line = entry
        field = override["field"]
        value = coerce_manual_value(field, override["value"])
        if field in order_aliases:
            order[order_aliases[field]] = value
        else:
            line[line_aliases.get(field, field)] = value
    with TemporaryDirectory(prefix=f"huakang-c-{customer_code}-output-") as temp_dir:
        root = Path(temp_dir)
        output_path = root / preview["output_file_name"]
        try:
            profile = huakang_schedule.PROFILES[spec.legacy_code]
            safe_schedule_content = schedule_content
            if Path(schedule_file_name).suffix.lower() in {".xlsx", ".xlsm"}:
                safe_schedule_content, _date_repairs = (
                    huakang_schedule.repair_invalid_xlsx_date_bytes(schedule_content)
                )

            def row_values(entry: tuple[dict[str, Any], dict[str, Any]], row_no: int) -> dict[int, Any]:
                order, line = entry
                return huakang_schedule.compose_row(
                    profile,
                    order,
                    line,
                    row_no,
                    EXCHANGE_RATE,
                )

            if spec.code in {"jazwares", "maxx"}:
                groups = (
                    _jazwares_group_entries(prepared.entries)
                    if spec.code == "jazwares"
                    else _maxx_group_entries(prepared.entries)
                )

                def summary_values(
                    group_key: str,
                    _records: list[tuple[dict[str, Any], dict[str, Any]]],
                    _row_no: int,
                    detail_start_row: int,
                    detail_end_row: int,
                ) -> dict[int, Any]:
                    return {
                        10: f"{group_key} 合计" if spec.code == "jazwares" else "合计",
                        11: f"=SUM(K{detail_start_row}:K{detail_end_row})",
                    }

                append_grouped_column_records_to_workbook(
                    safe_schedule_content,
                    output_path,
                    groups,
                    filename=schedule_file_name,
                    sheet_names=(prepared.sheet_name, *profile.sheets),
                    header_row=profile.header_rows,
                    max_col=profile.max_col,
                    summary_columns=(10,),
                    detail_style_columns=(11,) if spec.code == "jazwares" else (),
                    detail_row_values_factory=row_values,
                    summary_row_values_factory=summary_values,
                    reuse_trailing_summary_rows=spec.code == "maxx",
                    repair_existing_summary_values_factory=(
                        (
                            lambda _row_no, detail_start_row, detail_end_row: {
                                10: "合计",
                                11: f"=SUM(K{detail_start_row}:K{detail_end_row})",
                            }
                        )
                        if spec.code == "maxx"
                        else None
                    ),
                )
            else:
                append_column_records_to_workbook(
                    safe_schedule_content,
                    output_path,
                    prepared.entries,
                    filename=schedule_file_name,
                    sheet_names=(prepared.sheet_name, *profile.sheets),
                    header_row=profile.header_rows,
                    max_col=profile.max_col,
                    detail_columns=profile.scan_cols,
                    row_values_factory=row_values,
                    group_key_factory=(
                        _strottman_group_key
                        if spec.code == "strottman"
                        else None
                    ),
                    group_row_values_factory=(
                        _strottman_group_row_values
                        if spec.code == "strottman"
                        else None
                    ),
                    column_formats=(
                        {
                            1: "yyyy/m/d;@",
                            41: "yyyy/m/d;@",
                            42: '[$HK$-C04]#,##0.00;\\-[$HK$-C04]#,##0.00',
                            43: '[$HK$-C04]#,##0.00;\\-[$HK$-C04]#,##0.00',
                            44: "yyyy/m/d;@",
                        }
                        if spec.code == "index"
                        else (
                            {4: "yyyy/m/d;@", 13: 'm"月"d"日"', 34: "yyyy/m/d;@"}
                            if spec.code == "strottman"
                            else None
                        )
                    ),
                )
        except Exception as exc:
            raise HuakangCCustomerOrderError(
                f"生成{spec.name}新单失败：{exc}"
            ) from exc
        return output_path.read_bytes(), preview["output_file_name"], preview
