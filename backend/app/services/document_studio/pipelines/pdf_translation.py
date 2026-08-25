from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True)
class _TranslationFragment:
    literal: str = ""
    request_index: int | None = None
    leading_whitespace: str = ""
    trailing_whitespace: str = ""


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


def _split_protected(
    text: str,
    tokens: tuple[str, ...],
) -> tuple[tuple[str, bool], ...]:
    if not tokens:
        return ((text, False),)
    escaped_tokens = (
        re.escape(token) for token in sorted(tokens, key=len, reverse=True)
    )
    pattern = re.compile("|".join(escaped_tokens))
    fragments: list[tuple[str, bool]] = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            fragments.append((text[cursor : match.start()], False))
        fragments.append((match.group(0), True))
        cursor = match.end()
    if cursor < len(text):
        fragments.append((text[cursor:], False))
    return tuple(fragments)


def _queue_translation_fragments(
    text: str,
    tokens: tuple[str, ...],
    requests: list[str],
) -> tuple[_TranslationFragment, ...]:
    fragments: list[_TranslationFragment] = []
    for value, is_protected in _split_protected(text, tokens):
        if is_protected or not any(char.isalpha() for char in value):
            fragments.append(_TranslationFragment(literal=value))
            continue
        leading = value[: len(value) - len(value.lstrip())]
        trailing = value[len(value.rstrip()) :]
        core_end = len(value) - len(trailing) if trailing else len(value)
        core = value[len(leading) : core_end]
        if not core:
            fragments.append(_TranslationFragment(literal=value))
            continue
        request_index = len(requests)
        requests.append(core)
        fragments.append(
            _TranslationFragment(
                request_index=request_index,
                leading_whitespace=leading,
                trailing_whitespace=trailing,
            )
        )
    return tuple(fragments)


def _restore_fragments(
    fragments: tuple[_TranslationFragment, ...],
    translated: Sequence[str],
) -> str:
    restored: list[str] = []
    for fragment in fragments:
        if fragment.request_index is None:
            restored.append(fragment.literal)
            continue
        value = translated[fragment.request_index].strip()
        if not value:
            raise PdfTranslationError("翻译结果包含空白文本单元。")
        restored.append(
            fragment.leading_whitespace + value + fragment.trailing_whitespace
        )
    return "".join(restored)


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
        tuple[
            dict[str, object],
            str,
            str,
            tuple[_TranslationFragment, ...],
            list[float],
        ]
    ] = []
    translation_requests: list[str] = []
    for page in payload["pages"]:
        for block in page["blocks"]:
            source_text = str(block["raw_text"])
            if not source_text.strip():
                continue
            fragments = _queue_translation_fragments(
                source_text,
                _protected(source_text, protected_tokens),
                translation_requests,
            )
            units.append(
                (block, "normalized_text", source_text, fragments, block["bbox"])
            )
        for table in page["tables"]:
            for cell in table["cells"]:
                source_text = str(cell["raw_text"])
                if not source_text.strip():
                    continue
                fragments = _queue_translation_fragments(
                    source_text,
                    _protected(source_text, protected_tokens),
                    translation_requests,
                )
                units.append(
                    (
                        cell,
                        "normalized_value",
                        source_text,
                        fragments,
                        cell["source_bbox"],
                    )
                )
    if not units:
        raise PdfTranslationError("文档没有可翻译的文本单元。")
    translated = (
        translator(translation_requests, direction) if translation_requests else []
    )
    if len(translated) != len(translation_requests):
        raise PdfTranslationError("翻译单元数量与源文档不一致。")
    for target, output_key, source_text, fragments, bbox in units:
        restored = _restore_fragments(fragments, translated)
        target[output_key] = restored
        overflow = _overflow(source_text, restored, bbox)
        if output_key == "normalized_text":
            target["needs_review"] = overflow
        elif overflow:
            target["review_reasons"] = ["TEXT_OVERFLOW"]
    payload["languages"] = ["zh-CN", "en"]
    return DocumentSnapshot.model_validate(payload)
