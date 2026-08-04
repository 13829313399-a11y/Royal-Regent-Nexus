from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.injection_scheduling import InjectionSchedulingMold
from app.services.injection_scheduling_scheduler.normalization import color_rank


@dataclass(frozen=True, slots=True)
class TransitionImpact:
    setup_minutes: int
    mold_change_minutes: int
    material_change_minutes: int
    color_change_minutes: int
    dark_to_light: bool
    changeover_type: str


def transition_impact(
    previous: InjectionSchedulingMold | None,
    current: InjectionSchedulingMold,
    config: dict[str, Any],
) -> TransitionImpact:
    if previous is None:
        return TransitionImpact(0, 0, 0, 0, False, "INITIAL")
    previous_rank = color_rank(previous.color_profile, config.get("color_scale"))
    current_rank = color_rank(current.color_profile, config.get("color_scale"))
    configured_rule = next(
        (
            item
            for item in config.get("transition_rules", [])
            if item.get("from_material_group", "") in {"", previous.material_code}
            and item.get("to_material_group", "") in {"", current.material_code}
            and int(item.get("from_color_rank", previous_rank)) == previous_rank
            and int(item.get("to_color_rank", current_rank)) == current_rank
        ),
        None,
    )
    mold_change = (
        0
        if previous.id == current.id
        else int(
            (configured_rule or {}).get(
                "mold_change_minutes", config.get("mold_change_minutes", 30)
            )
        )
    )
    material_change = (
        0
        if previous.material_code == current.material_code
        else int(
            (configured_rule or {}).get(
                "material_change_minutes", config.get("material_change_minutes", 20)
            )
        )
    )
    dark_to_light = previous_rank > current_rank
    color_change = 0
    if previous.color_profile != current.color_profile:
        color_change = int(
            (configured_rule or {}).get(
                "color_change_minutes",
                config.get(
                    "dark_to_light_minutes"
                    if dark_to_light
                    else "color_change_minutes",
                    60 if dark_to_light else 10,
                ),
            )
        )
    setup = mold_change + material_change + color_change
    labels = []
    if mold_change:
        labels.append("MOLD")
    if material_change:
        labels.append("MATERIAL")
    if color_change:
        labels.append("DARK_TO_LIGHT" if dark_to_light else "COLOR")
    return TransitionImpact(
        setup_minutes=setup,
        mold_change_minutes=mold_change,
        material_change_minutes=material_change,
        color_change_minutes=color_change,
        dark_to_light=dark_to_light,
        changeover_type="+".join(labels) or "SAME_SETUP",
    )
