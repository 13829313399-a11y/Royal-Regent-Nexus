from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError


class AiProvider(ABC):
    @abstractmethod
    def complete_json(
        self, *, system_prompt: str, user_prompt: str, result_model: type[BaseModel]
    ) -> BaseModel:
        raise NotImplementedError


class DisabledAiProvider(AiProvider):
    def complete_json(
        self, *, system_prompt: str, user_prompt: str, result_model: type[BaseModel]
    ) -> BaseModel:
        raise HTTPException(
            status_code=503,
            detail="千问辅助当前未启用；导入、看板和排程核心功能不受影响",
        )


class QwenProvider(AiProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("QWEN_API_KEY", "").strip()
        self.base_url = os.getenv(
            "QWEN_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).rstrip("/")
        self.model = os.getenv("QWEN_MODEL", "qwen-plus").strip() or "qwen-plus"
        self.timeout_seconds = min(
            max(float(os.getenv("QWEN_TIMEOUT_SECONDS", "8")), 1), 30
        )
        if not self.api_key:
            raise HTTPException(
                status_code=503, detail="千问已启用但未配置 QWEN_API_KEY"
            )

    def complete_json(
        self, *, system_prompt: str, user_prompt: str, result_model: type[BaseModel]
    ) -> BaseModel:
        schema = result_model.model_json_schema()
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n只返回满足以下 JSON Schema 的对象："
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": user_prompt[:12_000]},
            ],
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=503, detail="千问服务暂时不可用，请稍后重试"
            ) from exc
        try:
            content = result["choices"][0]["message"]["content"]
            normalized = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                str(content).strip(),
                flags=re.IGNORECASE,
            )
            return result_model.model_validate(json.loads(normalized))
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise HTTPException(
                status_code=502, detail="千问返回内容未通过结构校验，未执行任何写入"
            ) from exc


def get_ai_provider() -> AiProvider:
    enabled = os.getenv("QWEN_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return QwenProvider() if enabled else DisabledAiProvider()
