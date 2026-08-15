from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import pypdfium2 as pdfium
from pypdf import PdfReader

try:
    import resource
except ImportError:  # pragma: no cover - Windows development only
    resource = None


class OfficePdfRenderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable


@dataclass(frozen=True)
class OfficePdfRenderResult:
    content: bytes
    output_file_name: str
    page_count: int
    blank_page_count: int = 0


_EXTERNAL_RELATIONSHIP = re.compile(
    rb"TargetMode\s*=\s*[\"']External[\"']",
    re.IGNORECASE,
)
_MACRO_PARTS = {"word/vbaproject.bin", "word/vbadata.xml"}
_FONT_ATTRIBUTES = {"ascii", "hAnsi", "eastAsia", "cs"}
_FONT_SUBSTITUTIONS = {
    "aptos": {"liberation sans", "dejavu sans"},
    "calibri": {"liberation sans", "dejavu sans"},
    "cambria": {"liberation serif", "dejavu serif"},
    "arial": {"liberation sans", "dejavu sans"},
    "times new roman": {"liberation serif", "dejavu serif"},
    "courier": {"liberation mono", "dejavu sans mono"},
    "courier new": {"liberation mono", "dejavu sans mono"},
    "microsoft yahei": {"noto sans cjk sc"},
    "微软雅黑": {"noto sans cjk sc"},
    "simsun": {"noto serif cjk sc"},
    "宋体": {"noto serif cjk sc"},
    "simhei": {"noto sans cjk sc"},
    "黑体": {"noto sans cjk sc"},
    "仿宋": {"noto serif cjk sc"},
    "等线": {"noto sans cjk sc"},
}


def _safe_filename(value: str) -> str:
    stem = re.sub(r'[\\/:*?"<>|]+', "_", Path(value or "Word文档.docx").stem)
    return f"{stem.strip(' .') or 'Word文档'}_转换结果.pdf"


def _validate_docx(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = {name.casefold() for name in archive.namelist()}
            if "[content_types].xml" not in names or "word/document.xml" not in names:
                raise OfficePdfRenderError(
                    "DOCUMENT_OFFICE_INPUT_CORRUPT",
                    "DOCX 缺少必要的 Office 文档部件。",
                )
            if names.intersection(_MACRO_PARTS):
                raise OfficePdfRenderError(
                    "DOCUMENT_INPUT_MACRO_REJECTED",
                    "不接受包含宏的 Word 文档。",
                )
            for name in archive.namelist():
                lowered = name.casefold()
                if lowered.endswith(".rels") and _EXTERNAL_RELATIONSHIP.search(
                    archive.read(name)
                ):
                    raise OfficePdfRenderError(
                        "DOCUMENT_EXTERNAL_LINK_REJECTED",
                        "Word 文档包含外部关系，已拒绝转换。",
                    )
                if lowered == "word/document.xml":
                    ElementTree.fromstring(archive.read(name))
    except OfficePdfRenderError:
        raise
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise OfficePdfRenderError(
            "DOCUMENT_OFFICE_INPUT_CORRUPT",
            "DOCX 文件已损坏或结构无效。",
        ) from exc


def _requested_fonts(content: bytes) -> frozenset[str]:
    fonts: set[str] = set()
    with zipfile.ZipFile(BytesIO(content)) as archive:
        for name in ("word/document.xml", "word/styles.xml"):
            if name not in archive.namelist():
                continue
            root = ElementTree.fromstring(archive.read(name))
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] != "rFonts":
                    continue
                for attribute, value in element.attrib.items():
                    local_name = attribute.rsplit("}", 1)[-1]
                    if local_name in _FONT_ATTRIBUTES and value.strip():
                        fonts.add(value.strip())
    return frozenset(fonts)


@lru_cache(maxsize=1)
def _installed_fonts() -> frozenset[str] | None:
    executable = shutil.which("fc-list")
    if executable is None:
        return None
    completed = subprocess.run(
        [executable, "--format=%{family}\n"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        return None
    return frozenset(
        family.strip().casefold()
        for line in completed.stdout.splitlines()
        for family in line.split(",")
        if family.strip()
    )


def _validate_fonts(content: bytes) -> None:
    requested = _requested_fonts(content)
    if not requested:
        return
    installed = _installed_fonts()
    if installed is None:
        return
    missing = []
    for font in requested:
        normalized = font.casefold()
        if normalized in installed:
            continue
        substitutions = _FONT_SUBSTITUTIONS.get(normalized, set())
        if substitutions.intersection(installed):
            continue
        missing.append(font)
    if missing:
        preview = "、".join(sorted(missing)[:5])
        raise OfficePdfRenderError(
            "DOCUMENT_FONT_MISSING",
            f"Office 渲染环境缺少文档字体：{preview}。",
        )


def _validate_pdf(content: bytes) -> tuple[int, int]:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) < 1:
            raise ValueError("invalid PDF")
        page_count = len(reader.pages)
        document = pdfium.PdfDocument(content)
        blank_page_count = 0
        for page_index in range(page_count):
            image = document[page_index].render(scale=0.25, grayscale=True).to_pil()
            histogram = image.convert("L").histogram()
            dark_pixels = sum(histogram[:250])
            threshold = max(5, image.width * image.height // 10_000)
            if dark_pixels <= threshold:
                blank_page_count += 1
        return page_count, blank_page_count
    except Exception as exc:
        raise OfficePdfRenderError(
            "DOCUMENT_OFFICE_OUTPUT_INVALID",
            "Office 渲染器未生成有效 PDF。",
        ) from exc


def render_docx_to_pdf(
    content: bytes,
    source_filename: str,
    *,
    command: str,
    timeout_seconds: int = 120,
    network_isolation_command: str | None = "unshare",
) -> OfficePdfRenderResult:
    _validate_docx(content)
    executable = shutil.which(command)
    if executable is None:
        raise OfficePdfRenderError(
            "DOCUMENT_OFFICE_RENDERER_UNAVAILABLE",
            "受限 Office 渲染器未安装。",
        )
    _validate_fonts(content)
    isolation_executable = (
        shutil.which(network_isolation_command)
        if network_isolation_command
        else None
    )
    if os.name != "nt" and network_isolation_command and isolation_executable is None:
        raise OfficePdfRenderError(
            "DOCUMENT_OFFICE_RENDERER_UNAVAILABLE",
            "Office 渲染器缺少无外网隔离命令。",
        )
    with tempfile.TemporaryDirectory(prefix="rrn-office-render-") as temp_dir:
        root = Path(temp_dir)
        source = root / "source.docx"
        output_dir = root / "output"
        profile_dir = root / "profile"
        output_dir.mkdir()
        profile_dir.mkdir()
        source.write_bytes(content)
        profile_url = profile_dir.resolve().as_uri()
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "HOME": str(root),
            "USERPROFILE": str(root),
        }
        try:
            office_command = [
                    executable,
                    "--headless",
                    "--safe-mode",
                    "--nologo",
                    "--nodefault",
                    "--norestore",
                    "--nolockcheck",
                    "--nofirststartwizard",
                    f"-env:UserInstallation={profile_url}",
                    "--convert-to",
                    "pdf:writer_pdf_Export",
                    "--outdir",
                    str(output_dir),
                    str(source),
                ]
            command_line = (
                [isolation_executable, "--net", "--", *office_command]
                if os.name != "nt" and isolation_executable is not None
                else office_command
            )

            def apply_limits() -> None:
                if resource is None:
                    return
                resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 5))
                resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
                resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2, 100 * 1024**2))
                resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

            completed = subprocess.run(
                command_line,
                check=False,
                capture_output=True,
                env=environment,
                timeout=timeout_seconds,
                preexec_fn=apply_limits if os.name != "nt" else None,
            )
        except subprocess.TimeoutExpired as exc:
            raise OfficePdfRenderError(
                "DOCUMENT_OFFICE_RENDER_TIMEOUT",
                "Word 转 PDF 超时。",
                retryable=True,
            ) from exc
        result_path = output_dir / "source.pdf"
        if completed.returncode != 0 or not result_path.is_file():
            raise OfficePdfRenderError(
                "DOCUMENT_OFFICE_RENDER_FAILED",
                "Office 渲染器未能完成 Word 转 PDF。",
                retryable=True,
            )
        result = result_path.read_bytes()
        page_count, blank_page_count = _validate_pdf(result)
        return OfficePdfRenderResult(
            content=result,
            output_file_name=_safe_filename(source_filename),
            page_count=page_count,
            blank_page_count=blank_page_count,
        )
