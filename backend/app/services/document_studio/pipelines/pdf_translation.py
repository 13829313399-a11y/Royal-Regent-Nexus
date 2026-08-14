from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from app.core.config import Settings
from app.schemas.document_studio import DocumentSnapshot
from app.services.document_translation import OfflineDocumentTranslator

TranslationBatch = Callable[[Sequence[str], str], list[str]]

_AUTO_PROTECTED = re.compile(
    r"https?://\S+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"(?<!\w)(?:[A-Z]{2,}[-_/])?[A-Z0-9]{2,}(?:[-_/][A-Z0-9]+)+(?!\w)|"
    r"(?<!\w)[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?!\w)"
)


class PdfTranslationError(RuntimeError):
    code = "DOCUMENT_TRANSLATION_FAILED"
    retryable = False


def _direction(snapshot: DocumentSnapshot, requested: str) -> str:
    if requested == "ZH_TO_EN":
        return "zh_to_en"
    if requested == "EN_TO_ZH":
        return "en_to_zh"
    text = "".join(
        [
            *(block.raw_text for page in snapshot.pages for block in page.blocks),
            *(
                cell.raw_text
                for page in snapshot.pages
                for table in page.tables
                for cell in table.cells
            ),
        ]
    )
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    letters = sum(char.isalpha() for char in text)
    return "zh_to_en" if cjk >= max(1, letters // 3) else "en_to_zh"


def _protected(text: str, configured: tuple[str, ...]) -> tuple[str, ...]:
    values = [match.group(0) for match in _AUTO_PROTECTED.finditer(text)]
    values.extend(token for token in configured if token in text)
    return tuple(dict.fromkeys(values))


def _mask(text: str, tokens: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    masked = text
    placeholders: dict[str, str] = {}
    for index, token in enumerate(sorted(tokens, key=len, reverse=True)):
        placeholder = f"RRNPROTECTEDTOKEN{index:04d}"
        masked = masked.replace(token, placeholder)
        placeholders[placeholder] = token
    return masked, placeholders


def _restore(text: str, placeholders: dict[str, str]) -> str:
    restored = text
    for placeholder, token in placeholders.items():
        if placeholder not in restored:
            raise PdfTranslationError("翻译结果丢失了受保护的数字或业务代码。")
        restored = restored.replace(placeholder, token)
    return restored


def _overflow(source: str, target: str, bbox: list[float]) -> bool:
    width = max(1.0, float(bbox[2]) - float(bbox[0]))
    height = max(1.0, float(bbox[3]) - float(bbox[1]))
    estimated_capacity = max(12, int(width / 6) * max(1, int(height / 12)))
    return len(target) > max(estimated_capacity, len(source) * 3 + 20)


def translate_snapshot(
    snapshot: DocumentSnapshot,
    *,
    settings: Settings,
    requested_direction: str,
    protected_tokens: tuple[str, ...],
    translator: TranslationBatch | None = None,
) -> DocumentSnapshot:
    direction = _direction(snapshot, requested_direction)
    if translator is None:
        offline = OfflineDocumentTranslator(
            settings.document_translation_model_dir,
            device=settings.document_translation_device,
        )
        if not offline.is_ready():
            raise PdfTranslationError("服务器尚未安装完整的中英双向离线翻译模型。")
        translator = offline.translate_batch

    payload = snapshot.model_dump(mode="json")
    units: list[
        tuple[dict[str, object], str, str, dict[str, str], list[float]]
    ] = []
    masked_texts: list[str] = []
    for page in payload["pages"]:
        for block in page["blocks"]:
            source_text = str(block["raw_text"])
            if not source_text.strip():
                continue
            masked, placeholders = _mask(
                source_text,
                _protected(source_text, protected_tokens),
            )
            units.append((block, "normalized_text", source_text, placeholders, block["bbox"]))
            masked_texts.append(masked)
        for table in page["tables"]:
            for cell in table["cells"]:
                source_text = str(cell["raw_text"])
                if not source_text.strip():
                    continue
                masked, placeholders = _mask(
                    source_text,
                    _protected(source_text, protected_tokens),
                )
                units.append(
                    (
                        cell,
                        "normalized_value",
                        source_text,
                        placeholders,
                        cell["source_bbox"],
                    )
                )
                masked_texts.append(masked)
    if not units:
        raise PdfTranslationError("文档没有可翻译的文本单元。")
    translated = translator(masked_texts, direction)
    if len(translated) != len(units):
        raise PdfTranslationError("翻译单元数量与源文档不一致。")
    for (target, output_key, source_text, placeholders, bbox), value in zip(
        units, translated, strict=True
    ):
        restored = _restore(value, placeholders)
        target[output_key] = restored
        overflow = _overflow(source_text, restored, bbox)
        if output_key == "normalized_text":
            target["needs_review"] = overflow
        elif overflow:
            target["review_reasons"] = ["TEXT_OVERFLOW"]
    payload["languages"] = ["zh-CN", "en"]
    return DocumentSnapshot.model_validate(payload)
