from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.injection_schedule_excel import normalize_key


DEFAULT_SCORING_WEIGHTS: dict[str, float] = {
    "due_date": 35.0,
    "sequence_affinity": 15.0,
    "setup_efficiency": 15.0,
    "color_transition": 10.0,
    "load_balance": 10.0,
    "downstream_priority": 10.0,
    "exact_match": 5.0,
    "split_penalty": 12.0,
    "special_handling_penalty": 8.0,
}

DEFAULT_RULE_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "shot_safety_factor": 0.85,
    "default_setup_hours": 1.0,
    "minimum_task_hours": 0.25,
    "allow_missing_data_in_draft_with_manual_confirmation": True,
    "availability_calendar_verified_through": "",
    "color_rank_dark_threshold": 5,
    "scoring_weights": DEFAULT_SCORING_WEIGHTS,
    "color_transition_matrix": [
        {"from_code": "*", "to_code": "*", "minutes": 30.0},
        {"from_code": "light", "to_code": "dark", "minutes": 15.0},
        {"from_code": "dark", "to_code": "light", "minutes": 60.0},
    ],
    "material_transition_matrix": [
        {"from_code": "*", "to_code": "*", "minutes": 45.0},
    ],
    "setup_minutes": [
        {
            "machine_class": "*",
            "same_mold_minutes": 0.0,
            "mold_change_minutes": 60.0,
        }
    ],
    "unavailable_windows": [],
}


def normalize_rule_config(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return a complete, detached rule document without mutating stored JSON."""

    source = value if isinstance(value, dict) else {}
    normalized = deepcopy(DEFAULT_RULE_CONFIG)
    for key in (
        "schema_version",
        "shot_safety_factor",
        "default_setup_hours",
        "minimum_task_hours",
        "allow_missing_data_in_draft_with_manual_confirmation",
        "availability_calendar_verified_through",
        "color_rank_dark_threshold",
    ):
        if key in source:
            normalized[key] = deepcopy(source[key])

    if isinstance(source.get("scoring_weights"), dict):
        normalized["scoring_weights"].update(
            {
                key: deepcopy(raw)
                for key, raw in source["scoring_weights"].items()
                if key in DEFAULT_SCORING_WEIGHTS
            }
        )
    for key in (
        "color_transition_matrix",
        "material_transition_matrix",
        "setup_minutes",
        "unavailable_windows",
    ):
        if isinstance(source.get(key), list):
            normalized[key] = deepcopy(source[key])
    return normalized


def color_code(
    value: str,
    rank: int | None = None,
    *,
    dark_threshold: int = 5,
) -> str:
    if rank is not None:
        return "dark" if rank >= dark_threshold else "light"
    normalized = normalize_key(value)
    if any(
        token in normalized
        for token in (
            "白",
            "透明",
            "浅",
            "米",
            "黄",
            "WHITE",
            "CLEAR",
            "LIGHT",
            "YELLOW",
        )
    ):
        return "light"
    if any(
        token in normalized
        for token in ("黑", "深", "灰", "BLACK", "DARK", "GREY", "GRAY")
    ):
        return "dark"
    return normalized or "unknown"


def canonical_color_key(pigment: str, color: str) -> str:
    """Return the immutable color key used by matrices and task snapshots.

    The workbook/master data exposes both a display color and a pigment/color
    code.  Matrix configuration is code-oriented, so pigment wins whenever it
    is present; display color is the fallback.
    """

    pigment_value = (pigment or "").strip()
    return pigment_value or (color or "").strip()


def transition_minutes(
    rows: list[dict[str, Any]],
    from_value: str,
    to_value: str,
    *,
    from_alias: str = "",
    to_alias: str = "",
) -> tuple[float | None, dict[str, Any]]:
    """Resolve a directed matrix row with exact/alias/wildcard precedence."""

    from_key = normalize_key(from_value)
    to_key = normalize_key(to_value)
    if (
        from_key
        and to_key
        and from_key not in {"UNKNOWN", "未知", "待确认"}
        and to_key not in {"UNKNOWN", "未知", "待确认"}
        and from_key == to_key
    ):
        return 0.0, {
            "match": "same",
            "from_code": from_value,
            "to_code": to_value,
        }

    candidates = [
        (from_key, to_key, "exact"),
        (normalize_key(from_alias), normalize_key(to_alias), "alias"),
        (from_key, "*", "from_wildcard"),
        ("*", to_key, "to_wildcard"),
        ("*", "*", "fallback"),
    ]
    for expected_from, expected_to, match_kind in candidates:
        if not expected_from or not expected_to:
            continue
        for row in rows:
            row_from = normalize_key(str(row.get("from_code", "")))
            row_to = normalize_key(str(row.get("to_code", "")))
            if row_from == expected_from and row_to == expected_to:
                try:
                    minutes = float(row.get("minutes", 0))
                except (TypeError, ValueError):
                    continue
                return minutes, {
                    "match": match_kind,
                    "from_code": row.get("from_code", ""),
                    "to_code": row.get("to_code", ""),
                }
    return None, {
        "match": "missing",
        "from_code": from_value,
        "to_code": to_value,
    }


def setup_row(
    rows: list[dict[str, Any]],
    machine_class: str,
) -> dict[str, Any] | None:
    machine_key = normalize_key(machine_class)
    fallback: dict[str, Any] | None = None
    for row in rows:
        row_key = normalize_key(str(row.get("machine_class", "")))
        if row_key == machine_key and machine_key:
            return row
        if row_key == "*":
            fallback = row
    return fallback


def calculate_transition_setup(
    *,
    from_mold_code: str,
    from_color: str,
    from_color_rank: int | None,
    from_material: str,
    to_mold_code: str,
    to_color: str,
    to_color_rank: int | None,
    to_material: str,
    machine_class: str,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Calculate one directed adjacent-task setup from the Phase 3 matrices."""

    threshold = int(rules.get("color_rank_dark_threshold") or 5)
    color_minutes, color_match = transition_minutes(
        rules["color_transition_matrix"],
        from_color,
        to_color,
        from_alias=color_code(
            from_color,
            from_color_rank,
            dark_threshold=threshold,
        ),
        to_alias=color_code(
            to_color,
            to_color_rank,
            dark_threshold=threshold,
        ),
    )
    material_minutes, material_match = transition_minutes(
        rules["material_transition_matrix"],
        from_material,
        to_material,
    )
    same_mold = _known_rule_value(from_mold_code) and _known_rule_value(
        to_mold_code
    ) and normalize_key(from_mold_code) == normalize_key(to_mold_code)
    machine_setup = setup_row(rules["setup_minutes"], machine_class) or {}
    mold_minutes = float(
        machine_setup.get(
            "same_mold_minutes" if same_mold else "mold_change_minutes",
            0,
        )
    )
    setup_minutes = (
        mold_minutes
        + float(color_minutes or 0)
        + float(material_minutes or 0)
    )
    return {
        "same_mold": same_mold,
        "mold_minutes": round(mold_minutes, 3),
        "color_minutes": color_minutes,
        "material_minutes": material_minutes,
        "setup_minutes": round(setup_minutes, 3),
        "color_matrix_match": str(color_match.get("match", "missing")),
        "material_matrix_match": str(material_match.get("match", "missing")),
    }


def _known_rule_value(value: str) -> bool:
    return normalize_key(value) not in {"", "UNKNOWN", "未知", "待确认"}
