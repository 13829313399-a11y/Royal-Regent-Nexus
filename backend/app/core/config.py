from pathlib import Path
from typing import Literal

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
    three_d_asset_dir: str = str(
        BACKEND_DIR / "data" / "three-d-printing-assets"
    )
    three_d_edge_agent_token: str = ""
    three_d_command_ttl_seconds: int = 120
    three_d_command_poll_interval_seconds: int = 3
    customer_order_test_duplicate_confirmation_enabled: bool | None = None
    injection_scheduling_export_signing_key: str = ""
    injection_scheduling_export_signing_key_id: str = "v1"
    injection_scheduling_export_verification_keys_json: str = "{}"

    @property
    def effective_session_cookie_secure(self) -> bool:
        return self.session_cookie_secure

    @property
    def effective_customer_order_test_duplicate_confirmation_enabled(self) -> bool:
        configured = self.customer_order_test_duplicate_confirmation_enabled
        if configured is not None:
            return configured
        return self.app_env.strip().lower() not in {"production", "prod"}

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")


settings = Settings()

if settings.authz_writes_enabled and settings.authz_mode != "enforce":
    raise RuntimeError("AUTHZ_WRITES_ENABLED=true requires AUTHZ_MODE=enforce")
