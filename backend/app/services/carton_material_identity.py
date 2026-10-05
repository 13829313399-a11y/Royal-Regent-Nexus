"""Shared material identity checks for vendor evidence and formal carton papers."""
import re
from decimal import Decimal, InvalidOperation


def text_identity(value):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(value or "").strip().casefold())


def dimension_identity(value):
    numbers = re.findall(r"\d+(?:[.,]\d+)?", str(value or ""))
    if len(numbers) not in {2, 3}:
        return ()
    try:
        return tuple(str(Decimal(number.replace(",", ".")).normalize()) for number in numbers)
    except InvalidOperation:
        return ()


def dimension_unit(value):
    found = re.search(r"(inches|inch|in|英寸|cm|厘米|mm|毫米)\s*$", str(value or ""), re.I)
    if not found:
        return ""
    unit = found.group(1).casefold()
    return "inch" if unit in {"inches", "inch", "in", "英寸"} else "mm" if unit in {"mm", "毫米"} else "cm"


def material_conflicts(source, target):
    """Missing/generic identifiers may be completed; explicit conflicts never match."""
    conflicts = []
    for key, label in (("packaging_type", "纸品类型"), ("paper_quality", "纸质")):
        value = str(source.get(key) or "").strip()
        missing = {"", "待复核"}
        if key == "packaging_type" and source.get("packaging_type_explicit") is False:
            value = ""  # Parser defaults are not evidence that the vendor specified a type.
        if value not in missing and text_identity(value) != text_identity(target.get(key)):
            conflicts.append(label)
    source_spec = str(source.get("specification") or "").strip()
    if source_spec and source_spec != "待复核":
        dimensions = dimension_identity(source_spec)
        matches = (dimensions == dimension_identity(target.get("specification")) if dimensions
                   else text_identity(source_spec) == text_identity(target.get("specification")))
        if not matches:
            conflicts.append("规格")
        declared_source = dimension_unit(source.get("dimension_unit"))
        embedded_source = dimension_unit(source_spec)
        declared_target = dimension_unit(target.get("dimension_unit"))
        embedded_target = dimension_unit(target.get("specification"))
        source_unit = declared_source or embedded_source
        target_unit = declared_target or embedded_target or "cm"
        if (declared_source and embedded_source and declared_source != embedded_source) or (declared_target and embedded_target and declared_target != embedded_target):
            conflicts.append("尺寸单位")
        if source_unit and source_unit != target_unit:
            if "尺寸单位" not in conflicts:
                conflicts.append("尺寸单位")
    return conflicts
