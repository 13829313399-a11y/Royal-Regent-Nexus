from __future__ import annotations

from app.services.auth import ALLOWED_FACTORY_IDS

from .contracts import PdfRenameRule, PdfRenameServiceError
from .rules import CATALOG_RULES


_RULES: dict[str, PdfRenameRule] = {
    rule.definition.rule_id: rule for rule in CATALOG_RULES
}


def _validate_factory(factory_id: str) -> str:
    normalized = factory_id.strip().lower()
    if normalized not in ALLOWED_FACTORY_IDS:
        raise PdfRenameServiceError(
            "PDF_RENAME_FACTORY_INVALID",
            "请选择有效的生产厂区。",
            action="请切换到对应厂区后重新选择改名规则。",
            status_code=400,
        )
    return normalized


def list_pdf_rename_rules(factory_id: str) -> tuple[dict[str, object], ...]:
    factory_id = _validate_factory(factory_id)
    if factory_id != "huaxing":
        return ()
    return tuple(
        rule.definition.as_dict()
        for rule in sorted(_RULES.values(), key=lambda item: item.definition.label)
        if not rule.definition.factory_ids or factory_id in rule.definition.factory_ids
    )


def get_pdf_rename_rule(rule_id: str, factory_id: str) -> PdfRenameRule:
    factory_id = _validate_factory(factory_id)
    if factory_id != "huaxing":
        raise PdfRenameServiceError(
            "PDF_RENAME_RULE_FACTORY_MISMATCH",
            "批量改名工具仅供华兴厂区使用。",
            action="请切换到华兴厂区后使用。",
            status_code=403,
        )
    normalized = rule_id.strip()
    rule = _RULES.get(normalized)
    if rule is None:
        raise PdfRenameServiceError(
            "PDF_RENAME_RULE_NOT_FOUND",
            "所选批量改名规则不存在。",
            action="请刷新规则列表后重新选择。",
            status_code=404,
        )
    if rule.definition.factory_ids and factory_id not in rule.definition.factory_ids:
        raise PdfRenameServiceError(
            "PDF_RENAME_RULE_FACTORY_MISMATCH",
            "所选改名规则不适用于当前厂区。",
            action="请使用当前厂区的改名规则，或切换到规则所属厂区。",
            status_code=403,
        )
    if not rule.definition.available:
        raise PdfRenameServiceError(
            "PDF_RENAME_RULE_NOT_READY",
            "所选规则仍在收集配置，暂不能处理文件。",
            action="请先补齐规则页码、固定区域、区间名格式和验收样例。",
            status_code=409,
        )
    return rule
