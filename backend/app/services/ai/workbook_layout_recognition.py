"""Legacy planned-schedule adapter for the unified workbook-mapping Skill.

New runtime code should call ``injection_workbook_mapping_recognition``
directly. This module only preserves the older plan-layout return type for
callers that have not yet migrated; it does not own a second prompt or tool.
"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.schemas.ai.workbook import (
    AIInjectionPlanLayoutRecognitionV1,
    AIWorkbookRecognitionPacketV1,
)
from app.services.ai.injection_workbook_mapping_recognition import (
    InjectionWorkbookMappingRecognitionError,
    recognize_injection_workbook_mapping,
)
from app.services.ai.provider_factory import build_provider
from app.services.ai.providers import LLMProvider
from app.services.injection_scheduling_ai_layout import _legacy_plan_layout


class WorkbookLayoutRecognitionError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code


async def recognize_workbook_layout(
    *,
    packet: AIWorkbookRecognitionPacketV1,
    provider: LLMProvider,
    settings: Settings,
    request_id: str,
) -> AIInjectionPlanLayoutRecognitionV1:
    try:
        mapping = await recognize_injection_workbook_mapping(
            packet=packet,
            provider=provider,
            settings=settings,
            request_id=request_id,
            requested_kind="PLANNED_SCHEDULE",
        )
    except InjectionWorkbookMappingRecognitionError as exc:
        code = (
            "AI_LAYOUT_INVALID_OUTPUT"
            if exc.code == "AI_MAPPING_INVALID_OUTPUT"
            else exc.code
        )
        raise WorkbookLayoutRecognitionError(
            code, exc.public_message, status_code=exc.status_code
        ) from exc
    return _legacy_plan_layout(mapping, business_date=packet.business_date)


def recognize_workbook_layout_sync(
    *,
    packet: AIWorkbookRecognitionPacketV1,
    settings: Settings,
    request_id: str,
) -> AIInjectionPlanLayoutRecognitionV1:
    async def run() -> AIInjectionPlanLayoutRecognitionV1:
        provider = build_provider(settings)
        try:
            return await recognize_workbook_layout(
                packet=packet,
                provider=provider,
                settings=settings,
                request_id=request_id,
            )
        finally:
            await provider.aclose()

    return asyncio.run(run())
