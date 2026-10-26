"""Editable defaults from the same unit rules used by warehouse forms."""
import json
import unicodedata
from pathlib import Path

_RULES = json.loads((Path(__file__).resolve().parents[3] / 'shared' / 'materialCategoryUnits.json').read_text(encoding='utf-8'))


def suggest_material_category(unit: str) -> str:
    normalized = unicodedata.normalize('NFKC', unit).strip().lower()
    return next((category for category, units in _RULES.items() if normalized in units), '')
