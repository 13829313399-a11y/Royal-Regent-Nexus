from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.config import Settings
from app.services.document_tools.contracts import DocumentToolError
from app.services.document_tools.qwen_client import (
    convert_qwen_error,
    create_qwen_client,
)


class QwenTranslationService:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self.client = create_qwen_client(settings, client=client)

    def translate_batch(
        self,
        texts: Sequence[str],
        direction: str,
        *,
        terms: Sequence[dict[str, str]] = (),
        translation_memory: Sequence[dict[str, str]] = (),
        domain_prompt: str = "",
    ) -> list[str]:
        if direction not in {"zh_to_en", "en_to_zh"}:
            raise DocumentToolError(
                "DOCUMENT_TRANSLATION_DIRECTION_INVALID",
                "翻译方向无效。",
                action="请选择中译英、英译中或自动识别。",
            )
        source_lang = "Chinese" if direction == "zh_to_en" else "English"
        target_lang = "English" if direction == "zh_to_en" else "Chinese"
        options: dict[str, object] = {
            "source_lang": source_lang,
            "target_lang": target_lang,
        }
        if terms:
            options["terms"] = list(terms)[:50]
        if translation_memory:
            options["tm_list"] = list(translation_memory)[:20]
        if domain_prompt.strip():
            options["domains"] = domain_prompt.strip()[:2000]

        translated: list[str] = []
        try:
            for text in texts:
                if not text.strip():
                    translated.append(text)
                    continue
                response = self.client.chat.completions.create(
                    model=self.settings.qwen_translation_model,
                    messages=[{"role": "user", "content": text}],
                    extra_body={"translation_options": options},
                )
                content = response.choices[0].message.content
                if not isinstance(content, str) or not content.strip():
                    raise DocumentToolError(
                        "QWEN_TRANSLATION_EMPTY",
                        "千问翻译返回了空结果。",
                        action="请重试；若持续失败，请管理员检查翻译模型配置。",
                        retryable=True,
                        status_code=502,
                    )
                translated.append(content.strip())
        except DocumentToolError:
            raise
        except Exception as exc:
            raise convert_qwen_error(exc, operation="翻译") from exc
        return translated
