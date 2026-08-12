from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import struct
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import pytest
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

if TYPE_CHECKING:
    from app.core.config import Settings

_LIVE_FLAG = "AI_B7A_LIVE"
_EXPECTED_MODEL = "qwen3.7-plus"
_EXPECTED_REGION = "cn-beijing"
_FUNCTION_NAME = "report_synthetic_image_probe"
_SAFE_EVENT_TYPE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_.-")
_PROVIDER_LOGGERS = ("openai", "httpx", "httpcore")


@dataclass(frozen=True, slots=True)
class SafeProbeEvidence:
    classification: str
    http_status: int | None
    response_status: str | None
    event_types: tuple[str, ...]

    def as_json(self) -> str:
        return json.dumps(
            {
                "classification": self.classification,
                "event_types": list(self.event_types),
                "http_status": self.http_status,
                "response_status": self.response_status,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


class ProbeProtocolError(Exception):
    def __init__(self, classification: str) -> None:
        super().__init__(classification)
        self.classification = classification


class LiveConfigurationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _live_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return source.get(_LIVE_FLAG, "") == "1"


def _read(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", checksum)
    )


def _synthetic_png_data_url() -> str:
    width = 32
    height = 32
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)  # PNG filter type: None.
        for x in range(width):
            if x < width // 2 and y < height // 2:
                color = (255, 0, 0)
            elif x >= width // 2 and y < height // 2:
                color = (0, 255, 0)
            elif x < width // 2 and y >= height // 2:
                color = (0, 0, 255)
            else:
                color = (255, 255, 255)
            pixels.extend(color)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(pixels), level=9))
        + _png_chunk(b"IEND", b"")
    )
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _request_kwargs(*, model: str, image_data_url: str) -> dict[str, object]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Inspect the synthetic four-quadrant PNG. Call the "
                            f"{_FUNCTION_NAME} function exactly once and do not "
                            "return prose. Set image_input_accepted to true only if "
                            "the image was available to you."
                        ),
                    },
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
        "tools": [
            {
                "type": "function",
                "name": _FUNCTION_NAME,
                "description": "Report whether the synthetic image was available.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_input_accepted": {"type": "boolean"},
                        "observed_pattern": {
                            "type": "string",
                            "enum": [
                                "four_color_quadrants",
                                "other",
                                "unclear",
                            ],
                        },
                    },
                    "required": ["image_input_accepted", "observed_pattern"],
                    "additionalProperties": False,
                },
            }
        ],
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "max_output_tokens": 256,
        "store": False,
        "stream": True,
    }


def _safe_event_type(value: object) -> str:
    if not isinstance(value, str):
        return "invalid_event_type"
    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 80
        or any(char not in _SAFE_EVENT_TYPE_CHARS for char in normalized)
    ):
        return "invalid_event_type"
    return normalized


def _safe_response_status(value: object) -> str | None:
    if isinstance(value, str) and value in {
        "completed",
        "failed",
        "incomplete",
        "cancelled",
    }:
        return value
    return "unknown" if value is not None else None


def _safe_http_status(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
    if isinstance(value, int) and 100 <= value <= 599:
        return value
    return None


def _classify_sdk_error(exc: Exception, status: int | None) -> str:
    if isinstance(exc, (APITimeoutError, TimeoutError, asyncio.TimeoutError)):
        return "timeout"
    if isinstance(exc, APIConnectionError):
        return "connection_error"
    if status in {400, 415, 422}:
        return "image_data_url_or_request_rejected"
    if status in {401, 403}:
        return "authentication_rejected"
    if status == 404:
        return "route_or_model_not_found"
    if status == 429:
        return "rate_limited"
    if status is not None and status >= 500:
        return "provider_error"
    return "sdk_error"


def _validate_function_call(item: object) -> bool:
    if _read(item, "type") != "function_call":
        return False
    if _read(item, "name") != _FUNCTION_NAME:
        raise ProbeProtocolError("unexpected_function_call")
    arguments = _read(item, "arguments")
    if not isinstance(arguments, str):
        raise ProbeProtocolError("invalid_function_arguments")
    try:
        payload = json.loads(arguments)
    except (TypeError, ValueError) as exc:
        raise ProbeProtocolError("invalid_function_arguments") from exc
    if not isinstance(payload, dict):
        raise ProbeProtocolError("invalid_function_arguments")
    if payload.get("image_input_accepted") is not True:
        raise ProbeProtocolError("model_did_not_confirm_image_input")
    observed_pattern = payload.get("observed_pattern")
    if observed_pattern not in {
        "four_color_quadrants",
        "other",
        "unclear",
    }:
        raise ProbeProtocolError("invalid_function_arguments")
    if observed_pattern != "four_color_quadrants":
        raise ProbeProtocolError("model_did_not_observe_expected_pattern")
    return True


def _inspect_completed_response(response: object) -> tuple[str | None, bool]:
    response_status = _safe_response_status(_read(response, "status"))
    function_seen = False
    output = _read(response, "output", ()) or ()
    try:
        for item in output:
            function_seen = _validate_function_call(item) or function_seen
    except TypeError as exc:
        raise ProbeProtocolError("invalid_completed_response") from exc
    return response_status, function_seen


async def _run_live_probe(*, settings: Settings, base_url: str) -> SafeProbeEvidence:
    client = AsyncOpenAI(
        api_key=settings.dashscope_api_key.get_secret_value(),
        base_url=f"{base_url.rstrip('/')}/",
        timeout=settings.ai_request_timeout_seconds,
        max_retries=0,
    )
    stream: Any | None = None
    event_types: set[str] = set()
    response_status: str | None = None
    function_seen = False
    completed_seen = False
    previous_levels = {
        name: logging.getLogger(name).level for name in _PROVIDER_LOGGERS
    }
    for name in _PROVIDER_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    try:
        stream = await client.responses.create(
            **_request_kwargs(
                model=settings.ai_default_model.strip(),
                image_data_url=_synthetic_png_data_url(),
            )
        )
        async for event in stream:
            event_type = _safe_event_type(_read(event, "type"))
            event_types.add(event_type)
            if event_type == "response.output_item.done":
                function_seen = (
                    _validate_function_call(_read(event, "item")) or function_seen
                )
            elif event_type == "response.completed":
                completed_seen = True
                response = _read(event, "response")
                if response is None:
                    raise ProbeProtocolError("missing_completed_response")
                response_status, completed_function_seen = _inspect_completed_response(
                    response
                )
                function_seen = function_seen or completed_function_seen
            elif event_type in {
                "response.failed",
                "response.incomplete",
                "error",
            }:
                raise ProbeProtocolError("provider_reported_failure_event")
    except ProbeProtocolError as exc:
        return SafeProbeEvidence(
            classification=exc.classification,
            http_status=None,
            response_status=response_status,
            event_types=tuple(sorted(event_types)),
        )
    except Exception as exc:  # noqa: BLE001 - redact the SDK boundary completely
        status = _safe_http_status(exc)
        return SafeProbeEvidence(
            classification=_classify_sdk_error(exc, status),
            http_status=status,
            response_status=response_status,
            event_types=tuple(sorted(event_types)),
        )
    finally:
        if stream is not None:
            close_stream = getattr(stream, "close", None)
            if close_stream is not None:
                try:
                    await close_stream()
                except Exception:  # noqa: BLE001, S110 - do not leak cleanup detail
                    pass
        try:
            await client.close()
        except Exception:  # noqa: BLE001, S110 - do not leak cleanup detail
            pass
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)

    if not completed_seen or response_status != "completed":
        classification = "stream_did_not_complete"
    elif not function_seen:
        classification = "custom_function_call_missing"
    else:
        classification = "passed_image_stream_function_call"
    return SafeProbeEvidence(
        classification=classification,
        http_status=None,
        response_status=response_status,
        event_types=tuple(sorted(event_types)),
    )


def _load_live_configuration() -> tuple[Settings, str]:
    # Keep app Settings (and therefore its configured env file) out of default test
    # collection. Standard Settings are loaded only after the explicit live marker.
    from app.core.config import Settings
    from app.services.ai.provider_factory import (
        ProviderConfigurationError,
        get_provider_status,
        resolve_qwen_base_url,
    )

    settings = Settings()
    if settings.ai_cloud_vision_enabled:
        raise LiveConfigurationError("production_vision_flag_must_remain_disabled")
    if settings.ai_provider.strip().lower() != "qwen":
        raise LiveConfigurationError("provider_must_be_qwen")
    if settings.ai_default_model.strip() != _EXPECTED_MODEL:
        raise LiveConfigurationError("model_must_be_qwen3_7_plus")
    if settings.ai_region.strip().lower() != _EXPECTED_REGION:
        raise LiveConfigurationError("region_must_be_cn_beijing")
    if settings.ai_base_url.strip():
        raise LiveConfigurationError("base_url_override_forbidden_for_live_spike")

    status = get_provider_status(settings)
    if not status.available:
        raise LiveConfigurationError(status.reason or "provider_unavailable")
    try:
        base_url = resolve_qwen_base_url(settings)
    except ProviderConfigurationError as exc:
        raise LiveConfigurationError(exc.reason) from None
    parsed = urlsplit(base_url)
    expected_host = (
        f"{settings.ai_workspace_id.strip().lower()}."
        f"{_EXPECTED_REGION}.maas.aliyuncs.com"
    )
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        raise LiveConfigurationError("unexpected_live_endpoint")
    return settings, base_url


def test_ai_b7a_live_probe_requires_exact_explicit_flag(monkeypatch):
    monkeypatch.delenv(_LIVE_FLAG, raising=False)
    assert _live_enabled() is False

    for value in ("", "0", "true", "yes", "on"):
        monkeypatch.setenv(_LIVE_FLAG, value)
        assert _live_enabled() is False

    monkeypatch.setenv(_LIVE_FLAG, "1")
    assert _live_enabled() is True


def test_ai_b7a_probe_request_is_in_memory_and_custom_function_only():
    data_url = _synthetic_png_data_url()
    prefix = "data:image/png;base64,"
    is_png_data_url = data_url.startswith(prefix)
    assert is_png_data_url is True

    png = base64.b64decode(data_url[len(prefix) :], validate=True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (32, 32)

    kwargs = _request_kwargs(model=_EXPECTED_MODEL, image_data_url=data_url)
    assert kwargs["store"] is False
    assert kwargs["stream"] is True
    assert kwargs["parallel_tool_calls"] is False
    assert kwargs["tool_choice"] == "required"
    tools = kwargs["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    tool_types = {tool["type"] for tool in tools}
    assert tool_types == {"function"}
    assert tools[0]["name"] == _FUNCTION_NAME

    inputs = kwargs["input"]
    assert isinstance(inputs, list)
    content = inputs[0]["content"]
    has_image_input = any(item.get("type") == "input_image" for item in content)
    assert has_image_input is True


@pytest.mark.parametrize("observed_pattern", ["other", "unclear"])
def test_ai_b7a_probe_does_not_pass_when_model_cannot_see_pattern(
    observed_pattern,
):
    item = {
        "type": "function_call",
        "name": _FUNCTION_NAME,
        "arguments": json.dumps(
            {
                "image_input_accepted": True,
                "observed_pattern": observed_pattern,
            }
        ),
    }

    with pytest.raises(ProbeProtocolError) as exc_info:
        _validate_function_call(item)

    assert exc_info.value.classification == ("model_did_not_observe_expected_pattern")


@pytest.mark.skipif(
    not _live_enabled(),
    reason=f"set {_LIVE_FLAG}=1 explicitly to run the provider compatibility spike",
)
def test_qwen_responses_accepts_data_url_image_stream_and_function_call(request):
    try:
        settings, base_url = _load_live_configuration()
    except LiveConfigurationError as exc:
        pytest.fail(
            f"AI-B7A live configuration rejected: {exc.reason}",
            pytrace=False,
        )

    evidence = asyncio.run(_run_live_probe(settings=settings, base_url=base_url))
    request.node.user_properties.append(("ai_b7a_safe_evidence", evidence.as_json()))
    if evidence.classification != "passed_image_stream_function_call":
        pytest.fail(evidence.as_json(), pytrace=False)
