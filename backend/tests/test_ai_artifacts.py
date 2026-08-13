from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from app.api.ai_artifacts import get_artifact_scanner, get_artifact_storage
from app.core.config import settings
from app.db import get_db
from app.main import app
from app.models.ai_artifact import AIArtifact
from app.services.ai.artifacts.contracts import ArtifactClassification
from app.services.ai.artifacts.readiness import ensure_artifact_runtime_ready
from app.services.ai.artifacts.retention import enforce_artifact_retention
from app.services.ai.artifacts.scanner import FakeArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactNotFoundError,
    ArtifactStorageFailedError,
    create_artifact,
    create_derived_artifact,
    delete_artifact,
    download_artifact,
    get_owned_artifact,
)
from app.services.ai.artifacts.storage import FakeArtifactStorage
from app.services.auth import get_current_user
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from tests.ai_artifact_helpers import (
    NOW,
    artifact_database,
    artifact_settings,
    artifact_user,
    csv_bytes,
)


def _create(db, storage, *, user=None, data=None, now=NOW):
    return create_artifact(
        db,
        user=user or artifact_user(),
        factory_id="huaxing",
        classification=ArtifactClassification.CONFIDENTIAL_BUSINESS,
        filename="订单.csv",
        declared_mime_type="text/csv",
        data=data or csv_bytes(),
        storage=storage,
        scanner=FakeArtifactScanner(),
        settings=artifact_settings(),
        allowed_factory_ids=frozenset({"huaxing"}),
        now=now,
    )


def test_original_is_immutable_and_duplicate_bytes_get_distinct_records() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    try:
        first = _create(db, storage)
        second = _create(db, storage)
        assert first.id != second.id
        assert first.storage_key != second.storage_key
        assert first.sha256 == second.sha256
        assert storage.objects[first.storage_key] == csv_bytes()
        assert first.parent_artifact_id is None
        assert first.derivation_type == "ORIGINAL"
        assert first.scanner_status == "CLEAN"
        assert first.parser_status == "NOT_REQUESTED"
    finally:
        db.close()


def test_download_reauthorizes_owner_factory_and_checks_integrity() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    try:
        record = _create(db, storage)
        allowed = frozenset({"huaxing"})
        assert (
            download_artifact(
                db,
                artifact_id=record.id,
                user=artifact_user(),
                allowed_factory_ids=allowed,
                storage=storage,
            ).data
            == csv_bytes()
        )
        for user in (
            artifact_user("other"),
            artifact_user("owner", factories=("huakang_a",)),
        ):
            with pytest.raises(ArtifactNotFoundError):
                download_artifact(
                    db,
                    artifact_id=record.id,
                    user=user,
                    allowed_factory_ids=allowed,
                    storage=storage,
                )

        storage.objects[record.storage_key] += b"tampered"
        with pytest.raises(Exception, match="完整性"):
            download_artifact(
                db,
                artifact_id=record.id,
                user=artifact_user(),
                allowed_factory_ids=allowed,
                storage=storage,
            )
    finally:
        db.close()


def test_derived_artifact_preserves_parent_versions_and_scope() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    try:
        parent = _create(db, storage)
        derived = create_derived_artifact(
            db,
            parent_artifact_id=parent.id,
            user=artifact_user(),
            classification="RESTRICTED",
            derivation_type="TRANSLATION",
            filename="订单-译文.csv",
            declared_mime_type="text/csv",
            data=csv_bytes("order,quantity\nA-001,十二\n"),
            parser_version="local-translation-v1",
            model_version="ct2-v1",
            storage=storage,
            scanner=FakeArtifactScanner(),
            settings=artifact_settings(),
            allowed_factory_ids=frozenset({"huaxing"}),
            now=NOW + timedelta(minutes=1),
        )
        assert derived.id != parent.id
        assert derived.parent_artifact_id == parent.id
        assert derived.derivation_type == "TRANSLATION"
        assert derived.parser_version == "local-translation-v1"
        assert derived.model_version == "ct2-v1"
        assert derived.retention_until <= parent.retention_until
        assert storage.objects[parent.storage_key] == csv_bytes()

        with pytest.raises(Exception, match="不能降低"):
            create_derived_artifact(
                db,
                parent_artifact_id=derived.id,
                user=artifact_user(),
                classification="INTERNAL",
                derivation_type="REPORT",
                filename="report.csv",
                declared_mime_type="text/csv",
                data=csv_bytes(),
                parser_version="report-v1",
                model_version="",
                storage=storage,
                scanner=FakeArtifactScanner(),
                settings=artifact_settings(),
                allowed_factory_ids=frozenset({"huaxing"}),
                now=NOW + timedelta(minutes=2),
            )
    finally:
        db.close()


def test_delete_revokes_access_before_online_cleanup_and_retention_retries() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage(fail_delete=True)
    config = artifact_settings()
    try:
        record = _create(db, storage)
        result = delete_artifact(
            db,
            artifact_id=record.id,
            user=artifact_user(),
            allowed_factory_ids=frozenset({"huaxing"}),
            storage=storage,
            settings=config,
            now=NOW,
        )
        assert result.status == "DELETION_PENDING"
        assert storage.exists(record.storage_key)
        with pytest.raises(ArtifactNotFoundError):
            get_owned_artifact(
                db, artifact_id=record.id, user=artifact_user()
            )

        storage.fail_delete = False
        report = enforce_artifact_retention(
            db, storage=storage, settings=config, now=NOW + timedelta(hours=1)
        )
        assert report.deleted_online == 1
        assert not storage.exists(record.storage_key)
        db.refresh(record)
        assert record.status == "DELETED"
        assert record.tombstone_expires_at
        assert record.backup_delete_by
    finally:
        db.close()


def test_expired_artifact_is_revoked_and_cleaned() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    try:
        record = _create(db, storage, now=NOW - timedelta(days=31))
        report = enforce_artifact_retention(
            db, storage=storage, settings=artifact_settings(), now=NOW
        )
        assert report.expired == 1
        assert report.deleted_online == 1
        db.refresh(record)
        assert record.status == "EXPIRED"
        with pytest.raises(ArtifactNotFoundError):
            get_owned_artifact(db, artifact_id=record.id, user=artifact_user())
    finally:
        db.close()


def test_storage_write_failure_rolls_back_metadata() -> None:
    db = artifact_database()
    try:
        with pytest.raises(ArtifactStorageFailedError):
            _create(db, FakeArtifactStorage(fail_put=True))
        assert db.scalar(select(func.count(AIArtifact.id))) == 0
    finally:
        db.close()


def test_production_enablement_requires_scanner_and_operational_evidence() -> None:
    config = artifact_settings()
    config.app_env = "production"
    config.ai_artifact_scanner_backend = "disabled"
    with pytest.raises(RuntimeError, match="SCANNER_BACKEND=clamav"):
        ensure_artifact_runtime_ready(config)

    config.ai_artifact_scanner_backend = "clamav"
    with pytest.raises(RuntimeError, match="private_volume_verified"):
        ensure_artifact_runtime_ready(config)

    config.ai_artifact_private_volume_verified = True
    config.ai_artifact_clamav_operations_verified = True
    config.ai_artifact_backup_region = "cn-hangzhou"
    config.ai_artifact_backup_bucket = "private-artifact-backup"
    config.ai_artifact_backup_kms_key_id = SecretStr("kms-secret-id")
    config.ai_artifact_backup_encryption_verified = True
    config.ai_artifact_backup_restore_drill_verified = True
    ensure_artifact_runtime_ready(config)


def test_artifact_api_default_off_then_upload_download_delete(monkeypatch) -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    user_holder = {"value": artifact_user()}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user_holder["value"]
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    app.dependency_overrides[get_artifact_scanner] = lambda: FakeArtifactScanner()
    for key, value in {
        "ai_enabled": True,
        "ai_pilot_enabled": True,
        "ai_pilot_user_ids": "owner,other",
        "ai_pilot_factory_ids": "huaxing",
        "ai_runtime_disable_path": "",
        "app_env": "development",
    }.items():
        monkeypatch.setattr(settings, key, value)
    try:
        client = TestClient(app)
        monkeypatch.setattr(settings, "ai_artifacts_enabled", False)
        assert client.get("/api/ai/artifacts/aiart-" + "0" * 32).status_code == 404

        monkeypatch.setattr(settings, "ai_artifacts_enabled", True)
        created = client.post(
            "/api/ai/artifacts",
            data={"factory_id": "huaxing", "classification": "INTERNAL"},
            files={"file": ("客户订单.csv", csv_bytes(), "text/csv")},
        )
        assert created.status_code == 201, created.text
        artifact_id = created.json()["id"]
        assert "storage_key" not in created.json()
        assert client.get(f"/api/ai/artifacts/{artifact_id}").status_code == 200
        downloaded = client.get(f"/api/ai/artifacts/{artifact_id}/download")
        assert downloaded.status_code == 200
        assert downloaded.content == csv_bytes()
        assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]
        assert downloaded.headers["x-content-type-options"] == "nosniff"

        user_holder["value"] = artifact_user("other")
        assert client.get(f"/api/ai/artifacts/{artifact_id}").status_code == 404
        assert client.get(f"/api/ai/artifacts/{artifact_id}/download").status_code == 404

        user_holder["value"] = artifact_user()
        removed = client.delete(f"/api/ai/artifacts/{artifact_id}")
        assert removed.status_code == 200
        assert removed.json()["access_revoked"] is True
        assert client.get(f"/api/ai/artifacts/{artifact_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_production_compose_keeps_storage_and_scanner_private() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]
    scanner = services["clamav"]
    assert scanner["image"] == "clamav/clamav:1.4_base"
    assert "ports" not in scanner
    assert scanner["environment"]["FRESHCLAM_CHECKS"] == "6"
    assert "clamav-db:/var/lib/clamav" in scanner["volumes"]
    for service_name in ("api", "ai-task-worker"):
        assert (
            "ai-artifacts:/app/backend/data/ai-artifacts"
            in services[service_name]["volumes"]
        )
    assert {"ai-artifacts", "clamav-db"} <= set(compose["volumes"])
