from __future__ import annotations

import functools
import json
import posixpath
import re
import threading
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable, Literal, Sequence
from zipfile import BadZipFile, ZipFile

from lxml import etree


TranslationDirection = Literal["zh_to_en", "en_to_zh"]
TranslationFunction = Callable[[Sequence[str], TranslationDirection], Sequence[str]]

MAX_ARCHIVE_ENTRIES = 5_000
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_TRANSLATABLE_UNITS = 20_000
MAX_TRANSLATABLE_CHARACTERS = 500_000
MAX_MODEL_CHUNK_CHARACTERS = 220

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
OFFICE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
URL_OR_EMAIL_PATTERN = re.compile(r"(?:https?://|www\.|\S+@\S+\.\S+)", re.IGNORECASE)
CODE_LIKE_PATTERN = re.compile(r"^[A-Za-z]*\d[A-Za-z0-9._/#\-:]*$")
SHORT_ACRONYM_PATTERN = re.compile(r"^[A-Z]{1,5}$")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[。！？!?；;\.])\s*")

MODEL_SUBDIRECTORIES = {
    "zh_to_en": "zh_en",
    "en_to_zh": "en_zh",
}

EXACT_GLOSSARY = {
    "zh_to_en": {
        "采购订单": "Purchase Order",
        "订单": "Order",
        "订单号": "Order No.",
        "合同号": "Contract No.",
        "物料号": "Item No.",
        "物料编号": "Item No.",
        "产品名称": "Product Name",
        "客户": "Customer",
        "供应商": "Supplier",
        "数量": "Quantity",
        "单位": "Unit",
        "单价": "Unit Price",
        "金额": "Amount",
        "合计": "Total",
        "交货日期": "Delivery Date",
        "出货日期": "Shipment Date",
        "规格": "Specification",
        "备注": "Remarks",
        "日期": "Date",
    },
    "en_to_zh": {
        "purchase order": "采购订单",
        "order": "订单",
        "order no.": "订单号",
        "order no": "订单号",
        "contract no.": "合同号",
        "contract no": "合同号",
        "item no.": "物料号",
        "item no": "物料号",
        "item number": "物料号",
        "product name": "产品名称",
        "customer": "客户",
        "supplier": "供应商",
        "quantity": "数量",
        "unit": "单位",
        "unit price": "单价",
        "amount": "金额",
        "total": "合计",
        "delivery date": "交货日期",
        "shipment date": "出货日期",
        "ship date": "出货日期",
        "specification": "规格",
        "remarks": "备注",
        "date": "日期",
    },
}


class DocumentTranslationError(RuntimeError):
    pass


class DocumentTranslationUnavailableError(DocumentTranslationError):
    pass


@dataclass(frozen=True)
class DocumentTranslationResult:
    content: bytes
    output_file_name: str
    media_type: str
    translated_unit_count: int
    skipped_unit_count: int
    processed_part_count: int


@dataclass
class _TextUnit:
    nodes: list[etree._Element]
    source_text: str


@dataclass
class _ParsedPart:
    name: str
    root: etree._Element
    units: list[_TextUnit]


class _OfflineModel:
    def __init__(self, package_dir: Path, *, device: str):
        try:
            import ctranslate2
            import sentencepiece
        except ImportError as exc:
            raise DocumentTranslationUnavailableError(
                "离线翻译运行库尚未安装，请安装 ctranslate2 与 sentencepiece。"
            ) from exc

        metadata_path = package_dir / "metadata.json"
        model_path = package_dir / "model"
        tokenizer_path = package_dir / "sentencepiece.model"
        if not metadata_path.is_file() or not model_path.is_dir() or not tokenizer_path.is_file():
            raise DocumentTranslationUnavailableError(
                f"离线翻译模型不完整：{package_dir.name}。请重新安装中英模型。"
            )

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DocumentTranslationUnavailableError("离线翻译模型元数据无法读取。") from exc

        self.target_prefix = str(metadata.get("target_prefix") or "")
        try:
            self.processor = sentencepiece.SentencePieceProcessor(
                model_file=str(tokenizer_path)
            )
            self.translator = ctranslate2.Translator(
                str(model_path),
                device=device,
                inter_threads=1,
                intra_threads=0,
                compute_type="auto",
            )
        except Exception as exc:
            raise DocumentTranslationUnavailableError(
                f"离线翻译模型加载失败：{exc}"
            ) from exc

    def translate(self, texts: Sequence[str]) -> list[str]:
        chunk_groups = [_split_for_model(text) for text in texts]
        chunks = [chunk for group in chunk_groups for chunk in group]
        if not chunks:
            return ["" for _ in texts]

        tokenized = [self.processor.encode(chunk, out_type=str) for chunk in chunks]
        target_prefix = None
        if self.target_prefix:
            target_prefix = [[self.target_prefix] for _ in tokenized]

        try:
            batches = self.translator.translate_batch(
                tokenized,
                target_prefix=target_prefix,
                replace_unknowns=True,
                max_batch_size=32,
                batch_type="tokens",
                beam_size=4,
                num_hypotheses=1,
                length_penalty=0.2,
                return_scores=False,
            )
        except Exception as exc:
            raise DocumentTranslationError(f"离线翻译执行失败：{exc}") from exc

        translated_chunks: list[str] = []
        for batch in batches:
            pieces = batch.hypotheses[0]
            value = self.processor.decode(pieces).replace("▁", " ")
            if self.target_prefix and value.startswith(self.target_prefix):
                value = value[len(self.target_prefix) :]
            translated_chunks.append(value.lstrip())

        translated_texts: list[str] = []
        offset = 0
        for group in chunk_groups:
            group_result = translated_chunks[offset : offset + len(group)]
            translated_texts.append("".join(group_result))
            offset += len(group)
        return translated_texts


class OfflineDocumentTranslator:
    def __init__(self, model_dir: str | Path, *, device: str = "cpu"):
        self.model_dir = Path(model_dir)
        self.device = device
        self._models: dict[TranslationDirection, _OfflineModel] = {}
        self._lock = threading.Lock()

    def is_ready(self) -> bool:
        return all(_model_package_ready(self.model_dir / subdir) for subdir in MODEL_SUBDIRECTORIES.values())

    def translate_batch(
        self,
        texts: Sequence[str],
        direction: TranslationDirection,
    ) -> list[str]:
        translated: list[str | None] = [None] * len(texts)
        pending_texts: list[str] = []
        pending_indexes: list[int] = []
        glossary = EXACT_GLOSSARY[direction]
        for index, text in enumerate(texts):
            key = text.strip() if direction == "zh_to_en" else text.strip().casefold()
            glossary_value = glossary.get(key)
            if glossary_value is not None:
                prefix, _core, suffix = _split_outer_whitespace(text)
                translated[index] = f"{prefix}{glossary_value}{suffix}"
            else:
                pending_indexes.append(index)
                pending_texts.append(text)

        if not pending_texts:
            return [value or "" for value in translated]

        with self._lock:
            model = self._models.get(direction)
            if model is None:
                package_dir = self.model_dir / MODEL_SUBDIRECTORIES[direction]
                model = _OfflineModel(package_dir, device=self.device)
                self._models[direction] = model
        model_values = model.translate(pending_texts)
        for index, value in zip(pending_indexes, model_values, strict=True):
            translated[index] = value
        return [value or "" for value in translated]


@functools.lru_cache(maxsize=4)
def _cached_offline_translator(model_dir: str, device: str) -> OfflineDocumentTranslator:
    return OfflineDocumentTranslator(model_dir, device=device)


def translate_texts_locally(
    texts: Sequence[str],
    direction: TranslationDirection,
    *,
    model_dir: str | Path,
    device: str = "cpu",
) -> list[str]:
    """Reuse the document engine without creating or persisting a document."""
    if direction not in MODEL_SUBDIRECTORIES:
        raise DocumentTranslationError("翻译方向无效。")
    translator = _cached_offline_translator(str(Path(model_dir).resolve()), device)
    return translator.translate_batch(texts, direction)


def document_translation_status(model_dir: str | Path) -> dict[str, object]:
    root = Path(model_dir)
    directions = {
        direction: _model_package_ready(root / subdir)
        for direction, subdir in MODEL_SUBDIRECTORIES.items()
    }
    runtime_ready = True
    try:
        import ctranslate2  # noqa: F401
        import sentencepiece  # noqa: F401
    except ImportError:
        runtime_ready = False
    return {
        "available": runtime_ready and all(directions.values()),
        "engine": "offline",
        "engineLabel": "服务器离线中英模型",
        "directions": directions,
    }


def translate_document(
    content: bytes,
    file_name: str,
    *,
    direction: TranslationDirection,
    translator: TranslationFunction | None = None,
    model_dir: str | Path | None = None,
    device: str = "cpu",
    selected_sheet_names: Sequence[str] | None = None,
) -> DocumentTranslationResult:
    if direction not in MODEL_SUBDIRECTORIES:
        raise DocumentTranslationError("翻译方向无效，只支持中译英或英译中。")

    extension = Path(file_name).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".docx"}:
        raise DocumentTranslationError("只支持 .xlsx、.xlsm 或 .docx 文件。")
    if extension == ".docx" and selected_sheet_names is not None:
        raise DocumentTranslationError("Word 文档不支持工作表选择。")

    if translator is None:
        if model_dir is None:
            raise DocumentTranslationUnavailableError("服务器尚未配置离线翻译模型目录。")
        offline_translator = _cached_offline_translator(
            str(Path(model_dir).resolve()),
            device,
        )
        if not offline_translator.is_ready():
            raise DocumentTranslationUnavailableError(
                "服务器尚未安装完整的中英双向离线翻译模型。"
            )
        translator = offline_translator.translate_batch

    try:
        source_archive = ZipFile(BytesIO(content), "r")
    except BadZipFile as exc:
        raise DocumentTranslationError("文件内容不是有效的 Office 文档。") from exc

    with source_archive:
        infos = source_archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise DocumentTranslationError("Office 文档内部文件数量过多，无法安全处理。")
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise DocumentTranslationError("Office 文档解压后内容过大，无法安全处理。")

        expected_marker = "xl/workbook.xml" if extension in {".xlsx", ".xlsm"} else "word/document.xml"
        if expected_marker not in {info.filename for info in infos}:
            raise DocumentTranslationError("文件扩展名与 Office 文档内容不匹配。")

        payloads = {info.filename: source_archive.read(info.filename) for info in infos}
        parsed_parts = _parse_translatable_parts(
            payloads,
            extension,
            selected_sheet_names=selected_sheet_names,
        )

        all_units = [unit for part in parsed_parts for unit in part.units]
        candidates: list[tuple[_TextUnit, str, str, str]] = []
        skipped_count = 0
        unique_texts: list[str] = []
        seen_texts: set[str] = set()

        for unit in all_units:
            prefix, core, suffix = _split_outer_whitespace(unit.source_text)
            if not _should_translate(core, direction):
                skipped_count += 1
                continue
            candidates.append((unit, prefix, core, suffix))
            if core not in seen_texts:
                seen_texts.add(core)
                unique_texts.append(core)

        if not candidates:
            direction_label = "中文" if direction == "zh_to_en" else "英文"
            raise DocumentTranslationError(f"未检测到可翻译的{direction_label}文字。")
        if len(candidates) > MAX_TRANSLATABLE_UNITS:
            raise DocumentTranslationError(
                f"可翻译文本超过 {MAX_TRANSLATABLE_UNITS} 段，请拆分文档后重试。"
            )
        if sum(len(text) for text in unique_texts) > MAX_TRANSLATABLE_CHARACTERS:
            raise DocumentTranslationError("可翻译文字总量超过 50 万字符，请拆分文档后重试。")

        translated_values = list(translator(unique_texts, direction))
        if len(translated_values) != len(unique_texts):
            raise DocumentTranslationError("翻译引擎返回的文本段数量不一致，已停止生成文件。")
        if any(not isinstance(value, str) or not value.strip() for value in translated_values):
            raise DocumentTranslationError("翻译引擎返回了空文本，已停止生成文件。")

        translation_map = dict(zip(unique_texts, translated_values, strict=True))
        for unit, prefix, core, suffix in candidates:
            _write_unit_text(unit, f"{prefix}{translation_map[core]}{suffix}")

        for part in parsed_parts:
            payloads[part.name] = etree.tostring(
                part.root,
                encoding="UTF-8",
                xml_declaration=True,
                standalone=None,
            )

        output = BytesIO()
        from zipfile import ZipFile as OutputZipFile

        with OutputZipFile(output, "w") as target_archive:
            for info in infos:
                target_archive.writestr(info, payloads[info.filename])

    safe_stem = _safe_output_stem(file_name)
    direction_suffix = "中译英" if direction == "zh_to_en" else "英译中"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if extension == ".docx"
        else "application/vnd.ms-excel.sheet.macroEnabled.12"
        if extension == ".xlsm"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return DocumentTranslationResult(
        content=output.getvalue(),
        output_file_name=f"{safe_stem}_{direction_suffix}{extension}",
        media_type=media_type,
        translated_unit_count=len(candidates),
        skipped_unit_count=skipped_count,
        processed_part_count=len(parsed_parts),
    )


def _parse_translatable_parts(
    payloads: dict[str, bytes],
    extension: str,
    *,
    selected_sheet_names: Sequence[str] | None = None,
) -> list[_ParsedPart]:
    parsed: list[_ParsedPart] = []
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)

    if extension in {".xlsx", ".xlsm"}:
        part_names = _selected_excel_part_names(
            payloads,
            parser,
            selected_sheet_names=selected_sheet_names,
        )
        shared_strings = _excel_shared_string_entries(payloads, parser)
    else:
        part_names = {
            name for name in payloads
            if _is_translatable_part(name, extension)
        }
        shared_strings = []

    for name in sorted(part_names):
        payload = payloads[name]
        try:
            root = etree.fromstring(payload, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise DocumentTranslationError(f"Office 文档内部 XML 无法读取：{name}") from exc

        if extension in {".xlsx", ".xlsm"}:
            if name.startswith("xl/worksheets/"):
                _materialize_selected_shared_strings(root, shared_strings)
            units = _excel_units(name, root)
        else:
            units = _word_units(root)
        if units:
            parsed.append(_ParsedPart(name=name, root=root, units=units))
    return parsed


def _selected_excel_part_names(
    payloads: dict[str, bytes],
    parser: etree.XMLParser,
    *,
    selected_sheet_names: Sequence[str] | None,
) -> set[str]:
    workbook_root = _parse_xml_payload(payloads, "xl/workbook.xml", parser)
    workbook_relationships = {
        relationship_id: target
        for relationship_id, target in _relationship_targets(
            payloads,
            "xl/workbook.xml",
            parser,
        )
    }
    sheet_parts: dict[str, str] = {}
    for sheet in workbook_root.xpath(".//s:sheet", namespaces={"s": SPREADSHEET_NS}):
        sheet_name = sheet.get("name")
        relationship_id = sheet.get(f"{{{OFFICE_RELATIONSHIP_NS}}}id")
        target = workbook_relationships.get(relationship_id or "")
        if sheet_name and target and target.startswith("xl/worksheets/") and target in payloads:
            sheet_parts[sheet_name] = target

    if not sheet_parts:
        raise DocumentTranslationError("Excel 文件中未找到可读取的工作表。")

    if selected_sheet_names is None:
        requested_names = list(sheet_parts)
    else:
        requested_names = list(dict.fromkeys(selected_sheet_names))
        if not requested_names:
            raise DocumentTranslationError("请至少选择一个需要翻译的工作表。")
        if any(not isinstance(name, str) or not name.strip() for name in requested_names):
            raise DocumentTranslationError("工作表选择参数格式不正确。")
        missing_names = [name for name in requested_names if name not in sheet_parts]
        if missing_names:
            raise DocumentTranslationError(
                f"未找到所选工作表：{'、'.join(missing_names)}。请重新上传文件后选择。"
            )

    selected_parts = {sheet_parts[name] for name in requested_names}
    pending = list(selected_parts)
    while pending:
        source_part = pending.pop()
        for _relationship_id, target in _relationship_targets(payloads, source_part, parser):
            if target not in payloads or target in selected_parts:
                continue
            if not _is_translatable_excel_related_part(target):
                continue
            selected_parts.add(target)
            pending.append(target)
    return selected_parts


def _parse_xml_payload(
    payloads: dict[str, bytes],
    name: str,
    parser: etree.XMLParser,
) -> etree._Element:
    payload = payloads.get(name)
    if payload is None:
        raise DocumentTranslationError(f"Office 文档缺少必要内部文件：{name}")
    try:
        return etree.fromstring(payload, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise DocumentTranslationError(f"Office 文档内部 XML 无法读取：{name}") from exc


def _relationship_targets(
    payloads: dict[str, bytes],
    source_part: str,
    parser: etree.XMLParser,
) -> list[tuple[str, str]]:
    relationships_name = posixpath.join(
        posixpath.dirname(source_part),
        "_rels",
        f"{posixpath.basename(source_part)}.rels",
    )
    payload = payloads.get(relationships_name)
    if payload is None:
        return []
    try:
        root = etree.fromstring(payload, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise DocumentTranslationError(
            f"Office 文档内部 XML 无法读取：{relationships_name}"
        ) from exc

    targets: list[tuple[str, str]] = []
    for relationship in root.xpath(
        ".//pr:Relationship",
        namespaces={"pr": PACKAGE_RELATIONSHIP_NS},
    ):
        if relationship.get("TargetMode") == "External":
            continue
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")
        if not relationship_id or not target:
            continue
        if target.startswith("/"):
            resolved_target = target.lstrip("/")
        else:
            resolved_target = posixpath.normpath(
                posixpath.join(posixpath.dirname(source_part), target)
            )
        targets.append((relationship_id, resolved_target))
    return targets


def _is_translatable_excel_related_part(name: str) -> bool:
    return (
        (name.startswith("xl/comments") and name.endswith(".xml"))
        or (name.startswith("xl/drawings/") and name.endswith(".xml"))
        or (name.startswith("xl/charts/") and name.endswith(".xml"))
        or (name.startswith("xl/diagrams/") and name.endswith(".xml"))
    )


def _excel_shared_string_entries(
    payloads: dict[str, bytes],
    parser: etree.XMLParser,
) -> list[etree._Element]:
    payload = payloads.get("xl/sharedStrings.xml")
    if payload is None:
        return []
    try:
        root = etree.fromstring(payload, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise DocumentTranslationError(
            "Office 文档内部 XML 无法读取：xl/sharedStrings.xml"
        ) from exc
    return root.xpath("./s:si", namespaces={"s": SPREADSHEET_NS})


def _materialize_selected_shared_strings(
    worksheet_root: etree._Element,
    shared_strings: Sequence[etree._Element],
) -> None:
    cells = worksheet_root.xpath(
        ".//s:c[@t='s' and not(s:f)]",
        namespaces={"s": SPREADSHEET_NS},
    )
    for cell in cells:
        value_node = cell.find(f"{{{SPREADSHEET_NS}}}v")
        if value_node is None or value_node.text is None:
            continue
        try:
            shared_index = int(value_node.text)
            shared_entry = shared_strings[shared_index]
        except (ValueError, IndexError):
            raise DocumentTranslationError("Excel 文件包含无效的共享字符串索引。") from None

        inline_string = etree.Element(f"{{{SPREADSHEET_NS}}}is")
        for child in shared_entry:
            inline_string.append(deepcopy(child))
        value_index = cell.index(value_node)
        cell.remove(value_node)
        cell.insert(value_index, inline_string)
        cell.set("t", "inlineStr")


def _is_translatable_part(name: str, extension: str) -> bool:
    if extension in {".xlsx", ".xlsm"}:
        return (
            name == "xl/sharedStrings.xml"
            or (name.startswith("xl/worksheets/") and name.endswith(".xml"))
            or (name.startswith("xl/comments") and name.endswith(".xml"))
            or (name.startswith("xl/drawings/") and name.endswith(".xml"))
            or (name.startswith("xl/charts/") and name.endswith(".xml"))
            or (name.startswith("xl/diagrams/") and name.endswith(".xml"))
        )
    return (
        name == "word/document.xml"
        or (name.startswith("word/header") and name.endswith(".xml"))
        or (name.startswith("word/footer") and name.endswith(".xml"))
        or name in {
            "word/footnotes.xml",
            "word/endnotes.xml",
            "word/comments.xml",
            "word/glossary/document.xml",
        }
    )


def _excel_units(name: str, root: etree._Element) -> list[_TextUnit]:
    containers: list[etree._Element]
    if name == "xl/sharedStrings.xml":
        containers = root.xpath(".//s:si", namespaces={"s": SPREADSHEET_NS})
    elif name.startswith("xl/worksheets/"):
        containers = root.xpath(".//s:is", namespaces={"s": SPREADSHEET_NS})
    elif name.startswith("xl/comments"):
        containers = root.xpath(".//s:comment/s:text", namespaces={"s": SPREADSHEET_NS})
    else:
        containers = root.xpath(".//a:p", namespaces={"a": DRAWING_NS})

    units: list[_TextUnit] = []
    for container in containers:
        nodes = [
            node
            for node in container.xpath(".//s:t | .//a:t", namespaces={"s": SPREADSHEET_NS, "a": DRAWING_NS})
            if node.text
        ]
        if nodes:
            units.append(_TextUnit(nodes=nodes, source_text="".join(node.text or "" for node in nodes)))
    if name.startswith("xl/worksheets/"):
        direct_string_nodes = root.xpath(
            ".//s:c[@t='str' and not(s:f)]/s:v",
            namespaces={"s": SPREADSHEET_NS},
        )
        units.extend(
            _TextUnit(nodes=[node], source_text=node.text or "")
            for node in direct_string_nodes
            if node.text
        )
    return units


def _word_units(root: etree._Element) -> list[_TextUnit]:
    units: list[_TextUnit] = []
    for paragraph in root.xpath(".//w:p[not(.//w:p)]", namespaces={"w": WORD_NS}):
        groups: list[list[etree._Element]] = []
        current: list[etree._Element] = []
        field_depth = 0

        for element in paragraph.iter():
            if element.tag == f"{{{WORD_NS}}}fldChar":
                field_type = element.get(f"{{{WORD_NS}}}fldCharType")
                if field_type == "begin":
                    if current:
                        groups.append(current)
                        current = []
                    field_depth += 1
                elif field_type == "end":
                    field_depth = max(0, field_depth - 1)
                continue
            if element.tag in {f"{{{WORD_NS}}}tab", f"{{{WORD_NS}}}br", f"{{{WORD_NS}}}cr"}:
                if current:
                    groups.append(current)
                    current = []
                continue
            if element.tag == f"{{{WORD_NS}}}t" and field_depth == 0 and element.text:
                if any(ancestor.tag == f"{{{WORD_NS}}}fldSimple" for ancestor in element.iterancestors()):
                    continue
                current.append(element)
        if current:
            groups.append(current)

        for nodes in groups:
            source = "".join(node.text or "" for node in nodes)
            if source:
                units.append(_TextUnit(nodes=nodes, source_text=source))
    return units


def _should_translate(text: str, direction: TranslationDirection) -> bool:
    if not text or URL_OR_EMAIL_PATTERN.fullmatch(text):
        return False
    if CODE_LIKE_PATTERN.fullmatch(text) or SHORT_ACRONYM_PATTERN.fullmatch(text):
        return False
    if direction == "zh_to_en":
        return bool(CJK_PATTERN.search(text))
    return bool(LATIN_PATTERN.search(text))


def _split_outer_whitespace(text: str) -> tuple[str, str, str]:
    prefix_length = len(text) - len(text.lstrip())
    suffix_length = len(text) - len(text.rstrip())
    prefix = text[:prefix_length]
    suffix = text[len(text) - suffix_length :] if suffix_length else ""
    core_end = len(text) - suffix_length if suffix_length else len(text)
    return prefix, text[prefix_length:core_end], suffix


def _write_unit_text(unit: _TextUnit, translated_text: str) -> None:
    source_lengths = [len(node.text or "") for node in unit.nodes]
    chunks = _distribute_text(translated_text, source_lengths)
    for node, chunk in zip(unit.nodes, chunks, strict=True):
        node.text = chunk
        if chunk.startswith((" ", "\t", "\n")) or chunk.endswith((" ", "\t", "\n")):
            node.set(XML_SPACE, "preserve")
        else:
            node.attrib.pop(XML_SPACE, None)


def _distribute_text(text: str, source_lengths: Sequence[int]) -> list[str]:
    if not source_lengths:
        return []
    if len(source_lengths) == 1:
        return [text]

    total_source = sum(source_lengths)
    if total_source <= 0:
        return [text] + ["" for _ in source_lengths[1:]]

    boundaries: list[int] = []
    consumed_source = 0
    previous = 0
    for length in source_lengths[:-1]:
        consumed_source += length
        ideal = round(len(text) * consumed_source / total_source)
        boundary = _nearest_word_boundary(text, ideal, previous)
        boundaries.append(boundary)
        previous = boundary

    chunks: list[str] = []
    start = 0
    for boundary in boundaries:
        chunks.append(text[start:boundary])
        start = boundary
    chunks.append(text[start:])
    return chunks


def _nearest_word_boundary(text: str, ideal: int, minimum: int) -> int:
    if ideal <= minimum or ideal >= len(text):
        return max(minimum, min(ideal, len(text)))
    candidates = [
        index
        for index in range(max(minimum + 1, ideal - 8), min(len(text), ideal + 8) + 1)
        if text[index - 1 : index].isspace() or text[index : index + 1].isspace()
    ]
    if not candidates:
        return ideal
    return min(candidates, key=lambda index: (abs(index - ideal), index))


def _split_for_model(text: str) -> list[str]:
    if len(text) <= MAX_MODEL_CHUNK_CHARACTERS:
        return [text]

    sentences = [part for part in SENTENCE_BOUNDARY_PATTERN.split(text) if part]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > MAX_MODEL_CHUNK_CHARACTERS:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                sentence[index : index + MAX_MODEL_CHUNK_CHARACTERS]
                for index in range(0, len(sentence), MAX_MODEL_CHUNK_CHARACTERS)
            )
        elif not current or len(current) + len(sentence) <= MAX_MODEL_CHUNK_CHARACTERS:
            current += sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks or [text]


def _model_package_ready(package_dir: Path) -> bool:
    return (
        (package_dir / "metadata.json").is_file()
        and (package_dir / "sentencepiece.model").is_file()
        and (package_dir / "model").is_dir()
    )


def _safe_output_stem(file_name: str) -> str:
    stem = Path(file_name).stem.strip() or "文档"
    safe = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", stem)
    return safe[:120].rstrip(". ") or "文档"
