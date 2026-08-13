from __future__ import annotations

from collections.abc import Iterable

from app.services.ai.previews.contracts import PreviewTypeSpec
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS


class PreviewRegistryError(ValueError):
    pass


class PreviewRegistry:
    def __init__(self, specs: Iterable[PreviewTypeSpec]) -> None:
        items = tuple(specs)
        by_type = {item.preview_type: item for item in items}
        if len(items) != len(by_type):
            raise PreviewRegistryError("duplicate Preview type")
        self._specs = tuple(sorted(items, key=lambda item: item.preview_type))
        self._by_type = by_type

    @property
    def specs(self) -> tuple[PreviewTypeSpec, ...]:
        return self._specs

    def require(self, preview_type: str) -> PreviewTypeSpec:
        spec = self._by_type.get(preview_type)
        if spec is None:
            raise PreviewRegistryError("unregistered Preview type")
        return spec


def build_preview_registry() -> PreviewRegistry:
    departments = frozenset(SCHEDULING_DEPARTMENTS)
    return PreviewRegistry(
        (
            PreviewTypeSpec(
                preview_type="injection_scheduling.run",
                required_permission="injection_scheduling:edit",
                allowed_departments=departments,
                required_assumption_keys=frozenset(
                    {
                        "plan_status",
                        "preview_mode",
                        "candidate_state",
                        "result_origin",
                    }
                ),
                required_assumption_values=(
                    ("plan_status", "DRAFT"),
                    ("preview_mode", "PREVIEW"),
                    ("candidate_state", "尚未应用、发布或执行"),
                    ("result_origin", "现有注塑排产确定性 Service"),
                ),
                deterministic_service=True,
                may_create_action_proposal=True,
            ),
            PreviewTypeSpec(
                preview_type="workbook.mapping",
                required_permission=(
                    "injection_scheduling:propose_import_profiles"
                ),
                allowed_departments=departments,
                required_assumption_keys=frozenset(
                    {
                        "target_status",
                        "approval_required",
                        "source_authority",
                        "write_performed",
                    }
                ),
                required_assumption_values=(
                    ("target_status", "PROFILE_DRAFT"),
                    ("approval_required", "必须完成"),
                    ("source_authority", "MODEL_INFERENCE"),
                    ("write_performed", "未执行"),
                ),
                deterministic_service=False,
                may_create_action_proposal=False,
            ),
        )
    )


__all__ = ["PreviewRegistry", "PreviewTypeSpec", "build_preview_registry"]
