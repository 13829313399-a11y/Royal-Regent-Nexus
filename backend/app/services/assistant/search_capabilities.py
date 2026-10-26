"""Native verification is independent of the legacy chat profile."""
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from .errors import AssistantError


class Combination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal["dashscope_multimodal"] = "dashscope_multimodal"
    model: str
    input: Literal["text", "text_image"]
    thinking: Literal["auto", "on", "off"]
    strategy: Literal["turbo"] = "turbo"
    forced_search: bool
    source_return: bool
    inline_citations: bool
    verified_at: str


class SearchProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    endpoint: str
    region: str
    verified_combinations: list[Combination] = Field(default_factory=list)
    last_result: dict | None = None


def configured():
    try:
        url = urlsplit(settings.assistant_search_endpoint)
        return bool(settings.assistant_qwen_api_key.get_secret_value() and settings.assistant_model and
                    url.scheme == "https" and url.hostname and not (url.username or url.password or url.query or url.fragment) and
                    url.path.endswith("/api/v1/services/aigc/multimodal-generation/generation"))
    except ValueError:
        return False


def capability():
    result = dict(configured=configured(), verification="unverified", verified_at=None, supported_modes=["off"],
        supported_protocols=["dashscope_multimodal"] if configured() else [], verified_combinations=[],
        source_return=False, inline_citations=False, page_fetch=True, last_result=None,
        reason_code="search_unconfigured", status_label="联网连接待配置；可关闭联网继续问答。")
    if not result["configured"]:
        return result
    result.update(reason_code="search_profile_missing", status_label="联网连接已配置，能力组合尚未验证。")
    if not settings.assistant_search_capabilities_file:
        return result
    try:
        p = SearchProfile.model_validate_json(Path(settings.assistant_search_capabilities_file).read_text(encoding="utf-8"))
        if (p.model, p.endpoint, p.region) != (settings.assistant_model, settings.assistant_search_endpoint, settings.assistant_search_region):
            result.update(reason_code="search_profile_mismatch", status_label="联网能力记录与当前模型、地域或连接不匹配，请管理员核对。")
            return result
        combos = [c.model_dump() for c in p.verified_combinations if c.model == p.model and c.source_return and c.forced_search]
        # Profile probes are historical verification, never a user's last execution.
        result.update(verified_combinations=combos, reason_code="search_combination_unverified",
                      status_label="尚无可用的联网组合；可关闭联网继续问答。")
        if combos:
            result.update(verification="verified", verified_at=max(c["verified_at"] for c in combos),
                          supported_modes=["off", "auto", "on"], source_return=True,
                          inline_citations=any(c["inline_citations"] for c in combos), reason_code=None,
                          status_label="可使用已验证的联网组合；实际来源以本次返回为准。")
    except (OSError, ValueError, json.JSONDecodeError):
        result["verification"] = "failed"
        result.update(reason_code="search_profile_invalid", status_label="联网能力记录无法读取，请管理员核对。")
    return result


def validate(payload):
    cap = capability()
    if payload.web_search not in cap["supported_modes"]:
        raise AssistantError("search_unavailable", "联网能力尚未配置或验证；可以关闭联网继续普通问答。")
    kind = "text_image" if payload.attachment_ids else "text"
    if not any(c["input"] == kind and c["thinking"] == payload.thinking for c in cap["verified_combinations"]):
        raise AssistantError("unsupported_combination", "当前联网方式尚未验证这组图片或思考选项，请选择已支持组合。")
