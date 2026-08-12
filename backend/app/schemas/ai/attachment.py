from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

AIImageMediaType = Literal["image/png", "image/jpeg", "image/webp"]
AIImageAttachmentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]


def _strict_true(value: object) -> object:
    if value is not True:
        raise ValueError("consent must be explicitly accepted")
    return value


AICloudConsentAccepted = Annotated[Literal[True], BeforeValidator(_strict_true)]

# A 4 MiB binary payload needs 5,592,408 Base64 characters. Keep only a small
# Data URL header allowance so a single field cannot grow without bound.
MAX_IMAGE_DATA_URL_CHARS = 5_592_512


class AIImageAttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: AIImageAttachmentId
    media_type: AIImageMediaType
    data_url: str = Field(
        min_length=1,
        max_length=MAX_IMAGE_DATA_URL_CHARS,
        repr=False,
    )


class AICloudProcessingConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    accepted: AICloudConsentAccepted
    notice_version: Literal["aliyun-cn-beijing-v1"]
    attachment_ids: list[AIImageAttachmentId] = Field(min_length=1, max_length=3)
