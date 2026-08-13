from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import Settings, settings
from app.services.ai import task_worker


def _enable_dependencies(monkeypatch) -> None:
    for name in (
        "ai_enabled",
        "ai_tasks_enabled",
        "ai_nif_runtime_enabled",
        "ai_skill_router_enabled",
        "ai_evidence_v1_enabled",
        "ai_task_worker_enabled",
    ):
        monkeypatch.setattr(settings, name, True)


def test_worker_is_default_off(monkeypatch) -> None:
    defaults = Settings(_env_file=None)
    assert defaults.ai_task_worker_enabled is False
    assert defaults.ai_task_worker_lease_seconds == 90
    assert defaults.ai_task_worker_heartbeat_seconds == 15
    assert defaults.ai_task_worker_max_recovery_retries == 2
    monkeypatch.setattr(settings, "ai_task_worker_enabled", False)
    with pytest.raises(RuntimeError, match="disabled"):
        task_worker._validate_worker_startup()


def test_worker_requires_postgresql_and_all_dependency_flags(monkeypatch) -> None:
    _enable_dependencies(monkeypatch)
    monkeypatch.setattr(
        task_worker,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
    )
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        task_worker._validate_worker_startup()

    monkeypatch.setattr(
        task_worker,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(settings, "ai_evidence_v1_enabled", False)
    with pytest.raises(RuntimeError, match="dependency flags"):
        task_worker._validate_worker_startup()

    monkeypatch.setattr(settings, "ai_evidence_v1_enabled", True)
    task_worker._validate_worker_startup()


def test_worker_process_has_no_direct_business_model_or_action_dependency() -> None:
    source = Path(task_worker.__file__).read_text(encoding="utf-8")
    assert "app.models" not in source
    assert "ai_action" not in source
    assert "controlled_apply_enabled=False" in source


def test_vision_comparison_worker_requires_every_stage_dependency(monkeypatch) -> None:
    _enable_dependencies(monkeypatch)
    monkeypatch.setattr(
        task_worker,
        "engine",
        SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
    )
    monkeypatch.setattr(settings, "ai_artifacts_enabled", True)
    monkeypatch.setattr(settings, "ai_artifact_workflows_enabled", True)
    monkeypatch.setattr(settings, "ai_artifact_scanner_backend", "clamav")
    monkeypatch.setattr(settings, "ai_provider_capability_router_enabled", True)
    monkeypatch.setattr(settings, "ai_cloud_vision_enabled", True)
    monkeypatch.setattr(settings, "ai_vision_tool_comparison_enabled", True)
    monkeypatch.setattr(settings, "ai_semantic_gateway_enabled", False)

    with pytest.raises(RuntimeError, match="Vision comparison Worker dependencies"):
        task_worker._validate_worker_startup()

    monkeypatch.setattr(settings, "ai_semantic_gateway_enabled", True)
    task_worker._validate_worker_startup()
