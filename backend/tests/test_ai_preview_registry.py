from __future__ import annotations

import pytest
from app.services.ai.previews.contracts import PreviewTypeSpec
from app.services.ai.previews.registry import (
    PreviewRegistry,
    PreviewRegistryError,
    build_preview_registry,
)


def test_preview_registry_is_closed_and_has_two_non_overlapping_adapters() -> None:
    registry = build_preview_registry()

    assert [item.preview_type for item in registry.specs] == [
        "injection_scheduling.run",
        "workbook.mapping",
    ]
    scheduling = registry.require("injection_scheduling.run")
    workbook = registry.require("workbook.mapping")
    assert scheduling.deterministic_service is True
    assert scheduling.may_create_action_proposal is True
    assert workbook.deterministic_service is False
    assert workbook.may_create_action_proposal is False

    with pytest.raises(PreviewRegistryError, match="unregistered"):
        registry.require("arbitrary.preview")


def test_preview_registry_rejects_duplicate_types_and_incomplete_contracts() -> None:
    spec = build_preview_registry().require("injection_scheduling.run")
    with pytest.raises(PreviewRegistryError, match="duplicate"):
        PreviewRegistry((spec, spec))

    with pytest.raises(ValueError, match="cover every key"):
        PreviewTypeSpec(
            preview_type="broken.preview",
            required_permission="broken:read",
            allowed_departments=frozenset({"production"}),
            required_assumption_keys=frozenset({"required"}),
            required_assumption_values=(),
            deterministic_service=True,
            may_create_action_proposal=False,
        )
