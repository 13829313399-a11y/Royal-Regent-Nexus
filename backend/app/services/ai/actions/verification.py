from __future__ import annotations

from app.schemas.ai.action_confirmation import AIActionVerificationData


def verification_json(value: AIActionVerificationData) -> dict[str, object]:
    """Return the closed metadata-only verification evidence persisted by the Gateway."""

    return value.model_dump(mode="json")
