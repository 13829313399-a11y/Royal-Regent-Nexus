from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_no: str = Field(min_length=1, max_length=80)
    item_sheet_name: Literal["ITEM表", "恐龙蛋口水车Iteam表"]
    product_name_zh: str = Field(default="", max_length=200)
    product_name_en: str = Field(default="", max_length=300)
    default_pack: str = Field(default="", max_length=7)

    @field_validator("product_no")
    @classmethod
    def identifier(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._/-]*", value):
            raise ValueError("货号只能包含英文、数字及常用货号分隔符")
        return value

    @field_validator("default_pack")
    @classmethod
    def pack(cls, value):
        value = value.strip()
        if value and (not re.fullmatch(r"[1-9]\d{0,6}", value) or int(value) > 1000000):
            raise ValueError("默认装箱数须为 1 至 1000000 的整数，或留空")
        return value

    @field_validator("product_name_zh", "product_name_en")
    @classmethod
    def text(cls, value):
        value = value.strip()
        if value.startswith(("=", "+", "-", "@")) or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("名称不能是表格公式或控制字符")
        return value


class ProductChoice(ProductValue):
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("reason")
    @classmethod
    def note(cls, value):
        value = value.strip()
        if not 4 <= len(value) <= 500:
            raise ValueError("请填写 4 至 500 字的核对原因")
        return value


class ProductSave(ProductChoice):
    expected_revision: int = Field(ge=0, strict=True)
    active: bool = Field(default=True, strict=True)
