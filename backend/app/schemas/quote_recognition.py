"""Text-only, bounded choices for Silverlit recognition; never accepts quote amounts."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecognitionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sheet: str = Field(min_length=1, max_length=80)
    cell: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,5}$")
    text: str = Field(min_length=1, max_length=400)


class RecognitionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    evidence: list[RecognitionEvidence] = Field(default_factory=list, max_length=3)


class RecognitionTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=160)
    kind: Literal["tool_match", "header", "cost_category"]
    target: str = Field(min_length=1, max_length=80)
    source: RecognitionEvidence
    context: list[RecognitionEvidence] = Field(default_factory=list, max_length=8)
    choices: list[RecognitionChoice] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def unique_choices(self):
        if len({c.id for c in self.choices}) != len(self.choices):
            raise ValueError("候选标识不能重复")
        return self


class QuoteRecognitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    factory_id: Literal["huaxing"]
    customer_id: Literal["yinhui"]
    tasks: list[RecognitionTask] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def bound_request(self):
        if len({t.id for t in self.tasks}) != len(self.tasks):
            raise ValueError("识别任务标识不能重复")
        if len(json.dumps(self.model_dump(), ensure_ascii=False)) > 100000:
            raise ValueError("识别文字过多，请分批处理")
        return self
