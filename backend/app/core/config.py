from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Royal Regent Nexus API"
    app_env: str = "development"
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'royal_regent_nexus.db'}"
    session_cookie_secure: bool = False
    seed_default_accounts: bool = True
    seed_admin_password: str = ""
    authz_mode: Literal["legacy", "shadow", "enforce"] = "legacy"
    authz_writes_enabled: bool = False
    three_d_asset_dir: str = str(BACKEND_DIR / "data" / "three-d-printing-assets")
    three_d_edge_agent_token: str = ""
    three_d_command_ttl_seconds: int = 120
    three_d_command_poll_interval_seconds: int = 3
    customer_order_test_duplicate_confirmation_enabled: bool | None = None
    document_translation_model_dir: str = str(
        BACKEND_DIR / "models" / "document-translation"
    )
    document_translation_device: Literal["cpu", "cuda", "auto"] = "cpu"
    injection_scheduling_export_signing_key: str = ""
    injection_scheduling_export_signing_key_id: str = "v1"
    injection_scheduling_export_verification_keys_json: str = "{}"
    document_tools_enabled: bool = True
    document_tool_max_file_bytes: int = Field(
        default=20 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
    )
    document_tool_max_pdf_pages: int = Field(default=80, ge=1, le=200)
    document_tool_temp_ttl_minutes: int = Field(default=60, ge=5, le=24 * 60)
    document_office_renderer_enabled: bool = False
    document_office_renderer_command: str = Field(
        default="libreoffice",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    document_office_renderer_timeout_seconds: int = Field(
        default=120,
        ge=30,
        le=300,
    )
    document_office_renderer_network_isolation_command: str = Field(
        default="unshare",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    document_office_renderer_network_isolation_verified: bool = False


    @property
    def effective_session_cookie_secure(self) -> bool:
        return self.session_cookie_secure

    @property
    def effective_customer_order_test_duplicate_confirmation_enabled(self) -> bool:
        configured = self.customer_order_test_duplicate_confirmation_enabled
        if configured is not None:
            return configured
        return self.app_env.strip().lower() not in {"production", "prod"}

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

if settings.authz_writes_enabled and settings.authz_mode != "enforce":
    raise RuntimeError("AUTHZ_WRITES_ENABLED=true requires AUTHZ_MODE=enforce")
