from hashlib import sha256
import hmac
import json
from urllib.parse import quote as url_quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.customer_order_jobs import run_order_job, order_job_request

from app.core.config import settings
from app.db import get_db
from app.models.customer_order import CustomerOrderExportAudit
from app.schemas.customer_order import CustomerOrderExportAuditOut, CustomerOrderImportPreviewOut
from app.services.auth import AuthContext, get_current_user, now_text
from app.services.business_authz import (
    ensure_permission_for_departments,
    has_permission_for_departments,
)
from app.services.customer_order_buzzbee import (
    CustomerOrderWorkbookError,
    XLSX_CONTENT_TYPE,
    MAX_BATCH_PO_BYTES,
    MAX_BATCH_PO_FILES,
    MAX_PO_BYTES,
    MAX_SCHEDULE_BYTES,
    create_buzzbee_batch_preview,
    create_buzzbee_preview,
    export_buzzbee_batch_schedule,
    export_buzzbee_schedule,
)
from app.services.customer_order_dickie import (
    create_dickie_batch_preview,
    export_dickie_batch_schedule,
)
from app.services.customer_order_caixing import (
    create_caixing_batch_preview,
    export_caixing_batch_schedule,
)
from app.services.customer_order_huaxing import (
    HUAXING_CUSTOMER_MAPPINGS,
    HuaxingCustomerOrderError,
    create_huaxing_customer_preview,
    export_huaxing_customer_schedule,
    get_huaxing_customer_mapping,
)
from app.services.customer_order_huadeng import (
    HUADENG_CUSTOMER_MAPPINGS,
    HuadengCustomerOrderError,
    create_huadeng_customer_preview,
    export_huadeng_customer_schedule,
    get_huadeng_customer_mapping,
)
from app.services.customer_order_huakang_a import (
    HUAKANG_A_CUSTOMER_MAPPINGS,
    HuakangACustomerOrderError,
    create_huakang_a_customer_preview,
    export_huakang_a_customer_schedule,
    get_huakang_a_customer_mapping,
)
from app.services.customer_order_huakang_c import (
    HUAKANG_C_CUSTOMER_MAPPINGS,
    HuakangCCustomerOrderError,
    create_huakang_c_customer_preview,
    export_huakang_c_customer_schedule,
    get_huakang_c_customer_mapping,
)
from app.services.customer_order_manual import (
    MANUAL_EDITABLE_FIELDS,
    coerce_manual_value,
    decorate_manual_resolution_policy,
)
from app.services.customer_order_unified import (
    create_unified_customer_preview,
    export_unified_customer_schedule,
    is_unified_schedule,
)


router = APIRouter(prefix="/api/customer-orders", tags=["customer-orders"], dependencies=[Depends(order_job_request)])
SALES_DEPARTMENTS = ("sales-business",)
XLS_CONTENT_TYPE = "application/vnd.ms-excel"
MAX_SKIPPED_ISSUE_KEYS = MAX_BATCH_PO_FILES * 200
MAX_CONFIRMATION_REASON_LENGTH = 500
MIN_CONFIRMATION_REASON_LENGTH = 4
MAX_MANUAL_OVERRIDES = MAX_BATCH_PO_FILES * 200
MAX_MANUAL_OVERRIDE_VALUE_LENGTH = 500
PREVIEW_FINGERPRINT_VERSION = "customer-order-preview-fingerprint-v1"
TEST_DUPLICATE_ISSUE_CODES = frozenset({
    "duplicate_reference",
    "existing_order_line",
    "duplicate_batch_order_line",
    "duplicate_existing_order",
})
CUSTOMER_FACTORY_IDS = {
    "buzzbee": "huaxing",
    "dickie": "huaxing",
    "caixing": "huaxing",
    **{customer_code: "huaxing" for customer_code in HUAXING_CUSTOMER_MAPPINGS},
    **{customer_code: "huadeng" for customer_code in HUADENG_CUSTOMER_MAPPINGS},
}
for customer_code in HUAKANG_C_CUSTOMER_MAPPINGS:
    CUSTOMER_FACTORY_IDS.setdefault(customer_code, "huakang-c")
CUSTOMER_FACTORY_OPTIONS = {
    customer_code: (factory_id,)
    for customer_code, factory_id in CUSTOMER_FACTORY_IDS.items()
}
for customer_code in HUAKANG_A_CUSTOMER_MAPPINGS:
    existing = CUSTOMER_FACTORY_OPTIONS.get(customer_code, ())
    CUSTOMER_FACTORY_OPTIONS[customer_code] = tuple(dict.fromkeys((*existing, "huakang-a")))
for customer_code in HUAKANG_C_CUSTOMER_MAPPINGS:
    existing = CUSTOMER_FACTORY_OPTIONS.get(customer_code, ())
    CUSTOMER_FACTORY_OPTIONS[customer_code] = tuple(
        dict.fromkeys((*existing, "huakang-c", "huakang-d"))
    )
# Retired entry points are unavailable for new previews/exports. Legacy specs
# and names remain readable for historical compatibility and audit records.
CUSTOMER_FACTORY_OPTIONS.pop("spin-master", None)
CUSTOMER_FACTORY_OPTIONS["jp"] = ("huakang-c",)
CUSTOMER_FACTORY_OPTIONS["disney"] = ("huaxing", "huakang-d")
CUSTOMER_FACTORY_OPTIONS["seasons"] = ("huaxing", "huakang-d")
CUSTOMER_FACTORY_OPTIONS["ubtech"] = ("huakang-d",)
CUSTOMER_NAMES = {
    "ubtech": "优必选",
    "buzzbee": "BuzzBee",
    "dickie": "Dickie",
    "caixing": "彩星",
    **{
        customer_code: spec.name
        for customer_code, spec in HUAXING_CUSTOMER_MAPPINGS.items()
    },
    **{
        customer_code: spec.name
        for customer_code, spec in HUADENG_CUSTOMER_MAPPINGS.items()
    },
    **{
        customer_code: spec.name
        for customer_code, spec in HUAKANG_A_CUSTOMER_MAPPINGS.items()
    },
    **{
        customer_code: spec.name
        for customer_code, spec in HUAKANG_C_CUSTOMER_MAPPINGS.items()
    },
}
FACTORY_NAMES = {
    "huaxing": "华兴",
    "huadeng": "华登",
    "huakang-a": "华康A",
    "huakang-c": "华康C",
    "huakang-d": "华康D",
}


def _ensure_customer_order_permission(
    db: Session,
    current_user: AuthContext,
    permission: str,
    factory_id: str,
) -> None:
    ensure_permission_for_departments(
        db,
        current_user,
        permission,
        factory_id,
        SALES_DEPARTMENTS,
    )


def _ensure_customer_factory(customer_code: str, factory_id: str) -> None:
    expected_factory_ids = CUSTOMER_FACTORY_OPTIONS.get(customer_code)
    if expected_factory_ids is None:
        raise HTTPException(status_code=404, detail=f"不支持的客户映射：{customer_code}")
    if factory_id not in expected_factory_ids:
        customer_name = CUSTOMER_NAMES[customer_code]
        factory_name = " / ".join(
            FACTORY_NAMES.get(expected, expected) for expected in expected_factory_ids
        )
        raise HTTPException(
            status_code=400,
            detail=f"{customer_name} 只属于{factory_name}厂区，不能用于当前厂区",
        )


def _get_mapped_customer_spec(customer_code: str, factory_id: str):
    if customer_code == 'ubtech' and factory_id == 'huakang-d':
        from app.services.customer_order_ubtech import SPEC
        return SPEC
    if customer_code in {"disney", "seasons"} and factory_id == "huakang-d":
        return get_huaxing_customer_mapping(customer_code)
    if factory_id == "huakang-a":
        try:
            return get_huakang_a_customer_mapping(customer_code)
        except HuakangACustomerOrderError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if factory_id in {"huakang-c", "huakang-d"}:
        try:
            return get_huakang_c_customer_mapping(customer_code)
        except HuakangCCustomerOrderError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if customer_code in HUADENG_CUSTOMER_MAPPINGS:
        try:
            return get_huadeng_customer_mapping(customer_code)
        except HuadengCustomerOrderError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return get_huaxing_customer_mapping(customer_code)
    except HuaxingCustomerOrderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _create_mapped_customer_preview(*, customer_code: str, **kwargs):
    return create_unified_customer_preview(customer_code=customer_code, **kwargs)


def _export_mapped_customer_schedule(*, customer_code: str, **kwargs):
    return export_unified_customer_schedule(customer_code=customer_code, **kwargs)


def _create_unified_single_preview(
    *, customer_code: str, po_file_name: str, po_content: bytes, **kwargs,
):
    if not is_unified_schedule(kwargs["schedule_content"]):
        if customer_code == "buzzbee":
            return create_buzzbee_preview(
                po_file_name=po_file_name,
                po_content=po_content,
                **kwargs,
            )
    return create_unified_customer_preview(
        customer_code=customer_code,
        po_files=[(po_file_name, po_content)],
        **kwargs,
    )


def _export_unified_single_schedule(
    *, customer_code: str, po_file_name: str, po_content: bytes, **kwargs,
):
    if not is_unified_schedule(kwargs["schedule_content"]):
        if customer_code == "buzzbee":
            return export_buzzbee_schedule(
                po_file_name=po_file_name,
                po_content=po_content,
                **kwargs,
            )
    return export_unified_customer_schedule(
        customer_code=customer_code,
        po_files=[(po_file_name, po_content)],
        **kwargs,
    )


def _create_special_batch_preview(*, customer_code: str, **kwargs):
    if is_unified_schedule(kwargs["schedule_content"]):
        return create_unified_customer_preview(customer_code=customer_code, **kwargs)
    legacy = {
        "buzzbee": create_buzzbee_batch_preview,
        "dickie": create_dickie_batch_preview,
        "caixing": create_caixing_batch_preview,
    }
    return legacy[customer_code](**kwargs)


def _export_special_batch_schedule(*, customer_code: str, **kwargs):
    if is_unified_schedule(kwargs["schedule_content"]):
        return export_unified_customer_schedule(customer_code=customer_code, **kwargs)
    legacy = {
        "buzzbee": export_buzzbee_batch_schedule,
        "dickie": export_dickie_batch_schedule,
        "caixing": export_caixing_batch_schedule,
    }
    return legacy[customer_code](**kwargs)


def _validate_upload(
    file: UploadFile,
    *,
    kind: str,
    supported: tuple[str, ...] | None = None,
) -> None:
    file_name = file.filename or ""
    if _is_macos_metadata_upload(file_name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{kind} 文件“{file_name}”是 Mac 解压产生的隐藏资源文件，不是真实文件；"
                "请选择同名且不带“._”前缀、并且不在 __MACOSX 目录中的文件"
            ),
        )
    resolved_supported = supported or ((".xls", ".xlsx") if kind == "PO" else (".xlsx",))
    if not file_name.lower().endswith(resolved_supported):
        suffixes = " / ".join(resolved_supported)
        raise HTTPException(status_code=400, detail=f"{kind} 文件只支持 {suffixes}")


def _is_macos_metadata_upload(file_name: str) -> bool:
    normalized = file_name.replace("\\", "/")
    parts = [part.lower() for part in normalized.split("/") if part]
    if not parts:
        return False
    base_name = parts[-1]
    return "__macosx" in parts or base_name.startswith("._") or base_name == ".ds_store"


def _parse_skipped_issue_keys(raw: str) -> set[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="跳过项参数格式无效") from exc
    if (
        not isinstance(value, list)
        or len(value) > MAX_SKIPPED_ISSUE_KEYS
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"确认项参数必须是字符串数组且不超过 {MAX_SKIPPED_ISSUE_KEYS} 项",
        )
    return {item.strip() for item in value}


def _parse_manual_overrides(raw: str) -> list[dict[str, str]]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="人工补录参数格式无效") from exc
    if not isinstance(value, list) or len(value) > MAX_MANUAL_OVERRIDES:
        raise HTTPException(
            status_code=400,
            detail=f"人工补录参数必须是数组且不超过 {MAX_MANUAL_OVERRIDES} 项",
        )
    normalized: list[dict[str, str]] = []
    seen_issue_keys: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="人工补录项格式无效")
        override = {
            key: str(item.get(key) or "").strip()
            for key in ("row_id", "issue_key", "field", "value")
        }
        if not all(override.values()):
            raise HTTPException(status_code=400, detail="人工补录项缺少行、问题、字段或补录值")
        if override["field"] not in MANUAL_EDITABLE_FIELDS:
            raise HTTPException(status_code=400, detail="人工补录字段不受支持")
        if len(override["value"]) > MAX_MANUAL_OVERRIDE_VALUE_LENGTH:
            raise HTTPException(status_code=400, detail="单项人工补录值不能超过 500 个字符")
        if override["issue_key"] in seen_issue_keys:
            raise HTTPException(status_code=400, detail="同一问题不能提交多个人工补录值")
        try:
            coerce_manual_value(override["field"], override["value"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        seen_issue_keys.add(override["issue_key"])
        normalized.append(override)
    return normalized


def _is_test_duplicate_issue_key(issue_key: str) -> bool:
    return any(code in issue_key for code in TEST_DUPLICATE_ISSUE_CODES)


def _ensure_test_duplicate_confirmation_allowed(issue_keys: set[str]) -> None:
    if (
        settings.effective_customer_order_test_duplicate_confirmation_enabled
        or not any(_is_test_duplicate_issue_key(key) for key in issue_keys)
    ):
        return
    raise HTTPException(
        status_code=409,
        detail="当前环境未启用测试阶段重复订单确认；请移除重复订单后重新解析",
    )


def _has_duplicate_confirmation_permission(
    current_user: AuthContext,
    factory_id: str,
) -> bool:
    return has_permission_for_departments(
        current_user,
        "customer_order:duplicate_confirm",
        factory_id,
        SALES_DEPARTMENTS,
    )


def _apply_customer_order_confirmation_policy(
    preview: dict,
    *,
    duplicate_confirmation_authorized: bool = True,
) -> dict:
    enabled = settings.effective_customer_order_test_duplicate_confirmation_enabled
    preview["duplicate_confirmation_enabled"] = enabled
    preview["duplicate_confirmation_authorized"] = duplicate_confirmation_authorized
    confirmation_allowed = enabled and duplicate_confirmation_authorized
    confirmation_rows = 0

    for row in preview.get("rows", []):
        issues = row.get("issues", [])
        duplicate_issues = [
            issue for issue in issues
            if issue.get("code") in TEST_DUPLICATE_ISSUE_CODES
        ]
        if not duplicate_issues:
            continue

        if confirmation_allowed:
            for issue in duplicate_issues:
                if issue.get("can_skip"):
                    issue["severity"] = "confirmation"
            if any(issue.get("severity") == "confirmation" for issue in issues):
                confirmation_rows += 1
                if not any(issue.get("severity") == "blocked" for issue in issues):
                    row["status"] = "warning"
                    row["status_label"] = "待确认"
        else:
            for issue in duplicate_issues:
                issue["severity"] = "blocked"
                issue["can_skip"] = False
                issue["skip_label"] = ""
                message = str(issue.get("message") or "").rstrip("；。")
                reason = (
                    "当前环境未启用重复订单确认"
                    if not enabled
                    else "当前账号没有重复订单确认权限"
                )
                issue["message"] = f"{message}；{reason}"
            row["status"] = "blocked"
            row["status_label"] = "阻断"

    rows = preview.get("rows", [])
    preview["confirmation_count"] = confirmation_rows if confirmation_allowed else 0
    summary = preview.setdefault("summary", {})
    summary.update({
        "total": len(rows),
        "valid": sum(row.get("status") == "valid" for row in rows),
        "warning": sum(row.get("status") == "warning" for row in rows),
        "blocked": sum(row.get("status") == "blocked" for row in rows),
    })
    return decorate_manual_resolution_policy(preview)


def _preview_fingerprint(preview: dict, received_date: str) -> str:
    identity = {
        "fingerprint_version": PREVIEW_FINGERPRINT_VERSION,
        "preview_schema_version": preview.get("preview_schema_version", ""),
        "customer_code": preview.get("customer_code", ""),
        "factory_id": preview.get("factory_id", ""),
        "received_date": received_date.strip(),
        "po_file_names": preview.get("po_file_names", []),
        "source_po_sha256s": preview.get("source_po_sha256s", []),
        "schedule_file_name": preview.get("schedule_file_name", ""),
        "source_schedule_sha256": preview.get("source_schedule_sha256", ""),
        "input_template": preview.get("input_template", ""),
        "target_template": preview.get("target_template", ""),
        "output_file_name": preview.get("output_file_name", ""),
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _finalize_preview(
    preview: dict,
    *,
    received_date: str,
    current_user: AuthContext,
    factory_id: str,
) -> dict:
    finalized = _apply_customer_order_confirmation_policy(
        preview,
        duplicate_confirmation_authorized=_has_duplicate_confirmation_permission(
            current_user,
            factory_id,
        ),
    )
    finalized["preview_fingerprint"] = _preview_fingerprint(finalized, received_date)
    return finalized


def _validated_confirmation_reason(issue_keys: set[str], raw_reason: str) -> str:
    reason = raw_reason.strip()
    if not issue_keys:
        return ""
    if len(reason) < MIN_CONFIRMATION_REASON_LENGTH:
        raise HTTPException(status_code=400, detail="存在人工确认或跳过项时，请填写至少 4 个字的确认原因")
    if len(reason) > MAX_CONFIRMATION_REASON_LENGTH:
        raise HTTPException(status_code=400, detail="确认原因不能超过 500 个字符")
    return reason


def _prepare_export_confirmation(
    db: Session,
    current_user: AuthContext,
    factory_id: str,
    issue_keys: set[str],
    raw_reason: str,
) -> str:
    _ensure_test_duplicate_confirmation_allowed(issue_keys)
    if any(_is_test_duplicate_issue_key(key) for key in issue_keys):
        _ensure_customer_order_permission(
            db,
            current_user,
            "customer_order:duplicate_confirm",
            factory_id,
        )
    return _validated_confirmation_reason(issue_keys, raw_reason)


def _actual_confirmed_issue_keys(preview: dict, requested_keys: set[str]) -> set[str]:
    decorate_manual_resolution_policy(preview)
    available_keys = {
        str(issue.get("skip_key") or "")
        for row in preview.get("rows", [])
        for issue in row.get("issues", [])
        if issue.get("can_skip") and issue.get("skip_key")
    }
    actual = requested_keys & available_keys
    unknown = requested_keys - available_keys
    if unknown:
        raise HTTPException(
            status_code=409,
            detail="预览中的确认项已经变化，请重新解析并确认当前批次",
        )
    return actual


def _actual_manual_overrides(
    preview: dict,
    requested_overrides: list[dict[str, str]],
) -> list[dict[str, str]]:
    decorate_manual_resolution_policy(preview)
    available = {
        (str(row.get("id") or ""), str(issue.get("skip_key") or "")): issue
        for row in preview.get("rows", [])
        for issue in row.get("issues", [])
        if issue.get("can_edit") and issue.get("skip_key")
    }
    for override in requested_overrides:
        issue = available.get((override["row_id"], override["issue_key"]))
        if issue is None or issue.get("edit_field") != override["field"]:
            raise HTTPException(
                status_code=409,
                detail="预览中的可补录项已经变化，请重新解析并填写当前批次",
            )
    return requested_overrides


def _ensure_preview_fingerprint(
    preview: dict,
    received_date: str,
    submitted_fingerprint: str,
) -> str:
    expected = _preview_fingerprint(preview, received_date)
    submitted = submitted_fingerprint.strip()
    if not submitted or not hmac.compare_digest(expected, submitted):
        raise HTTPException(
            status_code=409,
            detail="PO、客户排期或来单日期已与预览不一致，请重新解析后再生成",
        )
    return expected


def _record_export_audit(
    db: Session,
    current_user: AuthContext,
    *,
    preview: dict,
    received_date: str,
    preview_fingerprint: str,
    actual_issue_keys: set[str],
    manual_overrides: list[dict[str, str]],
    confirmation_reason: str,
    output: bytes,
    file_name: str,
) -> CustomerOrderExportAudit:
    audit = CustomerOrderExportAudit(
        id=f"customer-order-export-{uuid4().hex}",
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        actor_display_name=current_user.display_name,
        factory_id=str(preview.get("factory_id") or ""),
        customer_code=str(preview.get("customer_code") or ""),
        received_date=received_date.strip(),
        preview_schema_version=str(preview.get("preview_schema_version") or ""),
        preview_fingerprint=preview_fingerprint,
        po_file_names_json=json.dumps(preview.get("po_file_names", []), ensure_ascii=False),
        source_po_sha256s_json=json.dumps(preview.get("source_po_sha256s", [])),
        schedule_file_name=str(preview.get("schedule_file_name") or ""),
        source_schedule_sha256=str(preview.get("source_schedule_sha256") or ""),
        output_file_name=file_name,
        output_sha256=sha256(output).hexdigest(),
        output_template=str(preview.get("target_template") or ""),
        confirmed_issue_keys_json=json.dumps(sorted(actual_issue_keys), ensure_ascii=False),
        confirmed_issue_count=len(actual_issue_keys),
        manual_overrides_json=json.dumps(manual_overrides, ensure_ascii=False),
        manual_override_count=len(manual_overrides),
        confirmation_reason=confirmation_reason,
        created_at=now_text(),
    )
    db.add(audit)
    db.commit()
    return audit


def _complete_export_control(
    db: Session,
    current_user: AuthContext,
    *,
    preview: dict,
    received_date: str,
    submitted_fingerprint: str,
    requested_issue_keys: set[str],
    requested_manual_overrides: list[dict[str, str]],
    confirmation_reason: str,
    output: bytes,
    file_name: str,
) -> tuple[set[str], CustomerOrderExportAudit]:
    validated_fingerprint = _ensure_preview_fingerprint(
        preview,
        received_date,
        submitted_fingerprint,
    )
    actual_issue_keys = _actual_confirmed_issue_keys(preview, requested_issue_keys)
    actual_manual_overrides = _actual_manual_overrides(
        preview,
        requested_manual_overrides,
    )
    audit = _record_export_audit(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        preview_fingerprint=validated_fingerprint,
        actual_issue_keys=actual_issue_keys,
        manual_overrides=actual_manual_overrides,
        confirmation_reason=confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return actual_issue_keys, audit


def _audit_out(audit: CustomerOrderExportAudit) -> CustomerOrderExportAuditOut:
    return CustomerOrderExportAuditOut(
        id=audit.id,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        actor_display_name=audit.actor_display_name,
        factory_id=audit.factory_id,
        customer_code=audit.customer_code,
        received_date=audit.received_date,
        preview_schema_version=audit.preview_schema_version,
        preview_fingerprint=audit.preview_fingerprint,
        po_file_names=json.loads(audit.po_file_names_json or "[]"),
        source_po_sha256s=json.loads(audit.source_po_sha256s_json or "[]"),
        schedule_file_name=audit.schedule_file_name,
        source_schedule_sha256=audit.source_schedule_sha256,
        output_file_name=audit.output_file_name,
        output_sha256=audit.output_sha256,
        output_template=audit.output_template,
        confirmed_issue_keys=json.loads(audit.confirmed_issue_keys_json or "[]"),
        confirmed_issue_count=audit.confirmed_issue_count,
        manual_overrides=json.loads(audit.manual_overrides_json or "[]"),
        manual_override_count=audit.manual_override_count,
        confirmation_reason=audit.confirmation_reason,
        created_at=audit.created_at,
    )


async def _read_po_uploads(
    po_files: list[UploadFile],
    *,
    supported: tuple[str, ...] = (".xls", ".xlsx"),
) -> list[tuple[str, bytes]]:
    if not po_files:
        raise HTTPException(status_code=400, detail="请至少上传一份 PO 文件")
    usable_po_files = [
        po_file
        for po_file in po_files
        if not _is_macos_metadata_upload(po_file.filename or "")
    ]
    if not usable_po_files:
        first_name = po_files[0].filename or "未命名文件"
        raise HTTPException(
            status_code=400,
            detail=(
                f"PO 文件“{first_name}”是 Mac 解压产生的隐藏资源文件，不是真实 PO；"
                "请选择同名且不带“._”前缀、并且不在 __MACOSX 目录中的文件"
            ),
        )
    if len(usable_po_files) > MAX_BATCH_PO_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"单批最多上传 {MAX_BATCH_PO_FILES} 份 PO 文件",
        )
    uploaded: list[tuple[str, bytes]] = []
    total_size = 0
    for po_file in usable_po_files:
        _validate_upload(po_file, kind="PO", supported=supported)
        content = await po_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="PO 文件不能为空")
        if len(content) > MAX_PO_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"PO 文件超过 12MB 限制：{po_file.filename or '未命名文件'}",
            )
        total_size += len(content)
        if total_size > MAX_BATCH_PO_BYTES:
            raise HTTPException(status_code=400, detail="本批 PO 文件合计超过 80MB 限制")
        uploaded.append((po_file.filename or "", content))
    return uploaded


@router.post(
    "/buzzbee/preview",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_buzzbee_customer_order(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_file: UploadFile = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("buzzbee", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(po_file, kind="PO")
    _validate_upload(schedule_file, kind="客户排期")
    po_content = await po_file.read()
    schedule_content = await schedule_file.read()
    if not po_content or not schedule_content:
        raise HTTPException(status_code=400, detail="PO 和客户排期文件都不能为空")
    try:
        preview = await run_order_job(
            _create_unified_single_preview,
            db=db,
            customer_code="buzzbee",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_file_name=po_file.filename or "",
            po_content=po_content,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
        return _finalize_preview(
            preview,
            received_date=received_date,
            current_user=current_user,
            factory_id=normalized_factory_id,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/buzzbee/preview-batch",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_buzzbee_customer_order_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("buzzbee", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files)
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        preview = await run_order_job(
            _create_special_batch_preview,
            db=db,
            customer_code="buzzbee",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
        return _finalize_preview(
            preview,
            received_date=received_date,
            current_user=current_user,
            factory_id=normalized_factory_id,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/buzzbee/export")
async def export_buzzbee_customer_schedule(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(""),
    confirmation_reason: str = Form(""),
    po_file: UploadFile = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("buzzbee", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    normalized_manual_overrides = _parse_manual_overrides(manual_overrides)
    normalized_resolution_keys = normalized_skipped_issue_keys | {
        item["issue_key"] for item in normalized_manual_overrides
    }
    normalized_confirmation_reason = _prepare_export_confirmation(
        db,
        current_user,
        normalized_factory_id,
        normalized_resolution_keys,
        confirmation_reason,
    )
    _validate_upload(po_file, kind="PO")
    _validate_upload(schedule_file, kind="客户排期")
    po_content = await po_file.read()
    schedule_content = await schedule_file.read()
    if not po_content or not schedule_content:
        raise HTTPException(status_code=400, detail="PO 和客户排期文件都不能为空")
    try:
        output, file_name, preview = await run_order_job(
            _export_unified_single_schedule,
            db=db,
            customer_code="buzzbee",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_file_name=po_file.filename or "",
            po_content=po_content,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_resolution_keys,
            manual_overrides=normalized_manual_overrides,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_issue_keys, audit = _complete_export_control(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        submitted_fingerprint=preview_fingerprint,
        requested_issue_keys=normalized_resolution_keys,
        requested_manual_overrides=normalized_manual_overrides,
        confirmation_reason=normalized_confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": (
                "true" if preview.get("_schedule_encrypted") or output.startswith(b"\xd0\xcf\x11\xe0") else "false"
            ),
            "X-Skipped-Issue-Count": str(len(actual_issue_keys)),
            "X-Content-SHA256": audit.output_sha256,
            "X-Preview-Fingerprint": audit.preview_fingerprint,
            "X-Export-Audit-ID": audit.id,
        },
    )


@router.post("/buzzbee/export-batch")
async def export_buzzbee_customer_schedule_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(""),
    confirmation_reason: str = Form(""),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("buzzbee", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    normalized_manual_overrides = _parse_manual_overrides(manual_overrides)
    normalized_resolution_keys = normalized_skipped_issue_keys | {
        item["issue_key"] for item in normalized_manual_overrides
    }
    normalized_confirmation_reason = _prepare_export_confirmation(
        db,
        current_user,
        normalized_factory_id,
        normalized_resolution_keys,
        confirmation_reason,
    )
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files)
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        output, file_name, preview = await run_order_job(
            _export_special_batch_schedule,
            db=db,
            customer_code="buzzbee",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_resolution_keys,
            manual_overrides=normalized_manual_overrides,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_issue_keys, audit = _complete_export_control(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        submitted_fingerprint=preview_fingerprint,
        requested_issue_keys=normalized_resolution_keys,
        requested_manual_overrides=normalized_manual_overrides,
        confirmation_reason=normalized_confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": (
                "true" if preview.get("_schedule_encrypted") or output.startswith(b"\xd0\xcf\x11\xe0") else "false"
            ),
            "X-PO-File-Count": str(preview["po_file_count"]),
            "X-Skipped-Issue-Count": str(len(actual_issue_keys)),
            "X-Content-SHA256": audit.output_sha256,
            "X-Preview-Fingerprint": audit.preview_fingerprint,
            "X-Export-Audit-ID": audit.id,
        },
    )


@router.post(
    "/dickie/preview-batch",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_dickie_customer_order_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("dickie", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files, supported=(".pdf",))
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        preview = await run_order_job(
            _create_special_batch_preview,
            db=db,
            customer_code="dickie",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
        return _finalize_preview(
            preview,
            received_date=received_date,
            current_user=current_user,
            factory_id=normalized_factory_id,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/dickie/export-batch")
async def export_dickie_customer_schedule_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(""),
    confirmation_reason: str = Form(""),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("dickie", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    normalized_manual_overrides = _parse_manual_overrides(manual_overrides)
    normalized_resolution_keys = normalized_skipped_issue_keys | {
        item["issue_key"] for item in normalized_manual_overrides
    }
    normalized_confirmation_reason = _prepare_export_confirmation(
        db,
        current_user,
        normalized_factory_id,
        normalized_resolution_keys,
        confirmation_reason,
    )
    _validate_upload(schedule_file, kind="客户排期")
    uploaded_po_files = await _read_po_uploads(po_files, supported=(".pdf",))
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        output, file_name, preview = await run_order_job(
            _export_special_batch_schedule,
            db=db,
            customer_code="dickie",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_resolution_keys,
            manual_overrides=normalized_manual_overrides,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_issue_keys, audit = _complete_export_control(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        submitted_fingerprint=preview_fingerprint,
        requested_issue_keys=normalized_resolution_keys,
        requested_manual_overrides=normalized_manual_overrides,
        confirmation_reason=normalized_confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": (
                "true" if preview.get("_schedule_encrypted") or output.startswith(b"\xd0\xcf\x11\xe0") else "false"
            ),
            "X-PO-File-Count": str(preview["po_file_count"]),
            "X-Skipped-Issue-Count": str(len(actual_issue_keys)),
            "X-Content-SHA256": audit.output_sha256,
            "X-Preview-Fingerprint": audit.preview_fingerprint,
            "X-Export-Audit-ID": audit.id,
        },
    )


@router.post(
    "/caixing/preview-batch",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_caixing_customer_order_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("caixing", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(
        schedule_file,
        kind="客户排期",
        supported=(".xlsx",),
    )
    uploaded_po_files = await _read_po_uploads(po_files, supported=(".pdf",))
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        preview = await run_order_job(
            _create_special_batch_preview,
            db=db,
            customer_code="caixing",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
        return _finalize_preview(
            preview,
            received_date=received_date,
            current_user=current_user,
            factory_id=normalized_factory_id,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/caixing/export-batch")
async def export_caixing_customer_schedule_batch(
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(""),
    confirmation_reason: str = Form(""),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory("caixing", normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    normalized_manual_overrides = _parse_manual_overrides(manual_overrides)
    normalized_resolution_keys = normalized_skipped_issue_keys | {
        item["issue_key"] for item in normalized_manual_overrides
    }
    normalized_confirmation_reason = _prepare_export_confirmation(
        db,
        current_user,
        normalized_factory_id,
        normalized_resolution_keys,
        confirmation_reason,
    )
    _validate_upload(
        schedule_file,
        kind="客户排期",
        supported=(".xlsx",),
    )
    uploaded_po_files = await _read_po_uploads(po_files, supported=(".pdf",))
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    try:
        output, file_name, preview = await run_order_job(
            _export_special_batch_schedule,
            db=db,
            customer_code="caixing",
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_resolution_keys,
            manual_overrides=normalized_manual_overrides,
        )
    except CustomerOrderWorkbookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_issue_keys, audit = _complete_export_control(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        submitted_fingerprint=preview_fingerprint,
        requested_issue_keys=normalized_resolution_keys,
        requested_manual_overrides=normalized_manual_overrides,
        confirmation_reason=normalized_confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return Response(
        content=output,
        media_type=(
            XLS_CONTENT_TYPE
            if file_name.lower().endswith(".xls")
            else XLSX_CONTENT_TYPE
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": (
                "true" if preview.get("_schedule_encrypted") else "false"
            ),
            "X-PO-File-Count": str(preview["po_file_count"]),
            "X-Skipped-Issue-Count": str(len(actual_issue_keys)),
            "X-Content-SHA256": audit.output_sha256,
            "X-Preview-Fingerprint": audit.preview_fingerprint,
            "X-Export-Audit-ID": audit.id,
        },
    )


@router.get("/audits", response_model=list[CustomerOrderExportAuditOut])
def list_customer_order_export_audits(
    factory_id: str = "huaxing",
    customer_code: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:audit_read",
        normalized_factory_id,
    )
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="审计记录查询数量必须在 1 到 200 之间")
    query = select(CustomerOrderExportAudit).where(
        CustomerOrderExportAudit.factory_id == normalized_factory_id
    )
    normalized_customer_code = customer_code.strip()
    if normalized_customer_code:
        query = query.where(
            CustomerOrderExportAudit.customer_code == normalized_customer_code
        )
    query = query.order_by(
        CustomerOrderExportAudit.created_at.desc(),
        CustomerOrderExportAudit.id.desc(),
    ).limit(limit)
    return [_audit_out(audit) for audit in db.scalars(query).all()]


@router.post(
    "/{customer_code}/preview-batch",
    response_model=CustomerOrderImportPreviewOut,
)
async def preview_mapped_customer_order_batch(
    customer_code: str,
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory(customer_code, normalized_factory_id)
    spec = _get_mapped_customer_spec(customer_code, normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:read",
        normalized_factory_id,
    )
    _validate_upload(
        schedule_file,
        kind="客户排期",
        supported=(".xlsx",),
    )
    uploaded_po_files = await _read_po_uploads(
        po_files,
        supported=spec.po_extensions,
    )
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    if len(schedule_content) > MAX_SCHEDULE_BYTES:
        raise HTTPException(status_code=400, detail="客户排期文件超过 35MB 限制")
    try:
        preview = await run_order_job(
            _create_mapped_customer_preview,
            db=db,
            customer_code=customer_code,
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
        )
        return _finalize_preview(
            preview,
            received_date=received_date,
            current_user=current_user,
            factory_id=normalized_factory_id,
        )
    except (
        HuaxingCustomerOrderError,
        HuadengCustomerOrderError,
        HuakangACustomerOrderError,
        HuakangCCustomerOrderError,
        CustomerOrderWorkbookError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{customer_code}/export-batch")
async def export_mapped_customer_order_batch(
    customer_code: str,
    factory_id: str = Form("huaxing"),
    received_date: str = Form(...),
    confirmed: bool = Form(...),
    skipped_issue_keys: str = Form("[]"),
    manual_overrides: str = Form("[]"),
    preview_fingerprint: str = Form(""),
    confirmation_reason: str = Form(""),
    po_files: list[UploadFile] = File(...),
    schedule_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_factory_id = factory_id.strip() or "huaxing"
    _ensure_customer_factory(customer_code, normalized_factory_id)
    spec = _get_mapped_customer_spec(customer_code, normalized_factory_id)
    _ensure_customer_order_permission(
        db,
        current_user,
        "customer_order:export",
        normalized_factory_id,
    )
    if not confirmed:
        raise HTTPException(status_code=400, detail="请先完成预览并确认当前批次")
    normalized_skipped_issue_keys = _parse_skipped_issue_keys(skipped_issue_keys)
    normalized_manual_overrides = _parse_manual_overrides(manual_overrides)
    normalized_resolution_keys = normalized_skipped_issue_keys | {
        item["issue_key"] for item in normalized_manual_overrides
    }
    normalized_confirmation_reason = _prepare_export_confirmation(
        db,
        current_user,
        normalized_factory_id,
        normalized_resolution_keys,
        confirmation_reason,
    )
    _validate_upload(
        schedule_file,
        kind="客户排期",
        supported=(".xlsx",),
    )
    uploaded_po_files = await _read_po_uploads(
        po_files,
        supported=spec.po_extensions,
    )
    schedule_content = await schedule_file.read()
    if not schedule_content:
        raise HTTPException(status_code=400, detail="客户排期文件不能为空")
    if len(schedule_content) > MAX_SCHEDULE_BYTES:
        raise HTTPException(status_code=400, detail="客户排期文件超过 35MB 限制")
    try:
        output, file_name, preview = await run_order_job(
            _export_mapped_customer_schedule,
            db=db,
            customer_code=customer_code,
            factory_id=normalized_factory_id,
            received_date=received_date,
            po_files=uploaded_po_files,
            schedule_file_name=schedule_file.filename or "",
            schedule_content=schedule_content,
            skipped_issue_keys=normalized_resolution_keys,
            manual_overrides=normalized_manual_overrides,
        )
    except (
        HuaxingCustomerOrderError,
        HuadengCustomerOrderError,
        HuakangACustomerOrderError,
        HuakangCCustomerOrderError,
        CustomerOrderWorkbookError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    actual_issue_keys, audit = _complete_export_control(
        db,
        current_user,
        preview=preview,
        received_date=received_date,
        submitted_fingerprint=preview_fingerprint,
        requested_issue_keys=normalized_resolution_keys,
        requested_manual_overrides=normalized_manual_overrides,
        confirmation_reason=normalized_confirmation_reason,
        output=output,
        file_name=file_name,
    )
    return Response(
        content=output,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "X-Output-Template": preview["target_template"],
            "X-Workbook-Password-Required": (
                "true" if preview.get("_schedule_encrypted") else "false"
            ),
            "X-PO-File-Count": str(preview["po_file_count"]),
            "X-Skipped-Issue-Count": str(len(actual_issue_keys)),
            "X-Content-SHA256": audit.output_sha256,
            "X-Preview-Fingerprint": audit.preview_fingerprint,
            "X-Export-Audit-ID": audit.id,
        },
    )
