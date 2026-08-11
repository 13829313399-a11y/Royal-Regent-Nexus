import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import Settings
from app.services.ai.providers.base import LLMProvider
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.providers.qwen_responses import QwenResponsesProvider

_IDENTIFIER_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_CUSTOM_BASE_URL_ENVS = {"development", "test"}
_VISION_PROVIDER = "qwen"
_VISION_REGION = "cn-beijing"
_VISION_MODEL = "qwen3.7-plus"


class ProviderConfigurationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    enabled: bool
    available: bool
    provider: str
    model: str
    streaming: bool
    function_calls: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VisionProviderStatus:
    enabled: bool
    available: bool
    provider: str
    model: str
    region: str
    base_url: str | None = None
    test_only: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PilotProviderStatus:
    available: bool
    provider: str
    model: str
    region: str
    base_url: str | None = None
    reason: str | None = None


def _normalized_provider(settings: Settings) -> str:
    provider = settings.ai_provider.strip().lower()
    return provider if provider in {"fake", "qwen"} else "unsupported"


def resolve_qwen_base_url(settings: Settings) -> str:
    override = settings.ai_base_url.strip()
    app_env = settings.app_env.strip().lower()
    if override:
        if app_env not in _CUSTOM_BASE_URL_ENVS:
            raise ProviderConfigurationError("base_url_override_not_allowed")
        parsed = urlsplit(override)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError("invalid_base_url")
        return override.rstrip("/")

    workspace_id = settings.ai_workspace_id.strip().lower()
    region = settings.ai_region.strip().lower()
    if not workspace_id:
        raise ProviderConfigurationError("missing_workspace")
    if not _IDENTIFIER_PATTERN.fullmatch(workspace_id):
        raise ProviderConfigurationError("invalid_workspace")
    if not _IDENTIFIER_PATTERN.fullmatch(region):
        raise ProviderConfigurationError("invalid_region")
    return f"https://{workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"


def _validate_common_settings(settings: Settings) -> str | None:
    if not settings.ai_default_model.strip():
        return "missing_model"
    if settings.ai_cloud_vision_enabled and not settings.ai_vision_model.strip():
        return "missing_vision_model"
    if not 0 < settings.ai_request_timeout_seconds <= 300:
        return "invalid_request_timeout"
    limits = (
        settings.ai_max_tool_rounds,
        settings.ai_max_tool_result_rows,
        settings.ai_max_input_messages,
        settings.ai_max_input_message_chars,
        settings.ai_max_input_chars,
    )
    if any(value <= 0 for value in limits):
        return "invalid_limit"
    return None


def get_provider_status(settings: Settings) -> ProviderStatus:
    provider = _normalized_provider(settings)
    model = settings.ai_default_model.strip()
    if not settings.ai_enabled:
        return ProviderStatus(
            enabled=False,
            available=False,
            provider=provider,
            model=model,
            streaming=False,
            function_calls=False,
            reason="disabled",
        )

    common_error = _validate_common_settings(settings)
    if common_error:
        return ProviderStatus(
            enabled=True,
            available=False,
            provider=provider,
            model=model,
            streaming=False,
            function_calls=False,
            reason=common_error,
        )
    if provider == "unsupported":
        return ProviderStatus(
            enabled=True,
            available=False,
            provider=provider,
            model=model,
            streaming=False,
            function_calls=False,
            reason="unsupported_provider",
        )
    if provider == "fake":
        return ProviderStatus(
            enabled=True,
            available=True,
            provider=provider,
            model=model,
            streaming=True,
            function_calls=True,
        )

    if not settings.dashscope_api_key.get_secret_value().strip():
        return ProviderStatus(
            enabled=True,
            available=False,
            provider=provider,
            model=model,
            streaming=False,
            function_calls=False,
            reason="missing_api_key",
        )
    try:
        resolve_qwen_base_url(settings)
    except ProviderConfigurationError as exc:
        return ProviderStatus(
            enabled=True,
            available=False,
            provider=provider,
            model=model,
            streaming=False,
            function_calls=False,
            reason=exc.reason,
        )
    return ProviderStatus(
        enabled=True,
        available=True,
        provider=provider,
        model=model,
        streaming=True,
        function_calls=True,
    )


def get_vision_provider_status(settings: Settings) -> VisionProviderStatus:
    """Return the one runtime contract allowed by the Beijing consent notice."""

    provider = _normalized_provider(settings)
    model = settings.ai_vision_model.strip()
    region = settings.ai_region.strip().lower()

    def rejected(reason: str) -> VisionProviderStatus:
        return VisionProviderStatus(
            enabled=settings.ai_cloud_vision_enabled,
            available=False,
            provider=provider,
            model=model,
            region=region,
            reason=reason,
        )

    if not settings.ai_cloud_vision_enabled:
        return rejected("vision_disabled")
    if not settings.ai_enabled:
        return rejected("disabled")
    if model != _VISION_MODEL:
        return rejected("vision_model_not_allowed")
    if region != _VISION_REGION:
        return rejected("vision_region_not_allowed")

    app_env = settings.app_env.strip().lower()
    if settings.ai_test_fake_vision_enabled:
        if app_env == "test" and provider == "fake":
            return VisionProviderStatus(
                enabled=True,
                available=True,
                provider=provider,
                model=model,
                region=region,
                test_only=True,
            )
        return rejected("test_fake_vision_not_allowed")

    if provider != _VISION_PROVIDER:
        return rejected("vision_provider_not_allowed")
    if settings.ai_base_url.strip():
        return rejected("vision_base_url_override_not_allowed")

    provider_status = get_provider_status(settings)
    if not provider_status.available:
        return rejected(provider_status.reason or "provider_unavailable")
    try:
        base_url = resolve_qwen_base_url(settings)
    except ProviderConfigurationError as exc:
        return rejected(exc.reason)

    workspace_id = settings.ai_workspace_id.strip().lower()
    expected_base_url = (
        f"https://{workspace_id}.{_VISION_REGION}.maas.aliyuncs.com/"
        "compatible-mode/v1"
    )
    parsed = urlsplit(base_url)
    if (
        base_url != expected_base_url
        or parsed.scheme != "https"
        or parsed.hostname
        != f"{workspace_id}.{_VISION_REGION}.maas.aliyuncs.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return rejected("vision_endpoint_not_allowed")

    return VisionProviderStatus(
        enabled=True,
        available=True,
        provider=provider,
        model=model,
        region=region,
        base_url=base_url,
    )


def get_pilot_provider_status(settings: Settings) -> PilotProviderStatus:
    """Validate the only real Provider contract approved for production Pilot."""

    provider = _normalized_provider(settings)
    model = settings.ai_default_model.strip()
    region = settings.ai_region.strip().lower()

    def rejected(reason: str) -> PilotProviderStatus:
        return PilotProviderStatus(
            available=False,
            provider=provider,
            model=model,
            region=region,
            reason=reason,
        )

    if provider != _VISION_PROVIDER:
        return rejected("pilot_provider_not_allowed")
    if region != _VISION_REGION:
        return rejected("pilot_region_not_allowed")
    if model != _VISION_MODEL:
        return rejected("pilot_model_not_allowed")
    if settings.ai_base_url.strip():
        return rejected("pilot_base_url_override_not_allowed")

    provider_status = get_provider_status(settings)
    if not provider_status.available:
        return rejected(provider_status.reason or "provider_unavailable")
    try:
        base_url = resolve_qwen_base_url(settings)
    except ProviderConfigurationError as exc:
        return rejected(exc.reason)
    workspace_id = settings.ai_workspace_id.strip().lower()
    expected_base_url = (
        f"https://{workspace_id}.{_VISION_REGION}.maas.aliyuncs.com/"
        "compatible-mode/v1"
    )
    if base_url != expected_base_url:
        return rejected("pilot_endpoint_not_allowed")
    return PilotProviderStatus(
        available=True,
        provider=provider,
        model=model,
        region=region,
        base_url=base_url,
    )


def build_provider(
    settings: Settings,
    *,
    require_vision: bool = False,
) -> LLMProvider:
    if require_vision:
        vision_status = get_vision_provider_status(settings)
        if not vision_status.available:
            raise ProviderConfigurationError(
                vision_status.reason or "vision_provider_unavailable"
            )
        if vision_status.test_only:
            return FakeProvider()
        if vision_status.base_url is None:
            raise ProviderConfigurationError("vision_endpoint_not_allowed")
        return QwenResponsesProvider(
            api_key=settings.dashscope_api_key.get_secret_value(),
            base_url=vision_status.base_url,
            timeout_seconds=settings.ai_request_timeout_seconds,
            reasoning_effort=settings.ai_reasoning_effort,
        )

    status = get_provider_status(settings)
    if not status.available:
        raise ProviderConfigurationError(status.reason or "provider_unavailable")
    if status.provider == "fake":
        return FakeProvider()
    return QwenResponsesProvider(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=resolve_qwen_base_url(settings),
        timeout_seconds=settings.ai_request_timeout_seconds,
        reasoning_effort=settings.ai_reasoning_effort,
    )
