from __future__ import annotations

import re

from app.core.config import Settings


def ensure_artifact_runtime_ready(settings: Settings) -> None:
    """Fail closed when production upload is enabled without ADR-009 evidence."""

    if not settings.ai_artifacts_enabled:
        return
    if settings.ai_artifact_scanner_backend != "clamav":
        raise RuntimeError(
            "AI_ARTIFACTS_ENABLED=true requires AI_ARTIFACT_SCANNER_BACKEND=clamav."
        )
    if settings.app_env.strip().casefold() not in {"production", "prod"}:
        return
    missing: list[str] = []
    if not settings.ai_artifact_private_volume_verified:
        missing.append("private_volume_verified")
    if not settings.ai_artifact_clamav_operations_verified:
        missing.append("clamav_operations_verified")
    if re.fullmatch(r"cn-[a-z0-9-]+", settings.ai_artifact_backup_region) is None:
        missing.append("mainland_backup_region")
    if not settings.ai_artifact_backup_bucket.strip():
        missing.append("private_backup_bucket")
    if not settings.ai_artifact_backup_kms_key_id.get_secret_value().strip():
        missing.append("backup_kms_key")
    if not settings.ai_artifact_backup_encryption_verified:
        missing.append("backup_encryption_verified")
    if not settings.ai_artifact_backup_restore_drill_verified:
        missing.append("backup_restore_drill_verified")
    if missing:
        raise RuntimeError(
            "AI Artifact production readiness evidence is incomplete: "
            + ", ".join(missing)
        )
