from typing import Literal
from pydantic import BaseModel, Field, field_validator


class FeedbackReplyRequest(BaseModel):
    revision: int = Field(ge=1)
    status: Literal["OPEN", "FIXED", "DECLINED"]
    body: str = Field(min_length=1, max_length=3000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请填写回复或处理说明")
        return value.strip()


class FeatureUpdateRequest(BaseModel):
    audience: Literal["INTERNAL", "SUPPLIER"] = "INTERNAL"
    request_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=6000)

    @field_validator("title", "body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("更新标题和说明不能为空")
        return value.strip()
