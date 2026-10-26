"""Metadata-only diagnostics. Never return addresses, paths, keys or chat text."""
import os
from datetime import datetime, timezone
from app.core.config import settings
from app.services.auth import has_permission_in_scope
from .errors import AssistantError


def allowed(user):
    return has_permission_in_scope(user, "system:access_manage", "group", "system")


def details(user):
    if not allowed(user):
        raise AssistantError("diagnostics_forbidden", "仅有集团系统权限的管理员可查看连接诊断。", 403)
    from .capabilities import capabilities
    value = capabilities()
    return dict(diagnostics_version=1, checked_at=datetime.now(timezone.utc).isoformat(), process_id=os.getpid(),
        model=value["model"], chat_protocol="chat_completions", search_protocol="dashscope_multimodal",
        region=settings.assistant_search_region, configuration_status=value["configuration_status"],
        schema_status=value["schema_status"], chat_reason_code=value["reason_code"],
        chat_verified_at=value["verified_at"], search_reason_code=value["search"]["reason_code"],
        search_verified_at=value["search"]["verified_at"],
        verified_combinations=value["search"]["verified_combinations"],
        limits=dict(run_seconds=settings.assistant_run_timeout_seconds,
                    output_tokens=settings.assistant_max_output_tokens,
                    daily_tokens=settings.assistant_daily_token_budget,
                    tool_rounds=settings.assistant_max_tool_rounds),
        paid_retry="explicit_only", history_scope="current_user_and_employment_epoch")
