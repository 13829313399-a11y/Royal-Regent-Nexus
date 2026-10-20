"""Display-only legacy dimensions and strict unit-marked unordered identity."""
import re

_UNIT_SUFFIX = re.compile(r"\s*(?:\[(cm|in|inch|inches|mm|ft|m)\]|(cm|inches|inch|in|mm|ft|m|英寸|英吋|厘米|公分|毫米|″|\"))$", re.IGNORECASE)
_ALIASES = {"inch": "in", "inches": "in", "英寸": "in", "英吋": "in", "″": "in", '"': "in", "厘米": "cm", "公分": "cm", "毫米": "mm"}


def specification_unit(specification: str | None) -> tuple[str | None, str]:
    text = (specification or "").strip()
    match = _UNIT_SUFFIX.search(text)
    if not match or (match.start() > 0 and match.group(0)[0].isalpha() and text[match.start() - 1].isalpha()):
        return None, text
    unit = (match.group(1) or match.group(2)).lower()
    return _ALIASES.get(unit, unit), text[:match.start()].strip()


def dimension_unit_for_display(unit: str | None, specification: str | None) -> str:
    explicit = (unit or "").strip().lower()
    return _ALIASES.get(explicit, explicit) if explicit else (specification_unit(specification)[0] or "cm")


def specification_for_display(specification: str | None, unit: str | None) -> str:
    _, base = specification_unit(specification)
    return f"{base} {dimension_unit_for_display(unit, specification)}".strip()
