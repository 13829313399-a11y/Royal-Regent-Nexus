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

import pytest

_LIVE_FLAG = "AI_B7B_LIVE"
_EXPECTED_REPLY = "B7B_FOUR_QUADRANTS_OK"
_PROVIDER_LOGGERS = ("openai", "httpx", "httpcore")


@dataclass(frozen=True, slots=True)
class SafeLiveEvidence:
    classification: str
    provider_code: str | None
    status_code: int | None
    completed: bool

    def as_json(self) -> str:
        return json.dumps(
            {
                "classification": self.classification,
                "completed": self.completed,
                "provider_code": self.provider_code,
                "status_code": self.status_code,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


class LiveConfigurationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _live_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return source.get(_LIVE_FLAG, "") == "1"


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
        pixels.append(0)
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
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _load_live_configuration():
    # Keep Settings and its env-file source out of default test collection.
    from app.core.config import Settings
    from app.services.ai.provider_factory import get_vision_provider_status

    settings = Settings()
    status = get_vision_provider_status(settings)
    if not status.available or status.base_url is None or status.test_only:
        raise LiveConfigurationError(status.reason or "vision_provider_unavailable")
    return settings, status.base_url


async def _run_live_canary(settings, base_url: str) -> SafeLiveEvidence:
    from app.schemas.ai.attachment import AIImageAttachmentInput
    from app.services.ai.attachment_service import (
        clear_prepared_attachments,
        discard_raw_attachment_inputs,
        prepare_image_attachments,
    )
    from app.services.ai.providers.base import (
        ProviderCompleted,
        ProviderError,
        ProviderImageContent,
        ProviderMessage,
        ProviderRequest,
        ProviderTextContent,
        ProviderTextDelta,
        ProviderToolCallEvent,
    )
    from app.services.ai.providers.qwen_responses import QwenResponsesProvider

    attachment = AIImageAttachmentInput.model_validate(
        {
            "id": "synthetic-four-quadrants",
            "media_type": "image/png",
            "data_url": _synthetic_png_data_url(),
        }
    )
    prepared = ()
    provider = None
    previous_levels = {
        name: logging.getLogger(name).level for name in _PROVIDER_LOGGERS
    }
    for name in _PROVIDER_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)

    try:
        prepared = prepare_image_attachments(
            [attachment],
            max_count=settings.ai_max_image_attachments,
            max_bytes=settings.ai_max_image_bytes,
            max_total_bytes=settings.ai_max_image_total_bytes,
            max_encoded_chars=settings.ai_max_image_encoded_chars,
            max_pixels=settings.ai_max_image_pixels,
            max_total_pixels=settings.ai_max_image_total_pixels,
        )
        discard_raw_attachment_inputs([attachment])
        provider = QwenResponsesProvider(
            api_key=settings.dashscope_api_key.get_secret_value(),
            base_url=base_url,
            timeout_seconds=settings.ai_request_timeout_seconds,
            reasoning_effort=settings.ai_reasoning_effort,
        )
        request = ProviderRequest(
            model=settings.ai_vision_model.strip(),
            request_id="ai-b7b-live-synthetic",
            input=(
                ProviderMessage(
                    role="user",
                    content=(
                        ProviderTextContent(
                            text=(
                                "Inspect this synthetic 2x2 quadrant image. Reply with "
                                f"exactly {_EXPECTED_REPLY} only if top-left is red, "
                                "top-right green, bottom-left blue, and bottom-right "
                                "white. Otherwise reply exactly B7B_PATTERN_MISMATCH."
                            )
                        ),
                        ProviderImageContent(
                            attachment_id=prepared[0].attachment_id,
                            media_type=prepared[0].media_type,
                            data=prepared[0].data,
                        ),
                    ),
                ),
            ),
            tools=(),
            max_output_tokens=64,
        )
        output_parts: list[str] = []
        completed = False
        async for event in provider.stream(request):
            if isinstance(event, ProviderTextDelta):
                if sum(len(part) for part in output_parts) + len(event.delta) > 256:
                    return SafeLiveEvidence("output_too_large", None, None, False)
                output_parts.append(event.delta)
            elif isinstance(event, ProviderToolCallEvent):
                return SafeLiveEvidence("unexpected_tool_call", None, None, False)
            elif isinstance(event, ProviderCompleted):
                completed = True
        if not completed:
            return SafeLiveEvidence("stream_did_not_complete", None, None, False)
        if "".join(output_parts).strip() != _EXPECTED_REPLY:
            return SafeLiveEvidence("synthetic_pattern_mismatch", None, None, True)
        return SafeLiveEvidence("passed_sanitized_image_stream", None, None, True)
    except ProviderError as exc:
        return SafeLiveEvidence(
            "provider_error",
            exc.code.value,
            exc.status_code,
            False,
        )
    except Exception:  # noqa: BLE001 - never expose SDK/config/image details
        return SafeLiveEvidence("internal_canary_error", None, None, False)
    finally:
        discard_raw_attachment_inputs([attachment])
        clear_prepared_attachments(prepared)
        if provider is not None:
            try:
                await provider.aclose()
            except Exception:  # noqa: BLE001, S110 - preserve redacted evidence
                pass
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)


def test_ai_b7b_live_canary_requires_exact_explicit_flag(monkeypatch):
    monkeypatch.delenv(_LIVE_FLAG, raising=False)
    assert _live_enabled() is False
    for value in ("", "0", "true", "yes", "on"):
        monkeypatch.setenv(_LIVE_FLAG, value)
        assert _live_enabled() is False
    monkeypatch.setenv(_LIVE_FLAG, "1")
    assert _live_enabled() is True


@pytest.mark.skipif(
    not _live_enabled(),
    reason=f"set {_LIVE_FLAG}=1 explicitly to run the sanitized-image canary",
)
def test_qwen_b7b_sanitizer_to_provider_live_canary(request):
    try:
        settings, base_url = _load_live_configuration()
    except LiveConfigurationError as exc:
        pytest.fail(
            f"AI-B7B live configuration rejected: {exc.reason}",
            pytrace=False,
        )

    evidence = asyncio.run(_run_live_canary(settings, base_url))
    request.node.user_properties.append(("ai_b7b_safe_evidence", evidence.as_json()))
    if evidence.classification != "passed_sanitized_image_stream":
        pytest.fail(evidence.as_json(), pytrace=False)
