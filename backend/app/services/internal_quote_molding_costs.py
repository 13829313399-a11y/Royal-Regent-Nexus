"""Read-only checks for engineering inputs that still need injection costing."""
import json
from decimal import Decimal, InvalidOperation


def missing_molding_cost_reason(sections):
    by_code = {section.department: section for section in sections}
    engineering = by_code.get("engineering")
    if not engineering or not engineering.is_required or engineering.status == "not_applicable":
        return ""
    payload = json.loads(engineering.payload_json or "{}")
    molds = payload.get("molds", [])
    def positive(value):
        try:
            number = Decimal(str(value))
            return number.is_finite() and number > 0
        except (InvalidOperation, ValueError, TypeError):
            return False
    # Tooling prices alone do not imply injection costs. Plastic weights do.
    has_parts = any(isinstance(mold, dict) and (
        positive(mold.get("net_weight_g")) or any(
            isinstance(part, dict) and positive(part.get("net_weight_g"))
            for part in (mold.get("parts") or [])
        )) for mold in molds)
    if not has_parts:
        return ""
    molding = by_code.get("molding")
    if not molding or not molding.is_required or molding.status == "not_applicable":
        return "工程已有胶件重量，但未参与啤机核价；请确认参与部门并补全啤机核价。目标产能和成品用量保持原值。"
    if molding.calculation_status == "valid" and not any(
        row.get("kind") == "injection"
        for row in json.loads(molding.calculation_json or "{}").get("line_breakdown", [])
        if isinstance(row, dict)
    ):
        return "工程已有胶件重量，但缺少有效的啤机核价明细；请补全并保存后输出。"
    return ""
