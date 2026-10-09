"""Configuration is not a paid probe or evidence of connection success."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import inspect, UniqueConstraint
from app.core.config import settings
from app import db as database
from app.models import assistant as models
from .errors import AssistantError


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    base_url: str
    protocol: Literal["chat_completions"] = "chat_completions"
    region: str
    documentation: list[str] = Field(default_factory=list)
    verified_at: str | None = None
    thinking: Literal["unknown", "toggle", "always", "none"] = "unknown"
    vision: bool = False
    function_calling: bool = False
    # Search remains unavailable until a provenance-preserving adapter exists.
    web_search: Literal[False] = False
    output_limit_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    context_character_budget: int = Field(default=100000, ge=1000)
    verified_combinations: list[str] = Field(default_factory=list)


def profile():
    if not settings.assistant_model_capabilities_file:
        return None
    try:
        result = ModelProfile.model_validate_json(Path(settings.assistant_model_capabilities_file).read_text(encoding="utf-8"))
        if result.model != settings.assistant_model or result.base_url.rstrip("/") != settings.assistant_qwen_base_url.rstrip("/"):
            raise ValueError("configuration changed")
        return result
    except (OSError, ValueError, json.JSONDecodeError):
        raise AssistantError("capabilities_invalid", "模型能力记录与当前连接不匹配，请管理员核对。", 503)


def schema_ready():
    try:
        inspector = inspect(database.engine)
        for cls in (models.AssistantSession, models.AssistantMessage, models.AssistantRun, models.AssistantAttachment):
            table = cls.__table__
            if not inspector.has_table(table.name):
                return False
            if not set(table.columns.keys()) <= {c["name"] for c in inspector.get_columns(table.name)}:
                return False
            uniques = {tuple(sorted(c["column_names"])) for c in inspector.get_unique_constraints(table.name)}
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint) and tuple(sorted(c.name for c in constraint.columns)) not in uniques:
                    return False
            if len(inspector.get_foreign_keys(table.name)) < len(table.foreign_key_constraints):
                return False
        return True
    except Exception:
        return False


def configuration_status():
    if not (settings.assistant_qwen_api_key.get_secret_value() and settings.assistant_qwen_base_url and settings.assistant_model):
        return "unconfigured"
    url = urlsplit(settings.assistant_qwen_base_url)
    if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
            or not url.path.rstrip("/").endswith("/v1") or "ocr" in settings.assistant_model.lower()):
        return "invalid"
    return "configured"


def capabilities():
    config = configuration_status()
    p = None
    try:
        p = profile()
    except AssistantError:
        config = "invalid"
    verified = bool(p and p.verified_at and "text" in p.verified_combinations)
    ready = schema_ready() if settings.assistant_enabled else False
    return dict(enabled=settings.assistant_enabled, configuration_status=config,
        schema_status="ready" if ready else "schema_pending", connection_status="verified" if verified else "unverified",
        verified_at=p.verified_at if verified else None, provider=settings.assistant_provider, model=settings.assistant_model or None,
        help_status="ready", profiles=[dict(id="default", label="默认模型", thinking=p.thinking if verified else "unknown",
            vision=bool(verified and p.vision and "vision" in p.verified_combinations), web_search=False,
            function_calling=bool(verified and p.function_calling and "tools" in p.verified_combinations))])


def require_enabled(*, schema=True, chat=False):
    if not settings.assistant_enabled:
        raise AssistantError("disabled", "曜灵暂未启用。", 503)
    if schema and not schema_ready():
        raise AssistantError("schema_pending", "曜灵的数据准备尚未完成，本页说明仍可查看。", 503)
    if chat:
        status = configuration_status()
        if status != "configured":
            raise AssistantError(status, "曜灵的模型连接尚未完成。你仍可查看本页操作说明。", 503)
        profile()


def validate_options(payload):
    caps = capabilities()["profiles"][0]
    if payload.web_search != "off":
        raise AssistantError("search_unavailable", "当前模型连接尚未验证联网来源协议。")
    if payload.attachment_ids and not caps["vision"]:
        raise AssistantError("vision_unavailable", "当前模型尚未验证图片理解。")
    thinking = caps["thinking"]
    if payload.thinking != "auto" and (thinking != "toggle"):
        raise AssistantError("thinking_unavailable", "当前模型不支持切换思考模式，请使用自动。")
