from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    ai_enabled: bool = False
    ai_provider: str = "qwen"
    ai_region: str = "cn-beijing"
    ai_workspace_id: str = ""
    dashscope_api_key: SecretStr = SecretStr("")
    ai_default_model: str = "qwen3.7-plus"
    ai_vision_model: str = "qwen3.7-plus"
    ai_request_timeout_seconds: float = Field(default=60, gt=0, le=120)
    ai_max_tool_rounds: int = Field(default=4, ge=0, le=6)
    ai_max_tool_result_rows: int = Field(default=50, ge=1, le=50)
    ai_max_tool_result_bytes: int = Field(default=65_536, ge=1, le=65_536)
    ai_max_tool_result_fields: int = Field(default=64, ge=1, le=64)
    ai_max_input_messages: int = Field(default=12, ge=1, le=12)
    ai_max_input_message_chars: int = Field(default=8_000, ge=1, le=8_000)
    ai_max_input_chars: int = Field(default=40_000, ge=1, le=40_000)
    ai_reasoning_effort: Literal[
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ] = "low"
    ai_log_raw_prompts: bool = False
    ai_log_raw_tool_results: bool = False
    ai_pilot_enabled: bool = False
    ai_pilot_user_ids: str = ""
    ai_pilot_factory_ids: str = ""
    ai_pilot_public_tls_verified: bool = False
    ai_runtime_disable_path: str = ""
    ai_pilot_max_concurrent_per_user: int = Field(default=1, ge=1, le=2)
    ai_pilot_requests_per_minute: int = Field(default=10, ge=1, le=60)
    ai_pilot_daily_token_budget: int = Field(
        default=20_000_000,
        gt=0,
        le=100_000_000,
    )
    ai_pilot_max_output_tokens: int = Field(default=4_096, gt=0, le=16_384)
    ai_cloud_vision_enabled: bool = False
    ai_test_fake_vision_enabled: bool = False
    ai_max_image_attachments: int = Field(default=3, ge=1, le=3)
    ai_max_image_bytes: int = Field(default=4 * 1024 * 1024, gt=0, le=4 * 1024 * 1024)
    ai_max_image_total_bytes: int = Field(
        default=12 * 1024 * 1024,
        gt=0,
        le=12 * 1024 * 1024,
    )
    ai_max_image_encoded_chars: int = Field(default=17_000_000, gt=0, le=17_000_000)
    ai_max_request_bytes: int = Field(
        default=18 * 1024 * 1024,
        gt=0,
        le=18 * 1024 * 1024,
    )
    ai_max_image_pixels: int = Field(default=16_000_000, gt=0, le=16_000_000)
    ai_max_image_total_pixels: int = Field(
        default=24_000_000,
        gt=0,
        le=24_000_000,
    )
    ai_cloud_document_translation_enabled: bool = False
    ai_base_url: str = ""

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
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8"
    )


settings = Settings()

if settings.authz_writes_enabled and settings.authz_mode != "enforce":
    raise RuntimeError("AUTHZ_WRITES_ENABLED=true requires AUTHZ_MODE=enforce")
