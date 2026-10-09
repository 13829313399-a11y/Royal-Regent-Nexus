from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    iam_identity_writes_enabled: bool = False
    iam_identity_scheduling_enabled: bool = False
    three_d_asset_dir: str = str(BACKEND_DIR / "data" / "three-d-printing-assets")
    three_d_edge_agent_token: str = ""
    three_d_network_health_token: str = ""
    spray_ops_enabled: bool = False
    cutting_ops_enabled: bool = False
    uv_ops_enabled: bool = False
    uv_ops_dispatch_enabled: bool = False
    three_d_connector_enabled: bool = False
    three_d_connector_token: str = ""
    three_d_connector_control_enabled: bool = False
    three_d_connector_verified_machines: list[int] = []
    three_d_command_ttl_seconds: int = 120
    three_d_command_poll_interval_seconds: int = 3
    three_d_reconciliation_sweep_seconds: int = 60
    three_d_reconciliation_terminal_grace_seconds: int = 120
    three_d_reconciliation_stale_open_seconds: int = 12 * 3600
    three_d_reconciliation_same_file_window_seconds: int = 600
    # Optional rollout guard: when set, only runs observed at or after this instant may
    # create records. Unset means no guard, so set it deliberately when turning the
    # record switch on for a connection that was already being observed.
    three_d_record_reconcile_since: str = ""
    customer_order_test_duplicate_confirmation_enabled: bool | None = None
    document_translation_model_dir: str = str(
        BACKEND_DIR / "models" / "document-translation"
    )
    document_translation_device: Literal["cpu", "cuda", "auto"] = "cpu"
    document_tools_enabled: bool = True
    assistant_enabled: bool = False
    assistant_provider: Literal["qwen_openai_compatible"] = "qwen_openai_compatible"
    assistant_qwen_api_key: SecretStr = SecretStr("")
    assistant_qwen_base_url: str = ""
    assistant_model: str = ""
    assistant_model_capabilities_file: str = ""
    assistant_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    assistant_upstream_idle_timeout_seconds: int = Field(default=180, ge=1, le=600)
    assistant_run_timeout_seconds: int = Field(default=900, ge=1, le=3600)
    assistant_max_output_tokens: int | None = Field(default=None, ge=1)
    assistant_context_character_budget: int = Field(default=100000, ge=1000)
    assistant_per_user_concurrency: int = Field(default=2, ge=1, le=32)
    assistant_global_concurrency: int = Field(default=8, ge=1, le=128)
    assistant_storage_dir: str = str(BACKEND_DIR / "data" / "assistant")
    assistant_trusted_origins: list[str] = []
    assistant_max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    assistant_max_tool_rounds: int = Field(default=5, ge=1, le=16)
    assistant_daily_token_budget: int | None = Field(default=None, ge=1)
    assistant_retention_days: int | None = Field(default=None, ge=1)

    @field_validator("assistant_max_output_tokens", "assistant_daily_token_budget", "assistant_retention_days", mode="before")
    @classmethod
    def assistant_blank_is_unlimited(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    document_tools_storage_dir: str = str(BACKEND_DIR / "data" / "document-tools")
    document_tools_worker_concurrency: int = Field(default=2, ge=1, le=8)
    document_tools_lease_seconds: int = Field(default=90, ge=15, le=600)
    document_tools_max_attempts: int = Field(default=3, ge=1, le=10)
    document_tools_max_file_bytes: int = Field(default=100 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    document_tools_max_pages: int = Field(default=200, ge=1, le=1000)
    document_tools_retention_days: int | None = Field(default=None, ge=1)
    document_tools_ai_mode: Literal["auto", "off"] = "auto"
    document_tools_office_command: str = "soffice"
    document_tools_office_timeout_seconds: int = Field(default=300, ge=10, le=1800)
    document_tools_uno_python: str = "/usr/bin/python3"
    document_tools_qwen_api_key: SecretStr = SecretStr("")
    document_tools_qwen_base_url: str = ""
    document_tools_qwen_protocol: Literal["dashscope", "openai"] = "dashscope"
    document_tools_qwen_ocr_model: str = "qwen3.5-ocr"
    document_tools_qwen_layout_model: str = "qwen3-vl-plus"
    document_tools_translation_model: str = "qwen3-vl-plus"
    document_tools_qwen_timeout_seconds: int = Field(default=90, ge=5, le=300)
    image_translation_model_dir: str = str(BACKEND_DIR / "models" / "image-translation")
    image_translation_runner: str = str(BACKEND_DIR.parent / "shinobu-web" / "server" / "dist" / "runner.mjs")
    image_translation_node: str = "node"
    image_translation_timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    image_translation_max_pixels: int = Field(default=24_000_000, ge=1, le=40_000_000)
    image_translation_max_total_pixels: int = Field(default=80_000_000, ge=1, le=200_000_000)
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
