from __future__ import annotations

import io
from datetime import datetime

from app.core.config import Settings
from app.db import Base
from app.models.ai_artifact import AIArtifact
from app.models.auth import AuthAuditLog, AuthUser
from app.services.auth import AuthContext, AuthGrantContext
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def artifact_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        app_env="development",
        ai_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="owner,other",
        ai_pilot_factory_ids="huaxing,huakang_a",
        ai_artifacts_enabled=True,
        ai_artifact_scanner_backend="disabled",
    )


def artifact_user(
    user_id: str = "owner", *, factories: tuple[str, ...] = ("huaxing",)
) -> AuthContext:
    grants = tuple(
        AuthGrantContext(
            role_id=f"role-{user_id}-{factory}",
            role_name="AI Artifact Test",
            factory_id=factory,
            department="production",
            permissions=frozenset(),
            binding_id=f"binding-{user_id}-{factory}",
        )
        for factory in factories
    )
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name=user_id,
        roles=("AI Artifact Test",),
        role_codes=("ai-artifact-test",),
        permissions=frozenset(),
        factory_scopes=factories,
        department_scopes=("production",),
        grants=grants,
    )


def artifact_database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[AuthUser.__table__, AuthAuditLog.__table__, AIArtifact.__table__],
    )
    db = Session(engine)
    for user_id in ("owner", "other"):
        db.add(
            AuthUser(
                id=user_id,
                username=user_id,
                display_name=user_id,
                password_salt="salt",
                password_hash="hash",
                status="active",
                force_password_change=0,
                avatar_png=None,
                avatar_version="",
                last_login_at="",
                created_at="2026-08-12T08:00:00+08:00",
                updated_at="2026-08-12T08:00:00+08:00",
            )
        )
    db.commit()
    return db


def csv_bytes(value: str = "order,quantity\nA-001,12\n") -> bytes:
    return value.encode("utf-8")


def png_bytes(*, size: tuple[int, int] = (2, 2)) -> bytes:
    output = io.BytesIO()
    with Image.new("RGB", size, color=(10, 20, 30)) as image:
        image.save(output, format="PNG")
    return output.getvalue()


NOW = datetime.fromisoformat("2026-08-12T10:00:00+08:00")
