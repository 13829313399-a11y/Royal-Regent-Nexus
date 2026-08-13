from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreviewTypeSpec:
    preview_type: str
    required_permission: str
    allowed_departments: frozenset[str]
    required_assumption_keys: frozenset[str]
    required_assumption_values: tuple[tuple[str, str], ...]
    deterministic_service: bool
    may_create_action_proposal: bool

    def __post_init__(self) -> None:
        if not self.preview_type or "." not in self.preview_type:
            raise ValueError("Preview type is invalid")
        if not self.required_permission or not self.allowed_departments:
            raise ValueError("Preview type requires an IAM contract")
        if not self.required_assumption_keys:
            raise ValueError("Preview type requires assumptions")
        if {
            key for key, _value in self.required_assumption_values
        } != self.required_assumption_keys:
            raise ValueError("Preview assumption values must cover every key")
