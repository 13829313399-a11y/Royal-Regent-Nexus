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
    ai_nif_runtime_enabled: bool = False
    ai_provider_capability_router_enabled: bool = False
    ai_skill_router_enabled: bool = False
    ai_evidence_v1_enabled: bool = False
    ai_conversations_enabled: bool = False
    ai_adaptive_surface_enabled: bool = False
    ai_rich_message_renderer_enabled: bool = False
    ai_workbench_v2_enabled: bool = False
    ai_conversation_context_enabled: bool = False
    ai_presentation_blocks_enabled: bool = False
    ai_conversation_message_retention_days: Literal[30] = 30
    ai_conversation_summary_retention_days: Literal[30] = 30
    ai_conversation_tombstone_retention_days: Literal[180] = 180
    ai_conversation_security_audit_retention_days: Literal[180] = 180
    ai_conversation_action_audit_retention_days: Literal[365] = 365
    ai_conversation_backup_retention_days: Literal[30] = 30
    ai_conversation_backup_delete_sla_days: Literal[30] = 30
    ai_tasks_enabled: bool = False
    ai_task_retention_days: Literal[180] = 180
    ai_task_security_audit_retention_days: Literal[180] = 180
    ai_task_backup_delete_sla_days: Literal[30] = 30
    ai_task_worker_enabled: bool = False
    ai_task_worker_concurrency: int = Field(default=1, ge=1, le=4)
    ai_task_worker_lease_seconds: Literal[90] = 90
    ai_task_worker_heartbeat_seconds: Literal[15] = 15
    ai_task_worker_max_recovery_retries: Literal[2] = 2
    ai_task_worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=10)
    ai_shared_guard_enabled: bool = False
    ai_semantic_gateway_enabled: bool = False
    ai_knowledge_hub_enabled: bool = False
    ai_artifacts_enabled: bool = False
    ai_artifact_workflows_enabled: bool = False
    ai_vision_tool_comparison_enabled: bool = False
    ai_preview_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    ai_artifact_storage_dir: str = str(BACKEND_DIR / "data" / "ai-artifacts")
    ai_artifact_scanner_backend: Literal["disabled", "clamav"] = "disabled"
    ai_artifact_clamav_host: str = "clamav"
    ai_artifact_clamav_port: int = Field(default=3310, ge=1, le=65535)
    ai_artifact_clamav_timeout_seconds: float = Field(default=15, gt=0, le=60)
    ai_artifact_retention_days: Literal[30] = 30
    ai_artifact_tombstone_retention_days: Literal[180] = 180
    ai_artifact_security_audit_retention_days: Literal[180] = 180
    ai_artifact_backup_delete_sla_days: Literal[30] = 30
    ai_artifact_backup_provider: Literal["aliyun_oss"] = "aliyun_oss"
    ai_artifact_backup_region: str = ""
    ai_artifact_backup_bucket: str = ""
    ai_artifact_backup_kms_key_id: SecretStr = SecretStr("")
    ai_artifact_private_volume_verified: bool = False
    ai_artifact_clamav_operations_verified: bool = False
    ai_artifact_backup_encryption_verified: bool = False
    ai_artifact_backup_restore_drill_verified: bool = False
    ai_guard_instance_id: str = Field(
        default="",
        max_length=128,
        pattern=r"^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,127})?$",
    )
    ai_guard_lease_seconds: int = Field(default=900, ge=180, le=3600)
    ai_guard_request_retention_minutes: int = Field(default=10, ge=2, le=60)
    ai_guard_budget_retention_days: int = Field(default=35, ge=2, le=90)
    ai_task_event_stream_poll_seconds: float = Field(default=0.5, ge=0.1, le=2)
    ai_task_event_stream_max_seconds: int = Field(default=25, ge=5, le=30)
    ai_model_catalog_json: str = ""
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
    ai_cloud_workbook_mapping_enabled: bool = False
    ai_action_gateway_enabled: bool = False
    ai_controlled_apply_enabled: bool = False
    ai_feedback_enabled: bool = False
    ai_observability_enabled: bool = False
    ai_metric_export_enabled: bool = False
    ai_input_token_cost_usd_per_million: float = Field(default=0.0, ge=0, le=1000)
    ai_output_token_cost_usd_per_million: float = Field(default=0.0, ge=0, le=1000)
    ai_operational_alerts_enabled: bool = False
    ai_alert_target_user_ids: str = ""
    ai_alert_evaluation_interval_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
    )
    ai_alert_window_minutes: int = Field(default=15, ge=1, le=1440)
    ai_alert_cooldown_minutes: int = Field(default=60, ge=5, le=1440)
    ai_cost_per_successful_task_alert_microusd: int = Field(
        default=0,
        ge=0,
        le=10_000_000_000,
    )
    ai_provider_failure_alert_count: int = Field(default=0, ge=0, le=1_000_000)
    ai_tool_failure_alert_count: int = Field(default=0, ge=0, le=1_000_000)
    ai_worker_recovery_alert_count: int = Field(default=0, ge=0, le=1_000_000)
    ai_budget_alert_percent: int = Field(default=0, ge=0, le=100)
    ai_scanner_signature_max_age_hours: int = Field(default=0, ge=0, le=720)
    ai_nif18_stage: Literal["disabled", "preflight", "action-field"] = "disabled"
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
