from pathlib import Path

from app.core.config import Settings
from app.services.ai.artifacts.readiness import ensure_artifact_runtime_ready
from app.services.ai.observability.alerts import ensure_ai_alert_runtime_ready

PROFILE_PATH = Path(__file__).resolve().parents[1] / "local-ai.env.example"

ENABLED_FEATURE_FLAGS = {
    "AI_ENABLED",
    "AI_NIF_RUNTIME_ENABLED",
    "AI_PROVIDER_CAPABILITY_ROUTER_ENABLED",
    "AI_SKILL_ROUTER_ENABLED",
    "AI_EVIDENCE_V1_ENABLED",
    "AI_CONVERSATIONS_ENABLED",
    "AI_TASKS_ENABLED",
    "AI_SEMANTIC_GATEWAY_ENABLED",
    "AI_KNOWLEDGE_HUB_ENABLED",
    "AI_ARTIFACTS_ENABLED",
    "AI_ARTIFACT_WORKFLOWS_ENABLED",
    "AI_VISION_TOOL_COMPARISON_ENABLED",
    "AI_CLOUD_VISION_ENABLED",
    "AI_CLOUD_DOCUMENT_TRANSLATION_ENABLED",
    "AI_CLOUD_WORKBOOK_MAPPING_ENABLED",
    "AI_ACTION_GATEWAY_ENABLED",
    "AI_CONTROLLED_APPLY_ENABLED",
    "AI_FEEDBACK_ENABLED",
    "AI_OBSERVABILITY_ENABLED",
    "AI_METRIC_EXPORT_ENABLED",
    "AI_PILOT_ENABLED",
}

LOCAL_INFRASTRUCTURE_FLAGS = {
    "AI_TASK_WORKER_ENABLED": "false",
    "AI_SHARED_GUARD_ENABLED": "false",
    "AI_OPERATIONAL_ALERTS_ENABLED": "false",
    "AI_PILOT_PUBLIC_TLS_VERIFIED": "false",
    "AI_ARTIFACT_PRIVATE_VOLUME_VERIFIED": "false",
    "AI_ARTIFACT_CLAMAV_OPERATIONS_VERIFIED": "false",
    "AI_ARTIFACT_BACKUP_ENCRYPTION_VERIFIED": "false",
    "AI_ARTIFACT_BACKUP_RESTORE_DRILL_VERIFIED": "false",
}

FORBIDDEN_SECRET_KEYS = {
    "AI_BASE_URL",
    "AI_ARTIFACT_BACKUP_BUCKET",
    "AI_ARTIFACT_BACKUP_KMS_KEY_ID",
    "DASHSCOPE_API_KEY",
}


def _profile_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in PROFILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator == "="
        assert key not in values
        values[key] = value
    return values


def test_local_ai_profile_is_secret_free_and_enables_the_ui_surface() -> None:
    values = _profile_values()

    assert all(key.startswith("AI_") for key in values)
    assert FORBIDDEN_SECRET_KEYS.isdisjoint(values)
    assert all(values[key] == "true" for key in ENABLED_FEATURE_FLAGS)
    assert all(values[key] == value for key, value in LOCAL_INFRASTRUCTURE_FLAGS.items())
    assert values["AI_PILOT_USER_IDS"] == "user-admin"
    assert values["AI_NIF18_STAGE"] == "action-field"


def test_local_ai_profile_respects_development_startup_guards() -> None:
    profile = Settings(_env_file=PROFILE_PATH)

    assert profile.ai_artifact_scanner_backend == "clamav"
    assert profile.ai_artifacts_enabled is True
    assert profile.ai_operational_alerts_enabled is False
    assert profile.ai_task_worker_enabled is False
    assert profile.ai_shared_guard_enabled is False

    ensure_artifact_runtime_ready(profile)
    ensure_ai_alert_runtime_ready(profile)
