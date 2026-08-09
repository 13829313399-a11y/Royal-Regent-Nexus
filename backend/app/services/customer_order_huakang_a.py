from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.services.huakang_a_order_legacy import schedule_parser
from app.services.huaxing_order_legacy.new_order_excel import (
    append_records_to_workbook,
)
from app.services.customer_order_manual import (
    apply_overrides_to_preview,
    apply_overrides_to_records,
    decorate_manual_resolution_policy,
)


PREVIEW_SCHEMA_VERSION = "customer-order-huakang-a-mapped-preview-v1"


class HuakangACustomerOrderError(ValueError):
    """A Huakang A customer order could not be mapped safely."""


@dataclass(frozen=True)
class HuakangACustomerMappingSpec:
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


HUAKANG_A_CUSTOMER_MAPPINGS: dict[str, HuakangACustomerMappingSpec] = {
    "360": HuakangACustomerMappingSpec(
        code="360",
        name="360",
        po_extensions=(".pdf", ".xls", ".xlsx", ".xlsm"),
        schedule_extensions=(".xlsx", ".xlsm"),
        input_template="HUAKANG_A_360_PO_RELEASE_V1",
        target_template="HUAKANG_A_360_SCHEDULE_APPEND_V2",
        rule_summary=(
            "读取 ThreeSixty PURCHASE ORDER RELEASE 的 RL 合同号、修订日期、客户 PO、"
            "货号、数量、装箱、验货日、FCD、柜型和卸货港，并写入“360客排期表新单”。"
        ),
    ),
}


NEW_ORDER_ALIASES = {
    "order_date": ("入单日期", "来单日期"),
    "contract_no": ("正单合同号",),
    "item_no": ("产品货号",),
    "description": ("产品名称",),
    "quantity": ("PO数量",),
    "inspection_date": ("验货日期",),
    "fcd": ("走货期FCD", "FCD"),
    "customer_po": ("第三方客户 PO NO#", "客户PO"),
    "contact": ("跟单",),
    "customer_release": ("Customer Release No.",),
    "master_carton_qty": ("外箱装箱数",),
    "total_cartons": ("总箱数",),
    "container_type": ("MS Container Type (FCL/LCL)", "柜型"),
    "port": ("Port of Discharge", "卸货港"),
    "transportation_mode": ("走货方式",),
    "source_file": ("来源文件",),
    "warnings": ("识别警告",),
}


def get_huakang_a_customer_mapping(customer_code: str) -> HuakangACustomerMappingSpec:
    try:
        return HUAKANG_A_CUSTOMER_MAPPINGS[customer_code]
    except KeyError as exc:
        raise HuakangACustomerOrderError(
            f"不支持的华康A客户映射：{customer_code}"
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


def _duplicate_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _quantity_key(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, TypeError, ValueError):
        return _text(value)


def _safe_output_name(schedule_file_name: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(schedule_file_name).stem).strip(" ._")
    suffix = ".xlsm" if Path(schedule_file_name).suffix.lower() == ".xlsm" else ".xlsx"
    return f"{stem or '华康A排期'}_360新单{suffix}"


def _temporary_name(index: int, file_name: str) -> str:
    safe_name = Path(file_name).name or f"PO-{index}"
    return f"{index:03d}_{safe_name}"


def _prepare_batch(
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> PreparedBatch:
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="huakang-a-360-") as temp_dir:
        root = Path(temp_dir)
        schedule_path = root / (Path(schedule_file_name).name or "360排期.xlsx")
        schedule_path.write_bytes(schedule_content)
        try:
            schedule = schedule_parser.load_schedule(schedule_path)
        except Exception as exc:
            raise HuakangACustomerOrderError(
                f"{schedule_file_name}：无法读取华康A 360排期：{exc}"
            ) from exc
        existing_by_key: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
        for existing in schedule.get("rows") or []:
            key = (
                _duplicate_key(existing.get("contract_no")),
                _duplicate_key(existing.get("item_no")),
            )
            if all(key):
                existing_by_key[key].add(_quantity_key(existing.get("quantity")))

        for index, (file_name, content) in enumerate(po_files, start=1):
            po_path = root / _temporary_name(index, file_name)
            po_path.write_bytes(content)
            try:
                record = schedule_parser.parse_po_file(po_path, root)
            except Exception as exc:
                raise HuakangACustomerOrderError(
                    f"{file_name}：无法读取华康A 360 PO：{exc}"
                ) from exc
            record["file_name"] = file_name
            record["relative_path"] = file_name
            record["_source_po_file_name"] = file_name
            key = (
                _duplicate_key(record.get("contract_no")),
                _duplicate_key(record.get("item_no")),
            )
            existing_quantities = existing_by_key.get(key, set()) if all(key) else set()
            quantity = _quantity_key(record.get("quantity"))
            if existing_quantities and quantity and quantity in existing_quantities:
                record["_duplicate_existing"] = True
            elif existing_quantities:
                record["_existing_quantity_conflict"] = True
            records.append(record)
            warnings.extend(
                f"{file_name}：{message}"
                for message in record.get("parse_warnings") or []
            )

    return PreparedBatch(
        records=records,
        warnings=warnings,
        sheet_name=_text(schedule.get("sheet")) or schedule_parser.SCHEDULE_SHEET,
    )


def _total_cartons(record: dict[str, Any]) -> int | str:
    quantity = schedule_parser._number(record.get("quantity"))
    carton_qty = schedule_parser._number(record.get("master_carton_qty"))
    if quantity is None or carton_qty in (None, 0):
        return ""
    return math.ceil(float(quantity) / float(carton_qty))


def _record_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "po_no": record.get("customer_po"),
        "contract_no": record.get("contract_no"),
        "customer_name": "ThreeSixty",
        "country": "",
        "product_no": record.get("item_no"),
        "product_name_zh": "",
        "product_name_en": record.get("description"),
        "quantity": record.get("quantity"),
        "units_per_carton": record.get("master_carton_qty"),
        "carton_count": _total_cartons(record),
        "standard": _joined(record.get("release_type"), record.get("customer_release")),
        "unit_price_hkd": "",
        "amount_hkd": "",
        "packaging": _joined(
            record.get("container_type"),
            record.get("transportation_mode"),
            record.get("port"),
        ),
        "line_q": record.get("planned_inspection_date"),
        "customer_q": "",
        "requested_ship_date": record.get("factory_commit_date"),
    }


def _issues(record: dict[str, Any], row_id: str) -> list[dict[str, Any]]:
    field_by_message = {
        "未识别合同号": "contract_no",
        "未识别货号": "product_no",
        "未识别数量": "quantity",
        "未识别 FCD": "requested_ship_date",
    }
    issues: list[dict[str, Any]] = []
    for index, message in enumerate(record.get("parse_warnings") or [], start=1):
        field = field_by_message.get(_text(message), "row")
        severity = "warning" if message == "未识别 FCD" else "blocked"
        code = f"missing_{field}" if field != "row" else f"parse_warning_{index}"
        issues.append({
            "severity": severity,
            "code": code,
            "field": field,
            "message": _text(message) or "PO 字段需要人工复核",
            "can_skip": False,
            "skip_key": f"{row_id}:{code}",
            "skip_label": "",
        })
    if not record.get("parse_ok") and not any(
        issue["severity"] == "blocked" for issue in issues
    ):
        issues.append({
            "severity": "blocked",
            "code": "parse_failed",
            "field": "row",
            "message": "PO 关键字段解析失败",
            "can_skip": False,
            "skip_key": f"{row_id}:parse_failed",
            "skip_label": "",
        })
    if record.get("_existing_quantity_conflict"):
        issues.append({
            "severity": "blocked",
            "code": "existing_quantity_conflict",
            "field": "quantity",
            "message": "相同合同及货号已存在排期，但数量不同；按修改/补单阻断",
            "can_skip": False,
            "skip_key": f"{row_id}:existing_quantity_conflict",
            "skip_label": "",
        })
    if record.get("_duplicate_existing"):
        identity = _joined(record.get("contract_no"), record.get("item_no")) or "当前订单"
        issues.append({
            "severity": "blocked",
            "code": "duplicate_existing_order",
            "field": "contract_no",
            "message": f"{identity} 已存在当前华康A 360排期；测试阶段可人工确认后重复导入",
            "can_skip": True,
            "skip_key": f"{row_id}:duplicate_existing_order",
            "skip_label": "测试阶段确认重复导入当前排期已有订单",
        })
    return issues


def _preview_row(
    *,
    spec: HuakangACustomerMappingSpec,
    received_date: str,
    record: dict[str, Any],
    index: int,
    sheet_name: str,
) -> dict[str, Any]:
    row_id = f"huakang-a-360-{index}"
    issues = _issues(record, row_id)
    status = (
        "blocked"
        if any(issue["severity"] == "blocked" for issue in issues)
        else "warning" if issues else "valid"
    )
    source_file = _text(record.get("_source_po_file_name") or record.get("file_name"))
    common: dict[str, Any] = {
        "id": row_id,
        "status": status,
        "status_label": {"valid": "可导出", "warning": "需复核", "blocked": "已阻断"}[status],
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
    for field_name, value in _record_fields(record).items():
        common[field_name] = _text(value)
    common["customer_country"] = _joined(common["customer_name"], common["country"])
    return common


def create_huakang_a_customer_preview(
    *,
    customer_code: str,
    factory_id: str,
    received_date: str,
    po_files: list[tuple[str, bytes]],
    schedule_file_name: str,
    schedule_content: bytes,
) -> dict[str, Any]:
    spec = get_huakang_a_customer_mapping(customer_code)
    if factory_id != "huakang-a":
        raise HuakangACustomerOrderError(
            f"{spec.name} 的这套映射只属于华康A厂区，不能导入其他厂区"
        )
    if not po_files:
        raise HuakangACustomerOrderError("请至少上传一份华康A 360 PO")
    try:
        normalized_received_date = date.fromisoformat(received_date).isoformat()
    except ValueError as exc:
        raise HuakangACustomerOrderError("来单日期必须是 YYYY-MM-DD") from exc

    prepared = _prepare_batch(po_files, schedule_file_name, schedule_content)
    rows = [
        _preview_row(
            spec=spec,
            received_date=normalized_received_date,
            record=record,
            index=index,
            sheet_name=prepared.sheet_name,
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
        "output_file_name": _safe_output_name(schedule_file_name),
        "summary": {
            "total": len(rows),
            "valid": sum(row["status"] == "valid" for row in rows),
            "warning": sum(row["status"] == "warning" for row in rows),
            "blocked": sum(row["status"] == "blocked" for row in rows),
        },
        "rows": rows,
        "warnings": list(dict.fromkeys([
            spec.rule_summary,
            "入单日期沿用 PO 的 Revision Date；来单日期仅作为本次导入追踪日期。",
            "导出结果完整保留当前排期的所有 Sheet、历史数据、格式、公式、图片和打印设置；"
            "仅在“360客排期表”明细末尾/合计行之前插入本批新单，并从插入点向上选择"
            "最近的正常明细行继承格式、字体和公式逻辑，跳过合计/小计、分组标题和空白"
            "分隔行；另存为新文件，不覆盖原排期。",
            *prepared.warnings,
        ])),
    }


def _new_order_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_date": record.get("revision_date"),
        "contract_no": record.get("contract_no"),
        "item_no": record.get("item_no"),
        "description": record.get("description"),
        "quantity": schedule_parser._number(record.get("quantity")),
        "inspection_date": record.get("planned_inspection_date"),
        "fcd": record.get("factory_commit_date"),
        "customer_po": record.get("customer_po"),
        "contact": record.get("contact"),
        "customer_release": record.get("customer_release"),
        "master_carton_qty": schedule_parser._number(record.get("master_carton_qty")),
        "total_cartons": _total_cartons(record),
        "container_type": record.get("container_type"),
        "port": record.get("port"),
        "transportation_mode": record.get("transportation_mode"),
        "source_file": record.get("file_name"),
        "warnings": "；".join(record.get("parse_warnings") or []),
    }


def export_huakang_a_customer_schedule(
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
    preview = create_huakang_a_customer_preview(
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
        raise HuakangACustomerOrderError("确认项已失效，请重新预览后再生成")
    blockers = [
        issue["message"]
        for row in preview["rows"]
        for issue in row["issues"]
        if issue["severity"] == "blocked" and issue["skip_key"] not in requested_skips
    ]
    if blockers:
        raise HuakangACustomerOrderError("仍有阻断项：" + "；".join(dict.fromkeys(blockers)))
    if not preview["rows"]:
        raise HuakangACustomerOrderError("本批文件没有可安全生成的新单明细")

    prepared = _prepare_batch(po_files, schedule_file_name, schedule_content)
    apply_overrides_to_records(
        prepared.records,
        [str(row["id"]) for row in preview["rows"]],
        manual_overrides or [],
        field_aliases={
            "product_no": "item_no",
            "product_name_en": "description",
            "units_per_carton": "master_carton_qty",
            "line_q": "planned_inspection_date",
            "requested_ship_date": "factory_commit_date",
            "po_no": "customer_po",
        },
    )
    records = [_new_order_record(record) for record in prepared.records]
    with TemporaryDirectory(prefix="huakang-a-360-output-") as temp_dir:
        output_path = Path(temp_dir) / preview["output_file_name"]
        try:
            append_records_to_workbook(
                schedule_content,
                output_path,
                records,
                NEW_ORDER_ALIASES,
                filename=schedule_file_name,
                sheet_names=(schedule_parser.SCHEDULE_SHEET,),
            )
        except Exception as exc:
            raise HuakangACustomerOrderError(f"生成华康A 360新单失败：{exc}") from exc
        return output_path.read_bytes(), preview["output_file_name"], preview
